from __future__ import annotations

import platform
import socket
import socketserver
import time
from dataclasses import dataclass, field
from secrets import token_bytes, token_hex
from threading import Event, Lock, Semaphore, Thread
from typing import Callable

from linkable_desktop.config import DiscoveryConfig
from linkable_desktop.crypto.identity import DeviceIdentity, PeerIdentity
from linkable_desktop.crypto.session_cipher import EncryptedEnvelopeChannel, derive_directional_keys
from linkable_desktop.input.control import DesktopInputController
from linkable_desktop.pairing.code_generator import PairingChallengeMaterial
from linkable_desktop.pairing.ui_prompts import ConsolePrompts
from linkable_desktop.proto import (
    apps_pb2,
    build_envelope,
    bluetooth_pb2,
    camera_pb2,
    calls_pb2,
    clipboard_pb2,
    common_pb2,
    contacts_pb2,
    decode_payload,
    errors_pb2,
    files_pb2,
    input_pb2,
    notifications_pb2,
    pairing_pb2,
    session_pb2,
    storage_pb2,
    transport_pb2,
    utilities_pb2,
)
from linkable_desktop.session.auth import (
    SESSION_ACK_LABEL,
    SESSION_INIT_LABEL,
    build_session_signature_payload,
    generate_ephemeral_key_pair,
    is_timestamp_fresh,
)
from linkable_desktop.transport.framing import ConnectionIO
from linkable_desktop.transfer.file_receiver import FileReceiver
from linkable_desktop.transfer.file_sender import SendFileRequest, send_file
from linkable_desktop.trust.device_record import TrustedDeviceRecord
from linkable_desktop.trust.trust_store import TrustStore


@dataclass(slots=True)
class ActiveSessionRegistry:
    _lock: Lock = field(default_factory=Lock)
    _device_id: str | None = None
    _token: str | None = None

    def acquire(self, device_id: str) -> str | None:
        with self._lock:
            if self._device_id is not None:
                return None
            token = token_hex(8)
            self._device_id = device_id
            self._token = token
            return token

    def release(self, token: str) -> None:
        with self._lock:
            if self._token != token:
                return
            self._device_id = None
            self._token = None


def _timestamp_ms() -> int:
    return int(time.time() * 1000)


def _peer_from_descriptor(descriptor: common_pb2.PeerDescriptor) -> PeerIdentity:
    return PeerIdentity(
        device_id=descriptor.device_id.fingerprint,
        device_name=descriptor.device_name,
        public_key_bytes=descriptor.identity_public_key,
    )


def _descriptor_from_identity(identity: DeviceIdentity, protocol_version: str) -> common_pb2.PeerDescriptor:
    major, minor, patch = (int(part) for part in protocol_version.split("."))
    descriptor = common_pb2.PeerDescriptor()
    descriptor.device_id.fingerprint = identity.device_id
    descriptor.device_name = identity.device_name
    descriptor.platform = "linux"
    descriptor.protocol_version.major = major
    descriptor.protocol_version.minor = minor
    descriptor.protocol_version.patch = patch
    descriptor.identity_public_key = identity.public_key_bytes
    return descriptor


def _enum_name(enum_type: object, value: int) -> str:
    try:
        return enum_type.Name(value)  # type: ignore[attr-defined]
    except ValueError:
        return f"UNKNOWN_{value}"


def _format_sim_status(sim: calls_pb2.SimStatus) -> str:
    default_flags = []
    if sim.default_voice:
        default_flags.append("voice")
    if sim.default_data:
        default_flags.append("data")
    if sim.default_sms:
        default_flags.append("sms")
    defaults = ",".join(default_flags) if default_flags else "none"
    carrier = sim.carrier_name or sim.display_name or "unknown"
    return f"SIM {sim.sim_slot}: subId={sim.subscription_id}, carrier={carrier}, defaults={defaults}"


def _format_phone_capabilities(snapshot: calls_pb2.PhoneCapabilitySnapshot) -> str:
    permissions = snapshot.permissions
    lines = [
        (
            "permissions: "
            f"READ_PHONE_STATE={permissions.read_phone_state_granted}, "
            f"READ_CALL_LOG={permissions.read_call_log_granted}, "
            f"ANSWER_PHONE_CALLS={permissions.answer_phone_calls_granted}, "
            f"CALL_PHONE={permissions.call_phone_granted}"
        ),
        (
            "phone: "
            f"sims={snapshot.sim_count}, "
            f"ringer={_enum_name(calls_pb2.PhoneRingerMode, snapshot.ringer_mode)}, "
            f"route={_enum_name(calls_pb2.PhoneAudioRouteType, snapshot.active_audio_route)}, "
            f"speakerphone={snapshot.speakerphone_on}, "
            f"wired={snapshot.wired_headset_connected}, "
            f"bt_sco_available={snapshot.bluetooth_sco_available}"
        ),
        (
            "volumes: "
            f"ring={snapshot.ring_volume}/{snapshot.ring_volume_max}, "
            f"voice={snapshot.voice_call_volume}/{snapshot.voice_call_volume_max}"
        ),
        (
            "capabilities: "
            f"call_state={snapshot.call_state_mirroring_supported}, "
            f"caller_id={snapshot.caller_id_supported}, "
            f"call_control={snapshot.call_control_supported}, "
            f"direct_dial={snapshot.direct_dial_supported}, "
            f"lan_call_audio={snapshot.lan_call_audio_supported}, "
            f"bt_audio_recommended={snapshot.bluetooth_call_audio_recommended}"
        ),
    ]
    lines.extend(_format_sim_status(sim) for sim in snapshot.sims)
    if snapshot.detail:
        lines.append(f"detail: {snapshot.detail}")
    return "\n".join(lines)


def _format_call_metadata(event: calls_pb2.CallMetadataEvent) -> str:
    caller = event.caller_id if event.caller_id_available and event.caller_id else "unavailable"
    if caller == "unavailable" and event.masked_caller_id:
        caller = event.masked_caller_id
    sim = (
        f"SIM {event.sim_slot} subId={event.subscription_id} carrier={event.carrier_name or 'unknown'}"
        if event.sim_slot
        else "SIM unknown"
    )
    source = event.source_app_label or event.source_app_package or _enum_name(calls_pb2.CallSourceType, event.source_type)
    return (
        f"state={_enum_name(calls_pb2.PhoneCallState, event.state)}; "
        f"direction={_enum_name(calls_pb2.CallDirection, event.direction)}; "
        f"source={source}; caller={caller}; {sim}; "
        f"route={_enum_name(calls_pb2.PhoneAudioRouteType, event.active_audio_route)}; "
        f"video={event.video_call}; detail={event.detail}"
    )


def _format_notification_actions(notification: notifications_pb2.NotificationPosted) -> str:
    if not notification.actions:
        return "actions=none"
    parts = []
    for action in notification.actions:
        semantic = _enum_name(notifications_pb2.NotificationActionSemantic, action.semantic).removeprefix(
            "NOTIFICATION_ACTION_SEMANTIC_"
        )
        flags = []
        if action.supports_remote_input:
            flags.append("reply")
        if action.supports_plain_intent:
            flags.append("intent")
        suffix = f" ({','.join(flags)})" if flags else ""
        parts.append(f"{action.action_id}:{action.title or semantic}{suffix}")
    return "actions=" + ", ".join(parts)


def _format_telephony_diagnostics(result: calls_pb2.TelephonyDiagnosticsResult) -> str:
    permissions = result.permissions
    lines = [
        f"{result.device_model} / {result.android_version}",
        (
            "permissions: "
            f"READ_PHONE_STATE={permissions.read_phone_state_granted}, "
            f"READ_CALL_LOG={permissions.read_call_log_granted}, "
            f"ANSWER_PHONE_CALLS={permissions.answer_phone_calls_granted}, "
            f"CALL_PHONE={permissions.call_phone_granted}"
        ),
        (
            "capabilities: "
            f"call_state={result.call_state_mirroring_supported}, "
            f"call_control={result.call_control_supported}, "
            f"direct_dial={result.direct_dial_supported}"
        ),
    ]
    if result.sims:
        lines.extend(_format_sim_status(sim) for sim in result.sims)
    else:
        lines.append("SIMs: none visible to app")
    if result.HasField("phone_capabilities"):
        lines.append("phone capabilities:")
        lines.append(_format_phone_capabilities(result.phone_capabilities))
    if result.detail:
        lines.append(f"detail: {result.detail}")
    return "\n".join(lines)


@dataclass(slots=True)
class PairingSessionService:
    config: DiscoveryConfig
    identity: DeviceIdentity
    trust_store: TrustStore
    prompts: ConsolePrompts = field(default_factory=ConsolePrompts)
    send_file_request: SendFileRequest | None = None
    send_file_provider: Callable[[], SendFileRequest | None] | None = None
    ring_phone_request_provider: Callable[[], utilities_pb2.RingPhoneRequest | None] | None = None
    call_control_request_provider: Callable[[], calls_pb2.CallControlRequest | None] | None = None
    dial_request_provider: Callable[[], calls_pb2.DialRequest | None] | None = None
    telephony_diagnostics_request_provider: Callable[[], calls_pb2.TelephonyDiagnosticsRequest | None] | None = None
    notification_reply_request_provider: Callable[[], notifications_pb2.NotificationReplyRequest | None] | None = None
    notification_action_request_provider: Callable[[], notifications_pb2.NotificationActionRequest | None] | None = None
    bluetooth_assist_provider: Callable[[], bluetooth_pb2.BluetoothAssistDesktopStatus | None] | None = None
    shared_app_launch_request_provider: Callable[[], apps_pb2.SharedAppLaunchRequest | None] | None = None
    phone_file_list_request_provider: Callable[[], storage_pb2.PhoneFileListRequest | None] | None = None
    phone_file_pull_request_provider: Callable[[], storage_pb2.PhoneFilePullRequest | None] | None = None
    contacts_request_provider: Callable[[], contacts_pb2.PhoneContactsRequest | None] | None = None
    recent_contacts_request_provider: Callable[[], contacts_pb2.PhoneRecentContactsRequest | None] | None = None
    camera_capability_request_provider: Callable[[], camera_pb2.CameraCapabilityRequest | None] | None = None
    camera_start_request_provider: Callable[[], camera_pb2.CameraStreamStartRequest | None] | None = None
    camera_ack_provider: Callable[[], camera_pb2.CameraStreamAck | None] | None = None
    camera_stop_request_provider: Callable[[], camera_pb2.CameraStreamStopRequest | None] | None = None
    allow_new_pairing_provider: Callable[[], bool] | None = None
    trusted_session_allowed_provider: Callable[[str], bool] | None = None
    disconnect_requested_provider: Callable[[str], bool] | None = None
    active_session_registry: ActiveSessionRegistry = field(default_factory=ActiveSessionRegistry)
    prompt_notification_replies: bool = True
    outgoing_wakeup: Semaphore = field(default_factory=lambda: Semaphore(0))
    _prompt_lock: Lock = field(default_factory=Lock)
    _input_controller: DesktopInputController = field(default_factory=DesktopInputController)

    def handle_connection(self, connection: ConnectionIO, address: str) -> None:
        try:
            envelope = connection.read_envelope(self.config.max_frame_size)
            if envelope.packet_type == common_pb2.PACKET_TYPE_PAIRING_REQUEST:
                self._handle_pairing_request(connection, envelope, address)
                return
            if envelope.packet_type == common_pb2.PACKET_TYPE_SESSION_INIT:
                self._handle_session_init(connection, envelope, address)
                return
            reject = pairing_pb2.PairingReject(
                reason=pairing_pb2.PAIRING_REJECT_REASON_PROTOCOL_MISMATCH,
                detail="expected PairingRequest or SessionInit",
            )
            connection.write_envelope(
                build_envelope(common_pb2.PACKET_TYPE_PAIRING_REJECT, reject, sequence_number=1)
            )
        finally:
            connection.close()

    def _handle_pairing_request(
        self,
        connection: ConnectionIO,
        envelope: common_pb2.Envelope,
        address: str,
    ) -> None:
        request = decode_payload(envelope)
        assert isinstance(request, pairing_pb2.PairingRequest)
        initiator = _peer_from_descriptor(request.initiator)
        if self.allow_new_pairing_provider is not None and not self.allow_new_pairing_provider():
            reject = pairing_pb2.PairingReject(
                reason=pairing_pb2.PAIRING_REJECT_REASON_USER_DECLINED,
                detail="desktop is in trusted-only mode; enable a temporary pairing window to pair a new phone",
            )
            connection.write_envelope(
                build_envelope(common_pb2.PACKET_TYPE_PAIRING_REJECT, reject, sequence_number=2)
            )
            self.prompts.notify(
                f"[pairing blocked] New pairing from {initiator.device_name} ({initiator.device_id}) at {address}; trusted-only mode is active."
            )
            return

        with self._prompt_lock:
            allowed = self.prompts.confirm_pairing(initiator.device_name, initiator.device_id, address)
            if not allowed:
                reject = pairing_pb2.PairingReject(
                    reason=pairing_pb2.PAIRING_REJECT_REASON_USER_DECLINED,
                    detail="desktop user declined pairing",
                )
                connection.write_envelope(
                    build_envelope(common_pb2.PACKET_TYPE_PAIRING_REJECT, reject, sequence_number=2)
                )
                return

            challenge_nonce = token_bytes(32)
            challenge = pairing_pb2.PairingChallenge(
                acceptor=_descriptor_from_identity(self.identity, self.config.protocol_version),
                challenge_nonce=challenge_nonce,
                verification_code_length=6,
                code_derivation_label="linkable-pair-code-v1",
            )
            connection.write_envelope(
                build_envelope(common_pb2.PACKET_TYPE_PAIRING_CHALLENGE, challenge, sequence_number=2)
            )

            material = PairingChallengeMaterial(
                pairing_nonce=request.pairing_nonce,
                challenge_nonce=challenge_nonce,
                initiator_public_key=initiator.public_key_bytes,
                acceptor_public_key=self.identity.public_key_bytes,
                initiator_device_id=initiator.device_id,
                acceptor_device_id=self.identity.device_id,
                code_length=challenge.verification_code_length,
            )
            expected_code = material.pairing_code()
            typed_code = self.prompts.prompt_code()
            if typed_code != expected_code:
                reject = pairing_pb2.PairingReject(
                    reason=pairing_pb2.PAIRING_REJECT_REASON_CODE_MISMATCH,
                    detail="desktop code entry mismatch",
                )
                connection.write_envelope(
                    build_envelope(common_pb2.PACKET_TYPE_PAIRING_REJECT, reject, sequence_number=3)
                )
                return

        confirm_envelope = connection.read_envelope(self.config.max_frame_size)
        if confirm_envelope.packet_type != common_pb2.PACKET_TYPE_PAIRING_CONFIRM:
            reject = pairing_pb2.PairingReject(
                reason=pairing_pb2.PAIRING_REJECT_REASON_PROTOCOL_MISMATCH,
                detail="expected PairingConfirm from initiator",
            )
            connection.write_envelope(
                build_envelope(common_pb2.PACKET_TYPE_PAIRING_REJECT, reject, sequence_number=4)
            )
            return

        initiator_confirm = decode_payload(confirm_envelope)
        assert isinstance(initiator_confirm, pairing_pb2.PairingConfirm)
        transcript_hash = material.transcript_hash()
        if initiator_confirm.transcript_hash != transcript_hash:
            reject = pairing_pb2.PairingReject(
                reason=pairing_pb2.PAIRING_REJECT_REASON_INTERNAL_ERROR,
                detail="transcript mismatch",
            )
            connection.write_envelope(
                build_envelope(common_pb2.PACKET_TYPE_PAIRING_REJECT, reject, sequence_number=5)
            )
            return

        if not initiator.verify(transcript_hash, initiator_confirm.transcript_signature):
            reject = pairing_pb2.PairingReject(
                reason=pairing_pb2.PAIRING_REJECT_REASON_INTERNAL_ERROR,
                detail="initiator signature invalid",
            )
            connection.write_envelope(
                build_envelope(common_pb2.PACKET_TYPE_PAIRING_REJECT, reject, sequence_number=5)
            )
            return

        desktop_confirm = pairing_pb2.PairingConfirm(
            confirmer=_descriptor_from_identity(self.identity, self.config.protocol_version),
            transcript_hash=transcript_hash,
            transcript_signature=self.identity.sign(transcript_hash),
        )
        connection.write_envelope(
            build_envelope(common_pb2.PACKET_TYPE_PAIRING_CONFIRM, desktop_confirm, sequence_number=6)
        )

        record = TrustedDeviceRecord.from_public_key(
            device_id=initiator.device_id,
            device_name=initiator.device_name,
            public_key_bytes=initiator.public_key_bytes,
            paired_at_epoch_ms=_timestamp_ms(),
        )
        self.trust_store.upsert(record)
        complete = pairing_pb2.PairingComplete(
            trusted_peer=_descriptor_from_identity(self.identity, self.config.protocol_version),
            paired_at=common_pb2.Timestamp(unix_epoch_ms=record.paired_at_epoch_ms),
        )
        connection.write_envelope(
            build_envelope(common_pb2.PACKET_TYPE_PAIRING_COMPLETE, complete, sequence_number=7)
        )
        self.prompts.notify(f"Paired successfully with {initiator.device_name} ({initiator.device_id}).")

    def _handle_session_init(
        self,
        connection: ConnectionIO,
        envelope: common_pb2.Envelope,
        address: str,
    ) -> None:
        init = decode_payload(envelope)
        assert isinstance(init, session_pb2.SessionInit)
        initiator = _peer_from_descriptor(init.initiator)
        record = self.trust_store.get(initiator.device_id)
        if record is None:
            self._write_session_close(
                connection,
                session_pb2.SESSION_CLOSE_REASON_REVOKED,
                f"{initiator.device_name} is not trusted on this desktop",
                sequence_number=2,
            )
            return

        if record.public_key_bytes != initiator.public_key_bytes:
            self._write_session_close(
                connection,
                session_pb2.SESSION_CLOSE_REASON_REVOKED,
                "trusted identity key mismatch",
                sequence_number=2,
            )
            return

        if self.trusted_session_allowed_provider is not None and not self.trusted_session_allowed_provider(
            initiator.device_id
        ):
            self._write_session_close(
                connection,
                session_pb2.SESSION_CLOSE_REASON_NORMAL,
                "desktop user manually disconnected this phone",
                sequence_number=2,
            )
            self.prompts.notify(
                f"[trusted reconnect blocked] {initiator.device_name} ({initiator.device_id}) at {address}; device is manually disconnected."
            )
            return

        if not is_timestamp_fresh(
            init.issued_at.unix_epoch_ms,
            max_skew_ms=int(self.config.pairing_timeout_sec * 1000),
        ):
            self._write_session_close(
                connection,
                session_pb2.SESSION_CLOSE_REASON_TIMEOUT,
                "session init timestamp is outside the allowed skew window",
                sequence_number=2,
            )
            return

        init_payload = build_session_signature_payload(
            label=SESSION_INIT_LABEL,
            descriptor=init.initiator,
            ephemeral_public_key=init.ephemeral_public_key,
            issued_at_ms=init.issued_at.unix_epoch_ms,
        )
        trusted_peer = PeerIdentity(
            device_id=record.device_id,
            device_name=record.device_name,
            public_key_bytes=record.public_key_bytes,
        )
        if not trusted_peer.verify(init_payload, init.identity_signature):
            self._write_session_close(
                connection,
                session_pb2.SESSION_CLOSE_REASON_PROTOCOL_ERROR,
                "initiator session proof signature is invalid",
                sequence_number=2,
            )
            return

        session_token = self.active_session_registry.acquire(initiator.device_id)
        if session_token is None:
            self._write_session_close(
                connection,
                session_pb2.SESSION_CLOSE_REASON_PROTOCOL_ERROR,
                "desktop is already connected to another trusted phone; disconnect it before connecting this phone",
                sequence_number=2,
            )
            self.prompts.notify(
                f"[trusted reconnect blocked] {initiator.device_name} ({initiator.device_id}) at {address}; another phone session is active."
            )
            return

        acceptor = _descriptor_from_identity(self.identity, self.config.protocol_version)
        try:
            ack_issued_at = _timestamp_ms()
            ack_ephemeral = generate_ephemeral_key_pair()
            ack_payload = build_session_signature_payload(
                label=SESSION_ACK_LABEL,
                descriptor=acceptor,
                ephemeral_public_key=ack_ephemeral.public_key_bytes,
                issued_at_ms=ack_issued_at,
            )
            ack = session_pb2.SessionAck(
                acceptor=acceptor,
                ephemeral_public_key=ack_ephemeral.public_key_bytes,
                identity_signature=self.identity.sign(ack_payload),
                issued_at=common_pb2.Timestamp(unix_epoch_ms=ack_issued_at),
            )
            connection.write_envelope(
                build_envelope(common_pb2.PACKET_TYPE_SESSION_ACK, ack, sequence_number=2)
            )
            self.prompts.record_trusted_session_started(
                initiator.device_name,
                initiator.device_id,
                address,
            )
            self.prompts.notify(
                f"Trusted reconnect accepted from {initiator.device_name} ({initiator.device_id}) at {address}."
            )
            keys = derive_directional_keys(
                private_key=ack_ephemeral.private_key,
                peer_public_key_bytes=init.ephemeral_public_key,
                initiator_public_key_bytes=init.ephemeral_public_key,
                acceptor_public_key_bytes=ack_ephemeral.public_key_bytes,
            )
            encrypted = EncryptedEnvelopeChannel(
                stream=connection.stream,
                send_key=keys.server_to_client,
                receive_key=keys.client_to_server,
                max_frame_size=self.config.max_frame_size,
            )
            # Buffered socket streams become unusable after a read timeout.
            # Heartbeats provide liveness, while server shutdown explicitly
            # closes active clients to interrupt this blocking read.
            connection.sock.settimeout(None)
            self._serve_encrypted_transport(encrypted, initiator)
        finally:
            self.prompts.record_trusted_session_closed(initiator.device_id)
            self.prompts.notify(f"[trusted session closed] {initiator.device_name} ({initiator.device_id}).")
            self.active_session_registry.release(session_token)

    def _write_session_close(
        self,
        connection: ConnectionIO,
        reason: int,
        detail: str,
        *,
        sequence_number: int,
    ) -> None:
        close = session_pb2.SessionClose(reason=reason, detail=detail)
        connection.write_envelope(
            build_envelope(common_pb2.PACKET_TYPE_SESSION_CLOSE, close, sequence_number=sequence_number)
        )

    def _serve_encrypted_transport(self, encrypted: EncryptedEnvelopeChannel, peer: PeerIdentity) -> None:
        sequence_number = 100
        sequence_lock = Lock()
        stop_outgoing = Event()
        transport_ready = Event()
        file_receiver = FileReceiver()

        def next_sequence() -> int:
            nonlocal sequence_number
            with sequence_lock:
                current = sequence_number
                sequence_number += 1
                return current

        outgoing_thread = Thread(
            target=self._pump_outgoing_commands,
            args=(encrypted, next_sequence, stop_outgoing, transport_ready, peer),
            name=f"linkable-outgoing-{peer.device_id}",
            daemon=True,
        )
        outgoing_thread.start()
        try:
            while True:
                if self.disconnect_requested_provider is not None and self.disconnect_requested_provider(peer.device_id):
                    self.prompts.notify(f"[trusted disconnect] Closing session for {peer.device_name} ({peer.device_id}).")
                    return
                try:
                    envelope = encrypted.read_envelope()
                except (TimeoutError, socket.timeout):
                    continue
                except EOFError:
                    return

                if envelope.packet_type == common_pb2.PACKET_TYPE_PING:
                    ping = transport_pb2.Ping()
                    ping.ParseFromString(envelope.payload)
                    pong = transport_pb2.Pong(
                        token=ping.token,
                        sent_at=ping.sent_at,
                        received_at=common_pb2.Timestamp(unix_epoch_ms=_timestamp_ms()),
                    )
                    encrypted.write_envelope(
                        build_envelope(common_pb2.PACKET_TYPE_PONG, pong, sequence_number=next_sequence())
                    )
                elif envelope.packet_type == common_pb2.PACKET_TYPE_DEVICE_INFO_REQUEST:
                    response = transport_pb2.DeviceInfoResponse(
                        peer=_descriptor_from_identity(self.identity, self.config.protocol_version),
                        os_version=f"{platform.system()} {platform.release()}",
                        battery_present=False,
                        battery_percent=-1,
                        screen_locked=False,
                    )
                    response.network_interfaces.extend(["lan", f"tcp/{self.config.service_port}"])
                    encrypted.write_envelope(
                        build_envelope(common_pb2.PACKET_TYPE_DEVICE_INFO_RESPONSE, response, sequence_number=next_sequence())
                    )
                elif envelope.packet_type == common_pb2.PACKET_TYPE_CAPABILITIES_REQUEST:
                    response = transport_pb2.CapabilitiesResponse()
                    response.capabilities.extend(
                        [
                            transport_pb2.Capability(name="lan_transport", enabled=True, detail="TCP over LAN"),
                            transport_pb2.Capability(name="encrypted_test_transport", enabled=True, detail="AES-GCM session frames"),
                            transport_pb2.Capability(name="ring_phone", enabled=True, detail="LAN command triggers Android ringtone/vibration"),
                            transport_pb2.Capability(name="call_event_mirroring", enabled=True, detail="Receives Android call-state events over LAN"),
                            transport_pb2.Capability(name="call_metadata_events", enabled=True, detail="Receives Android call source, caller ID, SIM, direction, and route metadata over LAN"),
                            transport_pb2.Capability(name="call_control_commands", enabled=True, detail="Sends Android call accept/reject/hangup commands over LAN"),
                            transport_pb2.Capability(name="dial_from_desktop", enabled=True, detail="Sends Android dial requests over LAN; defaults to SIM slot 1"),
                            transport_pb2.Capability(name="telephony_diagnostics", enabled=True, detail="Requests Android permission, SIM, and call capability status over LAN"),
                            transport_pb2.Capability(name="notification_call_actions", enabled=True, detail="Uses Android notification PendingIntent actions for third-party app calls when exposed"),
                            transport_pb2.Capability(name="desktop_input_controls", enabled=True, detail="Receives Linkable keyboard, pointer, and audio control requests over encrypted LAN"),
                            transport_pb2.Capability(name="bluetooth_optional", enabled=True, detail="Milestone 4 transport does not use Bluetooth"),
                        ]
                    )
                    encrypted.write_envelope(
                        build_envelope(common_pb2.PACKET_TYPE_CAPABILITIES_RESPONSE, response, sequence_number=next_sequence())
                    )
                elif envelope.packet_type == common_pb2.PACKET_TYPE_HEARTBEAT:
                    if not transport_ready.is_set():
                        transport_ready.set()
                        self.outgoing_wakeup.release()
                elif envelope.packet_type == common_pb2.PACKET_TYPE_NOTIFICATION_POSTED:
                    notification = notifications_pb2.NotificationPosted()
                    notification.ParseFromString(envelope.payload)
                    self.prompts.notify(
                        "[notification] "
                        f"{notification.app_name or notification.package_name}: "
                        f"{notification.title} - {notification.body}; "
                        f"{_format_notification_actions(notification)}"
                    )
                    self.prompts.record_notification(notification)
                    if notification.call_like:
                        self.prompts.notify(
                            "[notification call] "
                            f"{notification.app_name or notification.package_name}: "
                            f"{notification.title} - {notification.body}; "
                            f"state={notification.call_state_hint or 'unknown'}; "
                            f"{_format_notification_actions(notification)}"
                        )
                    if self.prompt_notification_replies:
                        reply_actions = [
                            (action.action_id, action.title)
                            for action in notification.actions
                            if action.supports_remote_input
                        ]
                        reply = self.prompts.prompt_notification_reply(
                            app_name=notification.app_name or notification.package_name,
                            title=notification.title,
                            actions=reply_actions,
                        )
                        if reply is not None:
                            action_id, reply_text = reply
                            request = notifications_pb2.NotificationReplyRequest(
                                request_id=token_hex(8),
                                notification_id=notification.notification_id,
                                action_id=action_id,
                                reply_text=reply_text,
                            )
                            encrypted.write_envelope(
                                build_envelope(
                                    common_pb2.PACKET_TYPE_NOTIFICATION_REPLY_REQUEST,
                                    request,
                                    sequence_number=next_sequence(),
                                )
                            )
                elif envelope.packet_type == common_pb2.PACKET_TYPE_NOTIFICATION_REMOVED:
                    removed = notifications_pb2.NotificationRemoved()
                    removed.ParseFromString(envelope.payload)
                    self.prompts.notify(
                        f"[notification removed] {removed.package_name}:{removed.notification_id}"
                    )
                    self.prompts.record_notification_removed(removed.notification_id)
                elif envelope.packet_type == common_pb2.PACKET_TYPE_NOTIFICATION_REPLY_RESULT:
                    result = notifications_pb2.NotificationReplyResult()
                    result.ParseFromString(envelope.payload)
                    status = "sent" if result.success else "failed"
                    self.prompts.notify(
                        f"[notification reply {status}] request={result.request_id} detail={result.detail}"
                    )
                elif envelope.packet_type == common_pb2.PACKET_TYPE_NOTIFICATION_ACTION_RESULT:
                    result = notifications_pb2.NotificationActionResult()
                    result.ParseFromString(envelope.payload)
                    status = "sent" if result.success else "failed"
                    self.prompts.notify(
                        f"[notification action {status}] request={result.request_id} detail={result.detail}"
                    )
                elif envelope.packet_type == common_pb2.PACKET_TYPE_FILE_OFFER:
                    offer = files_pb2.FileOffer()
                    offer.ParseFromString(envelope.payload)
                    result = file_receiver.handle_offer(offer)
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_FILE_TRANSFER_RESULT,
                            result,
                            sequence_number=next_sequence(),
                        )
                    )
                    self.prompts.notify(
                        f"[file receive accepted] {offer.file_name} bytes={offer.size_bytes} save_to={result.saved_path}"
                    )
                elif envelope.packet_type == common_pb2.PACKET_TYPE_FILE_CHUNK:
                    chunk = files_pb2.FileChunk()
                    chunk.ParseFromString(envelope.payload)
                    result = file_receiver.handle_chunk(chunk)
                    if result is not None:
                        encrypted.write_envelope(
                            build_envelope(
                                common_pb2.PACKET_TYPE_FILE_TRANSFER_RESULT,
                                result,
                                sequence_number=next_sequence(),
                            )
                        )
                        status = "ok" if result.success else "failed"
                        self.prompts.notify(
                            f"[file receive {status}] {result.detail} bytes={result.bytes_received} saved_path={result.saved_path}"
                        )
                        self.prompts.record_file_received(result)
                elif envelope.packet_type == common_pb2.PACKET_TYPE_FILE_COMPLETE:
                    complete = files_pb2.FileComplete()
                    complete.ParseFromString(envelope.payload)
                    result = file_receiver.handle_complete(complete)
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_FILE_TRANSFER_RESULT,
                            result,
                            sequence_number=next_sequence(),
                        )
                    )
                    status = "ok" if result.success else "failed"
                    self.prompts.notify(
                        f"[file receive {status}] {result.detail} bytes={result.bytes_received} saved_path={result.saved_path}"
                    )
                    self.prompts.record_file_received(result)
                elif envelope.packet_type == common_pb2.PACKET_TYPE_FILE_TRANSFER_RESULT:
                    result = files_pb2.FileTransferResult()
                    result.ParseFromString(envelope.payload)
                    status = "ok" if result.success else "failed"
                    self.prompts.notify(
                        f"[file transfer {status}] {result.detail} bytes={result.bytes_received} saved_path={result.saved_path}"
                    )
                elif envelope.packet_type == common_pb2.PACKET_TYPE_RING_PHONE_RESULT:
                    result = utilities_pb2.RingPhoneResult()
                    result.ParseFromString(envelope.payload)
                    status = "ok" if result.success else "failed"
                    self.prompts.notify(
                        f"[ring phone {status}] {result.detail} ringing={result.ringing}"
                    )
                elif envelope.packet_type == common_pb2.PACKET_TYPE_CALL_STATE_EVENT:
                    event = calls_pb2.CallStateEvent()
                    event.ParseFromString(envelope.payload)
                    state = calls_pb2.PhoneCallState.Name(event.state)
                    self.prompts.notify(f"[call] state={state} detail={event.detail}")
                elif envelope.packet_type == common_pb2.PACKET_TYPE_CALL_METADATA_EVENT:
                    event = calls_pb2.CallMetadataEvent()
                    event.ParseFromString(envelope.payload)
                    self.prompts.notify(f"[call metadata] {_format_call_metadata(event)}")
                elif envelope.packet_type == common_pb2.PACKET_TYPE_PHONE_CAPABILITY_SNAPSHOT:
                    snapshot = calls_pb2.PhoneCapabilitySnapshot()
                    snapshot.ParseFromString(envelope.payload)
                    self.prompts.notify(f"[phone capabilities] {_format_phone_capabilities(snapshot)}")
                elif envelope.packet_type == common_pb2.PACKET_TYPE_BLUETOOTH_ASSIST_PHONE_STATUS:
                    status = bluetooth_pb2.BluetoothAssistPhoneStatus()
                    status.ParseFromString(envelope.payload)
                    self.prompts.record_bluetooth_status(peer.device_id, status)
                    bond_state = bluetooth_pb2.BluetoothBondState.Name(status.desktop_bond_state)
                    connected_desktop = status.connected_desktop_name or "none"
                    connected_address = status.connected_desktop_address or "none"
                    self.prompts.notify(
                        "[bluetooth status phone] "
                        f"name={status.adapter_name or 'unknown'}; "
                        f"desktop_address={status.desktop_address or 'unknown'}; "
                        f"enabled={status.adapter_enabled}; "
                        f"bond={bond_state}; "
                        f"desktop_connected={status.desktop_connected}; "
                        f"desktop_a2dp_connected={status.desktop_a2dp_connected}; "
                        f"desktop_headset_connected={status.desktop_headset_connected}; "
                        f"connected_desktop={connected_desktop}; "
                        f"connected_desktop_address={connected_address}; "
                        f"route_warning={status.route_warning}; "
                        f"detail={status.detail}"
                    )
                elif envelope.packet_type == common_pb2.PACKET_TYPE_DESKTOP_INPUT_REQUEST:
                    request = input_pb2.DesktopInputRequest()
                    request.ParseFromString(envelope.payload)
                    result = self._input_controller.handle(request)
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_DESKTOP_INPUT_RESULT,
                            result,
                            sequence_number=next_sequence(),
                        )
                    )
                    status = "ok" if result.success else "failed"
                    self.prompts.notify(f"[desktop input {status}] action={request.action_type} detail={result.detail}")
                elif envelope.packet_type == common_pb2.PACKET_TYPE_SHARED_APPS_SNAPSHOT:
                    snapshot = apps_pb2.SharedAppsSnapshot()
                    snapshot.ParseFromString(envelope.payload)
                    self.prompts.record_shared_apps(snapshot)
                    self.prompts.notify(f"[shared apps] received {len(snapshot.apps)} shortcuts")
                elif envelope.packet_type == common_pb2.PACKET_TYPE_SHARED_APP_LAUNCH_RESULT:
                    result = apps_pb2.SharedAppLaunchResult()
                    result.ParseFromString(envelope.payload)
                    self.prompts.record_shared_app_launch_result(result)
                    status = "ok" if result.success else "failed"
                    self.prompts.notify(f"[shared app launch {status}] {result.package_name}: {result.detail}")
                elif envelope.packet_type == common_pb2.PACKET_TYPE_PHONE_FILE_LIST_RESPONSE:
                    response = storage_pb2.PhoneFileListResponse()
                    response.ParseFromString(envelope.payload)
                    self.prompts.record_phone_file_list(response)
                    status = "ok" if response.success else "failed"
                    self.prompts.notify(f"[phone files {status}] {response.path}: {response.detail}")
                elif envelope.packet_type == common_pb2.PACKET_TYPE_PHONE_FILE_PULL_RESULT:
                    result = storage_pb2.PhoneFilePullResult()
                    result.ParseFromString(envelope.payload)
                    self.prompts.record_phone_file_pull_result(result)
                    status = "ok" if result.success else "failed"
                    self.prompts.notify(f"[phone file pull {status}] {result.path}: {result.detail}")
                elif envelope.packet_type == common_pb2.PACKET_TYPE_PHONE_CONTACTS_RESPONSE:
                    response = contacts_pb2.PhoneContactsResponse()
                    response.ParseFromString(envelope.payload)
                    self.prompts.record_contacts(response)
                    status = "ok" if response.success else "failed"
                    self.prompts.notify(f"[contacts {status}] {len(response.contacts)} results: {response.detail}")
                elif envelope.packet_type == common_pb2.PACKET_TYPE_PHONE_RECENT_CONTACTS_RESPONSE:
                    response = contacts_pb2.PhoneRecentContactsResponse()
                    response.ParseFromString(envelope.payload)
                    self.prompts.record_recent_contacts(response)
                    status = "ok" if response.success else "failed"
                    self.prompts.notify(f"[recent contacts {status}] {len(response.contacts)} results: {response.detail}")
                elif envelope.packet_type == common_pb2.PACKET_TYPE_CAMERA_CAPABILITY_RESPONSE:
                    response = camera_pb2.CameraCapabilityResponse()
                    response.ParseFromString(envelope.payload)
                    self.prompts.record_camera_capability(response)
                    status = "ok" if response.success else "failed"
                    self.prompts.notify(f"[camera capabilities {status}] {len(response.cameras)} camera(s): {response.detail}")
                elif envelope.packet_type == common_pb2.PACKET_TYPE_CAMERA_STREAM_START_RESULT:
                    result = camera_pb2.CameraStreamStartResult()
                    result.ParseFromString(envelope.payload)
                    self.prompts.record_camera_start_result(result)
                    status = "ok" if result.success else "failed"
                    route = camera_pb2.CameraRoute.Name(result.route)
                    self.prompts.notify(f"[camera start {status}] route={route} {result.width}x{result.height}@{result.fps}: {result.detail}")
                elif envelope.packet_type == common_pb2.PACKET_TYPE_CAMERA_STREAM_STOP_RESULT:
                    result = camera_pb2.CameraStreamStopResult()
                    result.ParseFromString(envelope.payload)
                    self.prompts.record_camera_stop_result(result)
                    status = "ok" if result.success else "failed"
                    self.prompts.notify(f"[camera stop {status}] {result.detail}")
                elif envelope.packet_type == common_pb2.PACKET_TYPE_CAMERA_STREAM_STATUS_EVENT:
                    event = camera_pb2.CameraStreamStatusEvent()
                    event.ParseFromString(envelope.payload)
                    self.prompts.record_camera_status(event)
                    state = "active" if event.active else "idle"
                    self.prompts.notify(f"[camera status] {state}: {event.detail}; frames={event.frames_sent}")
                elif envelope.packet_type == common_pb2.PACKET_TYPE_CAMERA_FRAME:
                    frame = camera_pb2.CameraFrame()
                    frame.ParseFromString(envelope.payload)
                    self.prompts.record_camera_frame(frame)
                elif envelope.packet_type == common_pb2.PACKET_TYPE_CLIPBOARD_UPDATE:
                    update = clipboard_pb2.ClipboardUpdate()
                    update.ParseFromString(envelope.payload)
                    self.prompts.record_clipboard_update(update)
                    self.prompts.notify(
                        "[clipboard] "
                        f"{update.source_device_name or peer.device_name or 'phone'} copied "
                        f"{update.text_length or len(update.text)} chars"
                    )
                elif envelope.packet_type == common_pb2.PACKET_TYPE_CALL_CONTROL_RESULT:
                    result = calls_pb2.CallControlResult()
                    result.ParseFromString(envelope.payload)
                    status = "ok" if result.success else "failed"
                    action = calls_pb2.CallControlAction.Name(result.action)
                    self.prompts.notify(f"[call control {status}] action={action} detail={result.detail}")
                elif envelope.packet_type == common_pb2.PACKET_TYPE_DIAL_RESULT:
                    result = calls_pb2.DialResult()
                    result.ParseFromString(envelope.payload)
                    status = "ok" if result.success else "failed"
                    sim_detail = (
                        f"SIM {result.requested_sim_slot} resolved to subId {result.resolved_subscription_id}"
                        if result.requested_sim_resolved
                        else f"SIM {result.requested_sim_slot} not resolved; system default used"
                    )
                    self.prompts.notify(f"[dial {status}] {result.detail}; {sim_detail}")
                elif envelope.packet_type == common_pb2.PACKET_TYPE_TELEPHONY_DIAGNOSTICS_RESULT:
                    result = calls_pb2.TelephonyDiagnosticsResult()
                    result.ParseFromString(envelope.payload)
                    self.prompts.notify(f"[telephony diagnostics] {_format_telephony_diagnostics(result)}")
                else:
                    error = errors_pb2.ErrorPayload(
                        code=errors_pb2.ERROR_CODE_INVALID_PACKET_TYPE,
                        message=f"unsupported encrypted packet type: {envelope.packet_type}",
                        fatal=False,
                        related_packet_type=envelope.packet_type,
                        related_sequence_number=envelope.sequence_number,
                    )
                    encrypted.write_envelope(
                        build_envelope(common_pb2.PACKET_TYPE_ERROR, error, sequence_number=next_sequence())
                    )
        except (ConnectionResetError, BrokenPipeError, EOFError, OSError) as exc:
            self.prompts.notify(f"[trusted session dropped] {peer.device_name} ({peer.device_id}): {exc}")
        finally:
            stop_outgoing.set()
            self.outgoing_wakeup.release()
            outgoing_thread.join(timeout=1.0)

    def _pump_outgoing_commands(
        self,
        encrypted: EncryptedEnvelopeChannel,
        next_sequence: Callable[[], int],
        stop_event: Event,
        transport_ready: Event,
        peer: PeerIdentity,
    ) -> None:
        file_sent = False
        while True:
            self.outgoing_wakeup.acquire()
            if stop_event.is_set():
                return
            while not transport_ready.wait(timeout=0.25):
                if stop_event.is_set():
                    return

            file_request = self._next_send_file_request(file_sent=file_sent)
            if file_request is not None:
                try:
                    self.prompts.notify(f"Sending file to {peer.device_name}: {file_request.path}")
                    send_file(
                        encrypted,
                        file_request,
                        sequence_number=0,
                        sequence_provider=next_sequence,
                    )
                    file_sent = True
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[file transfer failed] {exc}")
                    return

            ring_request = self._next_ring_phone_request()
            if ring_request is not None:
                try:
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_RING_PHONE_REQUEST,
                            ring_request,
                            sequence_number=next_sequence(),
                        )
                    )
                    action = utilities_pb2.RingPhoneAction.Name(ring_request.action)
                    self.prompts.notify(f"[ring phone queued] {action} request={ring_request.request_id}")
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[ring phone failed] {exc}")
                    return

            call_request = self._next_call_control_request()
            if call_request is not None:
                try:
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_CALL_CONTROL_REQUEST,
                            call_request,
                            sequence_number=next_sequence(),
                        )
                    )
                    action = calls_pb2.CallControlAction.Name(call_request.action)
                    self.prompts.notify(f"[call control queued] {action} request={call_request.request_id}")
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[call control failed] {exc}")
                    return

            notification_reply_request = self._next_notification_reply_request()
            if notification_reply_request is not None:
                try:
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_NOTIFICATION_REPLY_REQUEST,
                            notification_reply_request,
                            sequence_number=next_sequence(),
                        )
                    )
                    self.prompts.notify(
                        "[notification reply queued] "
                        f"notification={notification_reply_request.notification_id} "
                        f"action={notification_reply_request.action_id} "
                        f"request={notification_reply_request.request_id}"
                    )
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[notification reply failed] {exc}")
                    return

            notification_action_request = self._next_notification_action_request()
            if notification_action_request is not None:
                try:
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_NOTIFICATION_ACTION_REQUEST,
                            notification_action_request,
                            sequence_number=next_sequence(),
                        )
                    )
                    self.prompts.notify(
                        "[notification action queued] "
                        f"notification={notification_action_request.notification_id} "
                        f"action={notification_action_request.action_id} "
                        f"request={notification_action_request.request_id}"
                    )
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[notification action failed] {exc}")
                    return

            dial_request = self._next_dial_request()
            if dial_request is not None:
                try:
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_DIAL_REQUEST,
                            dial_request,
                            sequence_number=next_sequence(),
                        )
                    )
                    self.prompts.notify(
                        f"[dial queued] number={dial_request.phone_number} sim={dial_request.sim_slot}"
                    )
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[dial failed] {exc}")
                    return

            diagnostics_request = self._next_telephony_diagnostics_request()
            if diagnostics_request is not None:
                try:
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_TELEPHONY_DIAGNOSTICS_REQUEST,
                            diagnostics_request,
                            sequence_number=next_sequence(),
                        )
                    )
                    self.prompts.notify(f"[telephony diagnostics queued] request={diagnostics_request.request_id}")
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[telephony diagnostics failed] {exc}")
                    return

            bluetooth_status = self._next_bluetooth_assist_status()
            if bluetooth_status is not None:
                try:
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_BLUETOOTH_ASSIST_DESKTOP_STATUS,
                            bluetooth_status,
                            sequence_number=next_sequence(),
                        )
                    )
                    self.prompts.notify(
                        f"[bluetooth status queued] adapter={bluetooth_status.adapter_alias} "
                        f"{bluetooth_status.adapter_address}"
                    )
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[bluetooth status failed] {exc}")
                    return

            shared_launch = self._next_shared_app_launch_request()
            if shared_launch is not None:
                try:
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_SHARED_APP_LAUNCH_REQUEST,
                            shared_launch,
                            sequence_number=next_sequence(),
                        )
                    )
                    self.prompts.notify(f"[shared app launch queued] {shared_launch.package_name}")
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[shared app launch failed] {exc}")
                    return

            file_list = self._next_phone_file_list_request()
            if file_list is not None:
                try:
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_PHONE_FILE_LIST_REQUEST,
                            file_list,
                            sequence_number=next_sequence(),
                        )
                    )
                    self.prompts.notify(f"[phone file list queued] {file_list.path or '/'}")
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[phone file list failed] {exc}")
                    return

            file_pull = self._next_phone_file_pull_request()
            if file_pull is not None:
                try:
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_PHONE_FILE_PULL_REQUEST,
                            file_pull,
                            sequence_number=next_sequence(),
                        )
                    )
                    self.prompts.notify(f"[phone file pull queued] {file_pull.path}")
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[phone file pull failed] {exc}")
                    return

            contacts_request = self._next_contacts_request()
            if contacts_request is not None:
                try:
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_PHONE_CONTACTS_REQUEST,
                            contacts_request,
                            sequence_number=next_sequence(),
                        )
                    )
                    self.prompts.notify(f"[contacts request queued] {contacts_request.query}")
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[contacts request failed] {exc}")
                    return

            recent_contacts_request = self._next_recent_contacts_request()
            if recent_contacts_request is not None:
                try:
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_PHONE_RECENT_CONTACTS_REQUEST,
                            recent_contacts_request,
                            sequence_number=next_sequence(),
                        )
                    )
                    self.prompts.notify("[recent contacts request queued]")
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[recent contacts request failed] {exc}")
                    return

            camera_capability = self._next_camera_capability_request()
            if camera_capability is not None:
                try:
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_CAMERA_CAPABILITY_REQUEST,
                            camera_capability,
                            sequence_number=next_sequence(),
                        )
                    )
                    self.prompts.notify(f"[camera capability queued] request={camera_capability.request_id}")
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[camera capability failed] {exc}")
                    return

            camera_start = self._next_camera_start_request()
            if camera_start is not None:
                try:
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_CAMERA_STREAM_START_REQUEST,
                            camera_start,
                            sequence_number=next_sequence(),
                        )
                    )
                    route = camera_pb2.CameraRoute.Name(camera_start.route)
                    self.prompts.notify(
                        f"[camera start queued] route={route} port={camera_start.endpoint_port} "
                        f"request={camera_start.request_id}"
                    )
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[camera start failed] {exc}")
                    return

            camera_ack = self._next_camera_ack()
            if camera_ack is not None:
                try:
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_CAMERA_STREAM_ACK,
                            camera_ack,
                            sequence_number=next_sequence(),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[camera ack failed] {exc}")
                    return

            camera_stop = self._next_camera_stop_request()
            if camera_stop is not None:
                try:
                    encrypted.write_envelope(
                        build_envelope(
                            common_pb2.PACKET_TYPE_CAMERA_STREAM_STOP_REQUEST,
                            camera_stop,
                            sequence_number=next_sequence(),
                        )
                    )
                    self.prompts.notify(f"[camera stop queued] request={camera_stop.request_id} reason={camera_stop.reason}")
                except Exception as exc:  # noqa: BLE001
                    self.prompts.notify(f"[camera stop failed] {exc}")
                    return

    def _next_send_file_request(self, *, file_sent: bool) -> SendFileRequest | None:
        if self.send_file_provider is not None:
            return self.send_file_provider()
        if file_sent:
            return None
        return self.send_file_request

    def _next_ring_phone_request(self) -> utilities_pb2.RingPhoneRequest | None:
        if self.ring_phone_request_provider is None:
            return None
        return self.ring_phone_request_provider()

    def _next_call_control_request(self) -> calls_pb2.CallControlRequest | None:
        if self.call_control_request_provider is None:
            return None
        return self.call_control_request_provider()

    def _next_dial_request(self) -> calls_pb2.DialRequest | None:
        if self.dial_request_provider is None:
            return None
        return self.dial_request_provider()

    def _next_telephony_diagnostics_request(self) -> calls_pb2.TelephonyDiagnosticsRequest | None:
        if self.telephony_diagnostics_request_provider is None:
            return None
        return self.telephony_diagnostics_request_provider()

    def _next_notification_reply_request(self) -> notifications_pb2.NotificationReplyRequest | None:
        if self.notification_reply_request_provider is None:
            return None
        return self.notification_reply_request_provider()

    def _next_notification_action_request(self) -> notifications_pb2.NotificationActionRequest | None:
        if self.notification_action_request_provider is None:
            return None
        return self.notification_action_request_provider()

    def _next_bluetooth_assist_status(self) -> bluetooth_pb2.BluetoothAssistDesktopStatus | None:
        if self.bluetooth_assist_provider is None:
            return None
        return self.bluetooth_assist_provider()

    def _next_shared_app_launch_request(self) -> apps_pb2.SharedAppLaunchRequest | None:
        if self.shared_app_launch_request_provider is None:
            return None
        return self.shared_app_launch_request_provider()

    def _next_phone_file_list_request(self) -> storage_pb2.PhoneFileListRequest | None:
        if self.phone_file_list_request_provider is None:
            return None
        return self.phone_file_list_request_provider()

    def _next_phone_file_pull_request(self) -> storage_pb2.PhoneFilePullRequest | None:
        if self.phone_file_pull_request_provider is None:
            return None
        return self.phone_file_pull_request_provider()

    def _next_contacts_request(self) -> contacts_pb2.PhoneContactsRequest | None:
        if self.contacts_request_provider is None:
            return None
        return self.contacts_request_provider()

    def _next_recent_contacts_request(self) -> contacts_pb2.PhoneRecentContactsRequest | None:
        if self.recent_contacts_request_provider is None:
            return None
        return self.recent_contacts_request_provider()

    def _next_camera_capability_request(self) -> camera_pb2.CameraCapabilityRequest | None:
        if self.camera_capability_request_provider is None:
            return None
        return self.camera_capability_request_provider()

    def _next_camera_start_request(self) -> camera_pb2.CameraStreamStartRequest | None:
        if self.camera_start_request_provider is None:
            return None
        return self.camera_start_request_provider()

    def _next_camera_ack(self) -> camera_pb2.CameraStreamAck | None:
        if self.camera_ack_provider is None:
            return None
        return self.camera_ack_provider()

    def _next_camera_stop_request(self) -> camera_pb2.CameraStreamStopRequest | None:
        if self.camera_stop_request_provider is None:
            return None
        return self.camera_stop_request_provider()


class _ThreadedPairingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], handler_cls: type[socketserver.BaseRequestHandler], service: PairingSessionService):
        self.pairing_service = service
        self._active_requests: set[socket.socket] = set()
        self._active_requests_lock = Lock()
        super().__init__(server_address, handler_cls)

    def process_request_thread(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        with self._active_requests_lock:
            self._active_requests.add(request)
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self._active_requests_lock:
                self._active_requests.discard(request)

    def close_active_requests(self) -> None:
        with self._active_requests_lock:
            requests = tuple(self._active_requests)
        for request in requests:
            try:
                request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                request.close()
            except OSError:
                pass


class _PairingRequestHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        service: PairingSessionService = self.server.pairing_service  # type: ignore[attr-defined]
        address = f"{self.client_address[0]}:{self.client_address[1]}"
        self.request.settimeout(90.0)
        try:
            service.handle_connection(ConnectionIO(self.request), address)
        except (ConnectionError, EOFError, TimeoutError, socket.timeout) as error:
            service.prompts.notify(f"[connection closed] {address}: {error}")


@dataclass(slots=True)
class PairingServer:
    config: DiscoveryConfig
    identity: DeviceIdentity
    trust_store: TrustStore
    prompts: ConsolePrompts = field(default_factory=ConsolePrompts)
    send_file_request: SendFileRequest | None = None
    send_file_provider: Callable[[], SendFileRequest | None] | None = None
    ring_phone_request_provider: Callable[[], utilities_pb2.RingPhoneRequest | None] | None = None
    call_control_request_provider: Callable[[], calls_pb2.CallControlRequest | None] | None = None
    dial_request_provider: Callable[[], calls_pb2.DialRequest | None] | None = None
    telephony_diagnostics_request_provider: Callable[[], calls_pb2.TelephonyDiagnosticsRequest | None] | None = None
    notification_reply_request_provider: Callable[[], notifications_pb2.NotificationReplyRequest | None] | None = None
    notification_action_request_provider: Callable[[], notifications_pb2.NotificationActionRequest | None] | None = None
    bluetooth_assist_provider: Callable[[], bluetooth_pb2.BluetoothAssistDesktopStatus | None] | None = None
    shared_app_launch_request_provider: Callable[[], apps_pb2.SharedAppLaunchRequest | None] | None = None
    phone_file_list_request_provider: Callable[[], storage_pb2.PhoneFileListRequest | None] | None = None
    phone_file_pull_request_provider: Callable[[], storage_pb2.PhoneFilePullRequest | None] | None = None
    contacts_request_provider: Callable[[], contacts_pb2.PhoneContactsRequest | None] | None = None
    recent_contacts_request_provider: Callable[[], contacts_pb2.PhoneRecentContactsRequest | None] | None = None
    camera_capability_request_provider: Callable[[], camera_pb2.CameraCapabilityRequest | None] | None = None
    camera_start_request_provider: Callable[[], camera_pb2.CameraStreamStartRequest | None] | None = None
    camera_ack_provider: Callable[[], camera_pb2.CameraStreamAck | None] | None = None
    camera_stop_request_provider: Callable[[], camera_pb2.CameraStreamStopRequest | None] | None = None
    allow_new_pairing_provider: Callable[[], bool] | None = None
    trusted_session_allowed_provider: Callable[[str], bool] | None = None
    disconnect_requested_provider: Callable[[str], bool] | None = None
    active_session_registry: ActiveSessionRegistry = field(default_factory=ActiveSessionRegistry)
    prompt_notification_replies: bool = True
    _server: _ThreadedPairingTCPServer | None = None
    _thread: Thread | None = None
    _outgoing_wakeup: Semaphore = field(default_factory=lambda: Semaphore(0))

    def start(self) -> None:
        if self._server is not None:
            return
        service = PairingSessionService(
            config=self.config,
            identity=self.identity,
            trust_store=self.trust_store,
            prompts=self.prompts,
            send_file_request=self.send_file_request,
            send_file_provider=self.send_file_provider,
            ring_phone_request_provider=self.ring_phone_request_provider,
            call_control_request_provider=self.call_control_request_provider,
            dial_request_provider=self.dial_request_provider,
            telephony_diagnostics_request_provider=self.telephony_diagnostics_request_provider,
            notification_reply_request_provider=self.notification_reply_request_provider,
            notification_action_request_provider=self.notification_action_request_provider,
            bluetooth_assist_provider=self.bluetooth_assist_provider,
            shared_app_launch_request_provider=self.shared_app_launch_request_provider,
            phone_file_list_request_provider=self.phone_file_list_request_provider,
            phone_file_pull_request_provider=self.phone_file_pull_request_provider,
            contacts_request_provider=self.contacts_request_provider,
            recent_contacts_request_provider=self.recent_contacts_request_provider,
            camera_capability_request_provider=self.camera_capability_request_provider,
            camera_start_request_provider=self.camera_start_request_provider,
            camera_ack_provider=self.camera_ack_provider,
            camera_stop_request_provider=self.camera_stop_request_provider,
            allow_new_pairing_provider=self.allow_new_pairing_provider,
            trusted_session_allowed_provider=self.trusted_session_allowed_provider,
            disconnect_requested_provider=self.disconnect_requested_provider,
            active_session_registry=self.active_session_registry,
            prompt_notification_replies=self.prompt_notification_replies,
            outgoing_wakeup=self._outgoing_wakeup,
        )
        self._server = _ThreadedPairingTCPServer(("0.0.0.0", self.config.service_port), _PairingRequestHandler, service)
        self._thread = Thread(target=self._server.serve_forever, name="linkable-pairing-server", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.close_active_requests()
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None

    def wake_outgoing(self) -> None:
        """Wake the active encrypted-session writer for one newly queued command."""

        self._outgoing_wakeup.release()
