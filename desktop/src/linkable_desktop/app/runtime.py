from __future__ import annotations

import re
import hashlib
import shutil
import socket
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from threading import Lock
from uuid import uuid4

from linkable_desktop.app.device_settings import DesktopDeviceSettings, DeviceSettingsStore
from linkable_desktop.app.devices import ActiveDevice, DeviceViewModel, build_device_models
from linkable_desktop.camera.stream_receiver import CameraFrameServer
from linkable_desktop.config import IDENTITY_PATH, TRUST_STORE_PATH, DiscoveryConfig, ensure_state_dir, load_discovery_config
from linkable_desktop.crypto.identity import DeviceIdentity
from linkable_desktop.discovery.mdns_advertiser import DiscoveryAdvertisement
from linkable_desktop.bluetooth.hfp import HfpManager
from linkable_desktop.input.control import InputCommandResult
from linkable_desktop.mirroring.scrcpy import MirrorLaunch, ScrcpyManager, ScrcpyStatus, extract_ipv4_host
from linkable_desktop.pairing.pairing_server import PairingServer
from linkable_desktop.proto import apps_pb2, bluetooth_pb2, calls_pb2, camera_pb2, clipboard_pb2, common_pb2, contacts_pb2, files_pb2, notifications_pb2, storage_pb2, utilities_pb2
from linkable_desktop.app.safe_wifi import DesktopSafeWifiPolicy, DesktopSafeWifiStore
from linkable_desktop.transfer.file_sender import SendFileRequest
from linkable_desktop.trust.trust_store import TrustStore


LogCallback = Callable[[str], None]
DeviceChangedCallback = Callable[[], None]
PairingConfirmCallback = Callable[[str, str, str], bool]
CodePromptCallback = Callable[[], str]
NotificationChangedCallback = Callable[[], None]
ClipboardChangedCallback = Callable[[], None]
CameraFrameCallback = Callable[[bytes], None]
CameraStatusCallback = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class CallHistoryEntry:
    """One call-related event received from the phone for in-app diagnostics/history."""

    event_id: str
    timestamp_ms: int
    source: str
    caller: str
    state: str
    direction: str
    route: str
    sim: str
    detail: str
    raw: str


@dataclass(frozen=True, slots=True)
class CameraStreamHandle:
    """Desktop-side handle for a camera stream requested from the connected phone."""

    token: str
    route: int
    port: int
    request_id: str


class RuntimePrompts:
    """Thread-safe prompt adapter used by the protocol server."""

    def __init__(
        self,
        on_log: LogCallback,
        on_device_connected: Callable[[ActiveDevice], None],
        on_device_closed: Callable[[str], None],
        confirm_pairing: PairingConfirmCallback,
        prompt_code: CodePromptCallback,
        on_notification_posted: Callable[[notifications_pb2.NotificationPosted], None],
        on_notification_removed: Callable[[str], None],
        on_call_status: Callable[[str], None],
        on_shared_apps: Callable[[apps_pb2.SharedAppsSnapshot], None],
        on_shared_app_launch_result: Callable[[apps_pb2.SharedAppLaunchResult], None],
        on_phone_file_list: Callable[[storage_pb2.PhoneFileListResponse], None],
        on_phone_file_pull_result: Callable[[storage_pb2.PhoneFilePullResult], None],
        on_file_received: Callable[[files_pb2.FileTransferResult], None],
        on_contacts: Callable[[contacts_pb2.PhoneContactsResponse], None],
        on_recent_contacts: Callable[[contacts_pb2.PhoneRecentContactsResponse], None],
        on_camera_capability: Callable[[camera_pb2.CameraCapabilityResponse], None],
        on_camera_start_result: Callable[[camera_pb2.CameraStreamStartResult], None],
        on_camera_stop_result: Callable[[camera_pb2.CameraStreamStopResult], None],
        on_camera_status: Callable[[camera_pb2.CameraStreamStatusEvent], None],
        on_camera_frame: Callable[[camera_pb2.CameraFrame], None],
        on_clipboard_update: Callable[[clipboard_pb2.ClipboardUpdate], None],
        on_bluetooth_status: Callable[[str, bluetooth_pb2.BluetoothAssistPhoneStatus], None] = lambda device_id, status: None,
    ) -> None:
        self._on_log = on_log
        self._on_device_connected = on_device_connected
        self._on_device_closed = on_device_closed
        self._confirm_pairing = confirm_pairing
        self._prompt_code = prompt_code
        self._on_notification_posted = on_notification_posted
        self._on_notification_removed = on_notification_removed
        self._on_call_status = on_call_status
        self._on_shared_apps = on_shared_apps
        self._on_shared_app_launch_result = on_shared_app_launch_result
        self._on_phone_file_list = on_phone_file_list
        self._on_phone_file_pull_result = on_phone_file_pull_result
        self._on_file_received = on_file_received
        self._on_contacts = on_contacts
        self._on_recent_contacts = on_recent_contacts
        self._on_camera_capability = on_camera_capability
        self._on_camera_start_result = on_camera_start_result
        self._on_camera_stop_result = on_camera_stop_result
        self._on_camera_status = on_camera_status
        self._on_camera_frame = on_camera_frame
        self._on_clipboard_update = on_clipboard_update
        self._on_bluetooth_status = on_bluetooth_status

    def confirm_pairing(self, phone_name: str, device_id: str, address: str) -> bool:
        return self._confirm_pairing(phone_name, device_id, address)

    def prompt_code(self) -> str:
        return self._prompt_code()

    def notify(self, message: str) -> None:
        self._on_log(message)
        if message.startswith(("[call]", "[call metadata]", "[phone capabilities]", "[telephony diagnostics]")):
            self._on_call_status(message)

    def record_trusted_session_started(self, device_name: str, device_id: str, endpoint: str) -> None:
        self._on_device_connected(
            ActiveDevice(
                device_id=device_id,
                device_name=device_name.strip(),
                endpoint=endpoint.strip(),
                last_seen_epoch=time.time(),
            )
        )

    def record_trusted_session_closed(self, device_id: str) -> None:
        self._on_device_closed(device_id)

    def record_bluetooth_status(self, device_id: str, status: object) -> None:
        if isinstance(status, bluetooth_pb2.BluetoothAssistPhoneStatus):
            self._on_bluetooth_status(device_id, status)

    def record_notification(self, notification: object) -> None:
        if isinstance(notification, notifications_pb2.NotificationPosted):
            self._on_notification_posted(notification)

    def record_notification_removed(self, notification_id: str) -> None:
        self._on_notification_removed(notification_id)

    def record_shared_apps(self, snapshot: object) -> None:
        if isinstance(snapshot, apps_pb2.SharedAppsSnapshot):
            self._on_shared_apps(snapshot)

    def record_shared_app_launch_result(self, result: object) -> None:
        if isinstance(result, apps_pb2.SharedAppLaunchResult):
            self._on_shared_app_launch_result(result)

    def record_phone_file_list(self, response: object) -> None:
        if isinstance(response, storage_pb2.PhoneFileListResponse):
            self._on_phone_file_list(response)

    def record_phone_file_pull_result(self, result: object) -> None:
        if isinstance(result, storage_pb2.PhoneFilePullResult):
            self._on_phone_file_pull_result(result)

    def record_file_received(self, result: object) -> None:
        if isinstance(result, files_pb2.FileTransferResult):
            self._on_file_received(result)

    def record_contacts(self, response: object) -> None:
        if isinstance(response, contacts_pb2.PhoneContactsResponse):
            self._on_contacts(response)

    def record_recent_contacts(self, response: object) -> None:
        if isinstance(response, contacts_pb2.PhoneRecentContactsResponse):
            self._on_recent_contacts(response)

    def record_camera_capability(self, response: object) -> None:
        if isinstance(response, camera_pb2.CameraCapabilityResponse):
            self._on_camera_capability(response)

    def record_camera_start_result(self, result: object) -> None:
        if isinstance(result, camera_pb2.CameraStreamStartResult):
            self._on_camera_start_result(result)

    def record_camera_stop_result(self, result: object) -> None:
        if isinstance(result, camera_pb2.CameraStreamStopResult):
            self._on_camera_stop_result(result)

    def record_camera_status(self, event: object) -> None:
        if isinstance(event, camera_pb2.CameraStreamStatusEvent):
            self._on_camera_status(event)

    def record_camera_frame(self, frame: object) -> None:
        if isinstance(frame, camera_pb2.CameraFrame):
            self._on_camera_frame(frame)

    def record_clipboard_update(self, update: object) -> None:
        if isinstance(update, clipboard_pb2.ClipboardUpdate):
            self._on_clipboard_update(update)

    def prompt_notification_reply(self, app_name: str, title: str, actions: object) -> tuple[str, str] | None:
        return None


@dataclass(slots=True)
class DesktopRuntime:
    """Owns desktop discovery, pairing server, trust store, and live device state."""

    root_dir: Path
    on_log: LogCallback
    on_devices_changed: DeviceChangedCallback
    confirm_pairing: PairingConfirmCallback
    prompt_code: CodePromptCallback
    on_notifications_changed: NotificationChangedCallback = lambda: None
    on_clipboard_changed: ClipboardChangedCallback = lambda: None
    on_shared_apps_changed: DeviceChangedCallback = lambda: None
    on_phone_files_changed: DeviceChangedCallback = lambda: None
    on_contacts_changed: DeviceChangedCallback = lambda: None
    config: DiscoveryConfig | None = None
    identity: DeviceIdentity | None = None
    trust_store: TrustStore | None = None
    advertisement: DiscoveryAdvertisement | None = None
    pairing_server: PairingServer | None = None
    safe_wifi_store: DesktopSafeWifiStore = field(default_factory=DesktopSafeWifiStore)
    scrcpy_manager: ScrcpyManager = field(default_factory=ScrcpyManager)
    hfp_manager: HfpManager = field(default_factory=HfpManager)
    device_settings_store: DeviceSettingsStore = field(default_factory=DeviceSettingsStore)
    _pending_send_files: Queue[SendFileRequest] = field(default_factory=Queue)
    _pending_ring_requests: Queue[utilities_pb2.RingPhoneRequest] = field(default_factory=Queue)
    _pending_call_control_requests: Queue[calls_pb2.CallControlRequest] = field(default_factory=Queue)
    _pending_dial_requests: Queue[calls_pb2.DialRequest] = field(default_factory=Queue)
    _pending_telephony_diagnostics_requests: Queue[calls_pb2.TelephonyDiagnosticsRequest] = field(default_factory=Queue)
    _pending_notification_reply_requests: Queue[notifications_pb2.NotificationReplyRequest] = field(default_factory=Queue)
    _pending_notification_action_requests: Queue[notifications_pb2.NotificationActionRequest] = field(default_factory=Queue)
    _pending_shared_app_launch_requests: Queue[apps_pb2.SharedAppLaunchRequest] = field(default_factory=Queue)
    _pending_phone_file_list_requests: Queue[storage_pb2.PhoneFileListRequest] = field(default_factory=Queue)
    _pending_phone_file_pull_requests: Queue[storage_pb2.PhoneFilePullRequest] = field(default_factory=Queue)
    _pending_contacts_requests: Queue[contacts_pb2.PhoneContactsRequest] = field(default_factory=Queue)
    _pending_recent_contacts_requests: Queue[contacts_pb2.PhoneRecentContactsRequest] = field(default_factory=Queue)
    _pending_bluetooth_status_requests: Queue[bluetooth_pb2.BluetoothAssistDesktopStatus] = field(default_factory=Queue)
    _pending_camera_capability_requests: Queue[camera_pb2.CameraCapabilityRequest] = field(default_factory=Queue)
    _pending_camera_start_requests: Queue[camera_pb2.CameraStreamStartRequest] = field(default_factory=Queue)
    _pending_camera_acks: Queue[camera_pb2.CameraStreamAck] = field(default_factory=Queue)
    _pending_camera_stop_requests: Queue[camera_pb2.CameraStreamStopRequest] = field(default_factory=Queue)
    _active_devices: dict[str, ActiveDevice] = field(default_factory=dict)
    _known_device_endpoints: dict[str, str] = field(default_factory=dict)
    _bluetooth_connected_devices: set[str] = field(default_factory=set)
    _manual_disconnects: set[str] = field(default_factory=set)
    _disconnect_requests: set[str] = field(default_factory=set)
    _notifications: dict[str, notifications_pb2.NotificationPosted] = field(default_factory=dict)
    _notification_history: dict[str, notifications_pb2.NotificationPosted] = field(default_factory=dict)
    _notification_fingerprints: dict[str, str] = field(default_factory=dict)
    _clipboard_updates: dict[str, clipboard_pb2.ClipboardUpdate] = field(default_factory=dict)
    _clipboard_update_order: list[str] = field(default_factory=list)
    _clipboard_fingerprints: set[str] = field(default_factory=set)
    _call_history: list[CallHistoryEntry] = field(default_factory=list)
    _latest_app_call_notification_id: str = ""
    _latest_app_call_label: str = ""
    _latest_app_call_state: str = ""
    _latest_app_call_actions: dict[int, str] = field(default_factory=dict)
    _shared_apps: dict[str, apps_pb2.SharedAppShortcut] = field(default_factory=dict)
    _shared_apps_fingerprint: str = ""
    _phone_file_listing: storage_pb2.PhoneFileListResponse | None = None
    _phone_file_status: str = "Phone file browser has not loaded yet."
    _contact_results: list[contacts_pb2.PhoneContact] = field(default_factory=list)
    _recent_contacts: list[contacts_pb2.PhoneContact] = field(default_factory=list)
    _contacts_status: str = "Connect a phone to search contacts."
    _call_status: str = "No call events received yet."
    _camera_status: str = "Camera sharing is idle."
    _camera_receiver: CameraFrameServer | None = None
    _camera_handle: CameraStreamHandle | None = None
    _camera_frame_callback: CameraFrameCallback | None = None
    _camera_status_callback: CameraStatusCallback | None = None
    _last_mirror_status: str = "Screen mirror has not been checked yet."
    _last_connected_device_id: str = ""
    _new_pairing_allowed_until: float = 0.0
    _lock: Lock = field(default_factory=Lock)

    @property
    def endpoint_summary(self) -> str:
        if self.config is None:
            return "not started"
        addresses = []
        if self.advertisement is not None and self.advertisement.info is not None:
            addresses = [socket.inet_ntoa(address) for address in self.advertisement.info.addresses]
        return f"{', '.join(addresses) or '0.0.0.0'}:{self.config.service_port}"

    @property
    def service_name(self) -> str:
        if self.config is None:
            return "Linkable desktop"
        return self.config.device_name

    @property
    def device_id(self) -> str:
        if self.identity is None:
            return ""
        return self.identity.device_id

    @property
    def is_running(self) -> bool:
        return self.pairing_server is not None

    def start(self) -> None:
        if self.is_running:
            return
        ensure_state_dir()
        self.config = load_discovery_config()
        self.identity = DeviceIdentity.load_or_create(IDENTITY_PATH, device_name=self.config.device_name)
        self.config.device_id = self.identity.device_id
        self.trust_store = TrustStore(TRUST_STORE_PATH)
        prompts = RuntimePrompts(
            self.on_log,
            self._mark_device_connected,
            self._mark_device_closed,
            self.confirm_pairing,
            self.prompt_code,
            self._record_notification,
            self._remove_notification,
            self._set_call_status,
            self._record_shared_apps,
            self._record_shared_app_launch_result,
            self._record_phone_file_list,
            self._record_phone_file_pull_result,
            self._record_file_received,
            self._record_contacts,
            self._record_recent_contacts,
            self._record_camera_capability,
            self._record_camera_start_result,
            self._record_camera_stop_result,
            self._record_camera_status,
            self._record_camera_frame,
            self._record_clipboard_update,
            self._record_bluetooth_status,
        )
        self.advertisement = DiscoveryAdvertisement(self.config)
        self.pairing_server = PairingServer(
            config=self.config,
            identity=self.identity,
            trust_store=self.trust_store,
            prompts=prompts,
            send_file_provider=self._next_send_file_request,
            ring_phone_request_provider=self._next_ring_phone_request,
            call_control_request_provider=self._next_call_control_request,
            dial_request_provider=self._next_dial_request,
            telephony_diagnostics_request_provider=self._next_telephony_diagnostics_request,
            notification_reply_request_provider=self._next_notification_reply_request,
            notification_action_request_provider=self._next_notification_action_request,
            shared_app_launch_request_provider=self._next_shared_app_launch_request,
            phone_file_list_request_provider=self._next_phone_file_list_request,
            phone_file_pull_request_provider=self._next_phone_file_pull_request,
            contacts_request_provider=self._next_contacts_request,
            recent_contacts_request_provider=self._next_recent_contacts_request,
            bluetooth_assist_provider=self._next_bluetooth_status_request,
            camera_capability_request_provider=self._next_camera_capability_request,
            camera_start_request_provider=self._next_camera_start_request,
            camera_ack_provider=self._next_camera_ack,
            camera_stop_request_provider=self._next_camera_stop_request,
            allow_new_pairing_provider=self._new_pairing_allowed,
            trusted_session_allowed_provider=self._trusted_session_allowed,
            disconnect_requested_provider=self._disconnect_requested,
            prompt_notification_replies=False,
        )
        try:
            self.advertisement.start()
            self.pairing_server.start()
        except Exception:
            self.stop()
            raise
        self.on_log(f"Linkable desktop service started on {self.endpoint_summary}.")
        self.on_devices_changed()

    def stop(self) -> None:
        self.stop_camera_stream(reason="desktop service stopped", notify_phone=True)
        self.scrcpy_manager.stop_all()
        if self.pairing_server is not None:
            self.pairing_server.stop()
        if self.advertisement is not None:
            self.advertisement.stop()
        self.pairing_server = None
        self.advertisement = None
        with self._lock:
            self._active_devices.clear()
        self.on_devices_changed()

    def allow_new_pairing(self, seconds: int = 120) -> None:
        self._new_pairing_allowed_until = time.time() + seconds
        self.on_log(f"New phone pairing is allowed for {seconds} seconds.")

    def safe_wifi_policy(self) -> DesktopSafeWifiPolicy:
        return self.safe_wifi_store.load()

    def set_allow_all_wifi(self, allow_all: bool) -> None:
        changed = self.safe_wifi_store.set_allow_all_wifi(allow_all)
        trusted_current = False
        if not allow_all:
            trusted_current = self.safe_wifi_store.trust_current_wifi()
        if changed or trusted_current:
            self.on_log("Desktop Safe Wi-Fi policy updated.")
            self.on_devices_changed()

    def set_safe_wifi_network_enabled(self, ssid: str, enabled: bool) -> None:
        if self.safe_wifi_store.set_network_enabled(ssid, enabled):
            self.on_log(f"Desktop Safe Wi-Fi network {ssid} is {'enabled' if enabled else 'disabled'}.")
            self.on_devices_changed()

    def refresh(self) -> None:
        self.on_log("Refreshing Linkable desktop service.")
        if self.is_running:
            self.stop()
        self.start()

    def list_devices(self) -> list[DeviceViewModel]:
        if self.trust_store is None:
            self.trust_store = TrustStore(TRUST_STORE_PATH)
        with self._lock:
            active = dict(self._active_devices)
            manual = set(self._manual_disconnects)
            bluetooth_connected = set(self._bluetooth_connected_devices)
        return build_device_models(self.trust_store.list_records(), active, manual, bluetooth_connected)

    def notifications(self) -> list[notifications_pb2.NotificationPosted]:
        with self._lock:
            values = list(self._notifications.values())
        return sorted(values, key=lambda item: item.posted_at.unix_epoch_ms, reverse=True)

    def notification_history(self) -> list[notifications_pb2.NotificationPosted]:
        """Return recent phone notifications received by this desktop, including locally removed ones."""

        with self._lock:
            values = list(self._notification_history.values())
        return sorted(values, key=lambda item: item.posted_at.unix_epoch_ms, reverse=True)

    def clipboard_updates(self) -> list[clipboard_pb2.ClipboardUpdate]:
        """Return recent mobile clipboard updates received by this desktop."""

        with self._lock:
            return [
                self._clipboard_updates[update_id]
                for update_id in reversed(self._clipboard_update_order)
                if update_id in self._clipboard_updates
            ]

    def call_history(self) -> list[CallHistoryEntry]:
        """Return recent SIM/app-call events received from the phone."""

        with self._lock:
            return list(self._call_history)

    def shared_apps(self) -> list[apps_pb2.SharedAppShortcut]:
        with self._lock:
            values = list(self._shared_apps.values())
        return sorted(values, key=lambda item: (item.category.lower(), item.label.lower()))

    def launch_shared_app(self, package_name: str) -> MirrorLaunch:
        if self.scrcpy_manager.first_usb_device() is not None:
            launch = self.launch_usb_mirror()
        else:
            launch = self.launch_lan_mirror()
        if not launch.result.ok:
            self.on_log(f"Shared app launch skipped because mirroring failed: {launch.result.compact_output()}")
            return launch
        request = apps_pb2.SharedAppLaunchRequest(
            request_id=f"launch-{time.time_ns()}",
            package_name=package_name,
            requested_at=_timestamp(),
        )
        self._enqueue_outgoing(self._pending_shared_app_launch_requests, request)
        self.on_log(f"Queued shared app launch: {package_name}")
        return launch

    def request_phone_file_list(self, path: str = "") -> None:
        if not self.has_active_phone():
            with self._lock:
                self._phone_file_listing = None
                self._phone_file_status = "Connect a phone before browsing its files."
            self.on_phone_files_changed()
            return
        request = storage_pb2.PhoneFileListRequest(
            request_id=f"list-{time.time_ns()}",
            path=path,
            requested_at=_timestamp(),
        )
        with self._lock:
            self._phone_file_status = f"Requesting phone folder: {path or '/'}"
        self._enqueue_outgoing(self._pending_phone_file_list_requests, request)
        self.on_log(f"Queued phone file listing: {path or '/'}")
        self.on_phone_files_changed()

    def request_phone_file_pull(self, path: str) -> None:
        if not self.has_active_phone():
            with self._lock:
                self._phone_file_status = "Connect a phone before copying files from it."
            self.on_phone_files_changed()
            return
        request = storage_pb2.PhoneFilePullRequest(
            request_id=f"pull-{time.time_ns()}",
            path=path,
            requested_at=_timestamp(),
        )
        with self._lock:
            self._phone_file_status = f"Requesting phone file copy: {path}"
        self._enqueue_outgoing(self._pending_phone_file_pull_requests, request)
        self.on_log(f"Queued phone file pull: {path}")
        self.on_phone_files_changed()

    def phone_file_listing(self) -> storage_pb2.PhoneFileListResponse | None:
        with self._lock:
            return self._phone_file_listing

    def phone_file_status(self) -> str:
        with self._lock:
            return self._phone_file_status

    def request_contacts(self, query: str, limit: int = 20) -> None:
        if not self.has_active_phone():
            with self._lock:
                self._contacts_status = "Connect a phone before searching contacts."
            self.on_contacts_changed()
            return
        request = contacts_pb2.PhoneContactsRequest(
            request_id=f"contacts-{time.time_ns()}",
            query=query,
            limit=limit,
            requested_at=_timestamp(),
        )
        with self._lock:
            self._contacts_status = f"Searching phone contacts for '{query}'."
        self._enqueue_outgoing(self._pending_contacts_requests, request)
        self.on_log(f"Queued contact search: {query}")
        self.on_contacts_changed()

    def request_recent_contacts(self, limit: int = 20) -> None:
        if not self.has_active_phone():
            return
        request = contacts_pb2.PhoneRecentContactsRequest(
            request_id=f"recents-{time.time_ns()}",
            limit=limit,
            requested_at=_timestamp(),
        )
        with self._lock:
            self._contacts_status = "Requesting recent contacts from the phone."
        self._enqueue_outgoing(self._pending_recent_contacts_requests, request)
        self.on_log("Queued recent contacts request.")
        self.on_contacts_changed()

    def contact_results(self) -> list[contacts_pb2.PhoneContact]:
        with self._lock:
            return list(self._contact_results)

    def recent_contacts(self) -> list[contacts_pb2.PhoneContact]:
        with self._lock:
            return list(self._recent_contacts)

    def contacts_status(self) -> str:
        with self._lock:
            return self._contacts_status

    def has_active_phone(self) -> bool:
        with self._lock:
            return bool(self._active_devices)

    def active_phone_bluetooth_connected(self) -> bool:
        with self._lock:
            if self._last_connected_device_id:
                return self._last_connected_device_id in self._bluetooth_connected_devices
            return any(device_id in self._bluetooth_connected_devices for device_id in self._active_devices)

    def queue_send_file(self, path: Path) -> bool:
        try:
            request = SendFileRequest.from_path(str(path))
        except ValueError as exc:
            self.on_log(str(exc))
            return False
        self._enqueue_outgoing(self._pending_send_files, request)
        with self._lock:
            self._phone_file_status = f"Queued {request.path.name} for phone transfer."
        self.on_log(f"Queued file for phone transfer: {request.path}")
        self.on_phone_files_changed()
        return True

    def queue_ring_phone(self, start: bool = True) -> None:
        action = utilities_pb2.RING_PHONE_ACTION_START if start else utilities_pb2.RING_PHONE_ACTION_STOP
        request = utilities_pb2.RingPhoneRequest(
            request_id=f"ring-{time.time_ns()}",
            action=action,
            duration_ms=30_000,
            requested_at=_timestamp(),
        )
        self._enqueue_outgoing(self._pending_ring_requests, request)
        self.on_log("Queued ring-phone request." if start else "Queued stop-ring request.")

    def queue_call_control(self, action: int) -> None:
        if self._queue_app_call_action_if_available(action):
            return
        request = calls_pb2.CallControlRequest(
            request_id=f"call-{time.time_ns()}",
            action=action,
            requested_at=_timestamp(),
        )
        self._enqueue_outgoing(self._pending_call_control_requests, request)
        self.on_log(f"Queued call-control request: {calls_pb2.CallControlAction.Name(action)}.")

    def queue_dial(self, phone_number: str, sim_slot: int) -> bool:
        if not phone_number.strip():
            self.on_log("Dial request ignored: phone number is empty.")
            return False
        request = calls_pb2.DialRequest(
            request_id=f"dial-{time.time_ns()}",
            phone_number=phone_number.strip(),
            sim_slot=max(1, sim_slot),
            direct_call=True,
            requested_at=_timestamp(),
        )
        self._enqueue_outgoing(self._pending_dial_requests, request)
        self.on_log(f"Queued dial request: {request.phone_number} using SIM {request.sim_slot}.")
        return True

    def queue_telephony_diagnostics(self) -> None:
        request = calls_pb2.TelephonyDiagnosticsRequest(
            request_id=f"tel-{time.time_ns()}",
            requested_at=_timestamp(),
        )
        self._enqueue_outgoing(self._pending_telephony_diagnostics_requests, request)
        self.on_log("Queued telephony diagnostics refresh.")

    def queue_notification_reply(self, notification_id: str, action_id: str, reply_text: str) -> bool:
        if not reply_text.strip():
            return False
        request = notifications_pb2.NotificationReplyRequest(
            request_id=f"reply-{time.time_ns()}",
            notification_id=notification_id,
            action_id=action_id,
            reply_text=reply_text.strip(),
        )
        self._enqueue_outgoing(self._pending_notification_reply_requests, request)
        self.on_log(f"Queued notification reply for {notification_id}.")
        return True

    def queue_notification_action(self, notification_id: str, action_id: str) -> None:
        request = notifications_pb2.NotificationActionRequest(
            request_id=f"notify-action-{time.time_ns()}",
            notification_id=notification_id,
            action_id=action_id,
            requested_at=_timestamp(),
        )
        self._enqueue_outgoing(self._pending_notification_action_requests, request)
        self.on_log(f"Queued notification action for {notification_id}.")

    def _queue_app_call_action_if_available(self, action: int) -> bool:
        notification_id, action_id, label = self._app_call_action_for(action)
        if not notification_id:
            return False
        action_name = calls_pb2.CallControlAction.Name(action)
        if not action_id:
            self.on_log(
                f"App-call {action_name} requested for {label or 'app call'}, "
                "but the phone did not expose a matching notification action; falling back to SIM call-control."
            )
            return False
        request = notifications_pb2.NotificationActionRequest(
            request_id=f"notify-action-{time.time_ns()}",
            notification_id=notification_id,
            action_id=action_id,
            requested_at=_timestamp(),
        )
        self._enqueue_outgoing(self._pending_notification_action_requests, request)
        self.on_log(
            f"Queued app-call action: {action_name} for {label or 'app call'} "
            f"notification={notification_id} action={action_id}."
        )
        return True

    def _app_call_action_for(self, action: int) -> tuple[str, str, str]:
        candidates_by_action = {
            calls_pb2.CALL_CONTROL_ACTION_ACCEPT: (
                notifications_pb2.NOTIFICATION_ACTION_SEMANTIC_ANSWER_CALL,
            ),
            calls_pb2.CALL_CONTROL_ACTION_REJECT: (
                notifications_pb2.NOTIFICATION_ACTION_SEMANTIC_DECLINE_CALL,
                notifications_pb2.NOTIFICATION_ACTION_SEMANTIC_HANG_UP_CALL,
            ),
            calls_pb2.CALL_CONTROL_ACTION_HANGUP: (
                notifications_pb2.NOTIFICATION_ACTION_SEMANTIC_HANG_UP_CALL,
                notifications_pb2.NOTIFICATION_ACTION_SEMANTIC_DECLINE_CALL,
            ),
        }
        candidates = candidates_by_action.get(action, ())
        with self._lock:
            notification_id = self._latest_app_call_notification_id
            label = self._latest_app_call_label
            actions = dict(self._latest_app_call_actions)
        if not notification_id:
            return "", "", ""
        for semantic in candidates:
            action_id = actions.get(semantic)
            if action_id:
                return notification_id, action_id, label
        return notification_id, "", label

    def call_status(self) -> str:
        with self._lock:
            return self._call_status

    def mirror_status(self) -> ScrcpyStatus:
        status = self.scrcpy_manager.status()
        self._last_mirror_status = status.format()
        return status

    def launch_usb_mirror(self) -> MirrorLaunch:
        launch = self.scrcpy_manager.launch_usb_mirror()
        self._record_mirror_launch(launch)
        return launch

    def launch_lan_mirror(self) -> MirrorLaunch:
        host = self._active_phone_host()
        if not host:
            self.on_log("LAN mirror failed: no connected phone IP is known yet.")
            launch = MirrorLaunch(
                result=self.scrcpy_manager.connect_lan_adb(""),
            )
            self._record_mirror_launch(launch)
            return launch
        prepare = self.scrcpy_manager.enable_adb_tcpip()
        if prepare.ok:
            self.on_log(f"ADB TCP/IP prepared: {prepare.compact_output()}")
            time.sleep(1.0)
        else:
            self.on_log(f"ADB TCP/IP preparation did not complete: {prepare.compact_output()}")
        launch = self.scrcpy_manager.launch_lan_mirror(host)
        self._record_mirror_launch(launch)
        return launch

    def camera_status(self) -> str:
        with self._lock:
            return self._camera_status

    def camera_route_summary(self, route: int) -> str:
        """Return user-facing diagnostics for the selected camera transport."""

        if route == camera_pb2.CAMERA_ROUTE_USB:
            adb = self.scrcpy_manager.adb_path()
            device = self.scrcpy_manager.first_usb_device() if adb else None
            if adb and device is not None:
                return f"Camera route: USB via ADB reverse ({device.serial}). PC output: Linkable Camera."
            if not adb:
                return "Camera route: USB selected, but adb is missing. LAN fallback will be used if the phone is connected."
            return "Camera route: USB selected, but no authorized USB ADB phone is visible. LAN fallback will be used if connected."
        host = self._active_phone_host()
        endpoint = host or "active encrypted session"
        return f"Camera route: LAN over Linkable session ({endpoint}). PC output: Linkable Camera."

    def request_camera_capabilities(self) -> None:
        if not self.has_active_phone():
            with self._lock:
                self._camera_status = "Connect a phone before requesting camera capabilities."
            self.on_devices_changed()
            return
        request = camera_pb2.CameraCapabilityRequest(
            request_id=f"cam-cap-{time.time_ns()}",
            requested_at=_timestamp(),
        )
        self._enqueue_outgoing(self._pending_camera_capability_requests, request)
        with self._lock:
            self._camera_status = "Requesting phone camera capabilities."
        self.on_log("[camera capability queued] phone camera capability request queued")
        self.on_devices_changed()

    def start_camera_stream(
        self,
        *,
        route: int,
        facing: int,
        on_frame: CameraFrameCallback,
        on_status: CameraStatusCallback,
        width: int = 640,
        height: int = 480,
        fps: int = 12,
    ) -> CameraStreamHandle | None:
        if not self.has_active_phone():
            message = "Connect a phone before starting camera sharing."
            on_status(message)
            with self._lock:
                self._camera_status = message
            self.on_devices_changed()
            return None
        self.stop_camera_stream(reason="replaced by a new camera request", notify_phone=True)
        token = uuid4().hex
        actual_route = route
        receiver: CameraFrameServer | None = None
        media_port = 0
        endpoint_host = ""
        route_detail = "LAN"
        if actual_route == camera_pb2.CAMERA_ROUTE_USB:
            receiver = CameraFrameServer(
                token=token,
                on_frame=on_frame,
                on_status=lambda message: self._set_camera_status_from_receiver(message, on_status),
            )
            state = receiver.start()
            media_port = state.port
            usb_ok, detail = self._prepare_camera_usb_reverse(state.port)
            if not usb_ok:
                receiver.stop()
                receiver = None
                if self.has_active_phone():
                    actual_route = camera_pb2.CAMERA_ROUTE_LAN
                    route_detail = "encrypted LAN fallback"
                    on_status(f"USB camera route unavailable: {detail}. Falling back to LAN camera transport.")
                    self.on_log(f"[camera usb fallback] {detail}; using encrypted LAN camera transport")
                else:
                    message = f"USB camera route unavailable: {detail}"
                    on_status(message)
                    with self._lock:
                        self._camera_status = message
                    self.on_devices_changed()
                    return None
            else:
                endpoint_host = "127.0.0.1"
                route_detail = "USB"
                self.on_log(f"[camera usb reverse] {detail}")
                on_status(f"USB camera route active: {detail}")
        if actual_route != camera_pb2.CAMERA_ROUTE_USB:
            media_port = 0
            route_detail = "encrypted LAN"
            if route == camera_pb2.CAMERA_ROUTE_USB:
                route_detail = "encrypted LAN fallback"
            on_status("Camera stream will use the encrypted Linkable LAN session.")
        request = camera_pb2.CameraStreamStartRequest(
            request_id=f"cam-start-{time.time_ns()}",
            route=actual_route,
            facing=facing,
            codec=camera_pb2.CAMERA_CODEC_MJPEG,
            width=max(160, int(width)),
            height=max(120, int(height)),
            fps=max(1, min(30, int(fps))),
            jpeg_quality=58,
            endpoint_host=endpoint_host,
            endpoint_port=media_port,
            session_token=token,
            ack_interval_ms=2_000,
            ack_timeout_ms=7_000,
            requested_at=_timestamp(),
        )
        handle = CameraStreamHandle(
            token=token,
            route=actual_route,
            port=media_port,
            request_id=request.request_id,
        )
        with self._lock:
            self._camera_receiver = receiver
            self._camera_handle = handle
            self._camera_frame_callback = on_frame
            self._camera_status_callback = on_status
            self._camera_status = f"Camera start requested over {route_detail}; waiting for phone confirmation."
        self._enqueue_outgoing(self._pending_camera_start_requests, request)
        self.on_log(
            f"[camera start queued] route={route_detail} port={media_port} "
            f"size={request.width}x{request.height} fps={request.fps}"
        )
        self.on_devices_changed()
        return handle

    def ack_camera_stream(self, token: str) -> None:
        if not token:
            return
        self._enqueue_outgoing(
            self._pending_camera_acks,
            camera_pb2.CameraStreamAck(
                request_id=f"cam-ack-{time.time_ns()}",
                session_token=token,
                sent_at=_timestamp(),
            ),
        )

    def stop_camera_stream(self, *, reason: str = "desktop popup closed", notify_phone: bool = True) -> None:
        with self._lock:
            handle = self._camera_handle
            receiver = self._camera_receiver
            self._camera_handle = None
            self._camera_receiver = None
            self._camera_status_callback = None
            self._camera_status = "Camera sharing stopped."
        if notify_phone and handle is not None:
            self._enqueue_outgoing(
                self._pending_camera_stop_requests,
                camera_pb2.CameraStreamStopRequest(
                    request_id=f"cam-stop-{time.time_ns()}",
                    session_token=handle.token,
                    reason=reason,
                    requested_at=_timestamp(),
                ),
            )
        if receiver is not None:
            receiver.stop()
        with self._lock:
            if self._camera_handle is None:
                self._camera_frame_callback = None
        if handle is not None and handle.route == camera_pb2.CAMERA_ROUTE_USB:
            self._remove_camera_usb_reverse(handle.port)
        self.on_devices_changed()

    def set_speaker_volume(self, percent: int) -> InputCommandResult:
        result = _set_audio_volume(percent, source=False)
        self.on_log(f"Speaker volume {'set' if result.success else 'failed'}: {result.detail}")
        return result

    def set_microphone_volume(self, percent: int) -> InputCommandResult:
        result = _set_audio_volume(percent, source=True)
        self.on_log(f"Microphone volume {'set' if result.success else 'failed'}: {result.detail}")
        return result

    def received_files_dir(self) -> Path:
        return Path.home() / "Downloads" / "Linkable"

    def received_files(self) -> list[Path]:
        root = self.received_files_dir()
        if not root.exists():
            return []
        return sorted((path for path in root.iterdir() if path.is_file()), key=lambda path: path.stat().st_mtime, reverse=True)

    def disconnect_device(self, device_id: str) -> None:
        with self._lock:
            self._disconnect_requests.add(device_id)
            self._active_devices.pop(device_id, None)
            self._known_device_endpoints.pop(device_id, None)
            self._bluetooth_connected_devices.discard(device_id)
            if self._last_connected_device_id == device_id:
                self._last_connected_device_id = ""
        self.on_log(f"Device {device_id} was disconnected. Trusted auto-reconnect remains allowed.")
        self.on_devices_changed()

    def allow_reconnect(self, device_id: str) -> None:
        with self._lock:
            self._manual_disconnects.discard(device_id)
            self._disconnect_requests.discard(device_id)
        self.on_log(f"Device {device_id} is allowed to reconnect automatically again.")
        self.on_devices_changed()

    def unpair_device(self, device_id: str) -> bool:
        with self._lock:
            self._manual_disconnects.add(device_id)
            self._disconnect_requests.add(device_id)
            self._active_devices.pop(device_id, None)
            self._bluetooth_connected_devices.discard(device_id)
            if self._last_connected_device_id == device_id:
                self._last_connected_device_id = ""
        self.on_log(f"Unpaired device {device_id}. Trust is kept, but automatic reconnect is paused until Reconnect is clicked.")
        self.on_devices_changed()
        return True

    def forget_device(self, device_id: str) -> bool:
        if self.trust_store is None:
            self.trust_store = TrustStore(TRUST_STORE_PATH)
        with self._lock:
            self._manual_disconnects.discard(device_id)
            self._disconnect_requests.discard(device_id)
            self._active_devices.pop(device_id, None)
            self._known_device_endpoints.pop(device_id, None)
            self._bluetooth_connected_devices.discard(device_id)
            if self._last_connected_device_id == device_id:
                self._last_connected_device_id = ""
            self._new_pairing_allowed_until = time.time() + 120
        removed = self.trust_store.remove(device_id)
        settings_removed = self.device_settings_store.remove(device_id)
        self.on_log(
            f"Forgot device {device_id}. Cleared trust/settings; future contact will be treated as a new phone."
            if removed or settings_removed
            else f"Device {device_id} had no stored trust/settings."
        )
        self.on_devices_changed()
        return removed or settings_removed

    def device_settings(self, device_id: str) -> DesktopDeviceSettings:
        return self.device_settings_store.get(device_id)

    def set_device_setting(self, device_id: str, key: str, value: bool) -> DesktopDeviceSettings:
        settings = self.device_settings_store.set_value(device_id, key, value)
        self.on_log(f"Device setting saved for {device_id}: {key}={value}.")
        self.on_devices_changed()
        return settings

    def _new_pairing_allowed(self) -> bool:
        if not self.safe_wifi_store.is_current_wifi_allowed():
            self.on_log("New pairing blocked because desktop Safe Wi-Fi is enabled and this Wi-Fi is not allowed.")
            return False
        if self.trust_store is None:
            return True
        if not self.trust_store.list_records():
            return True
        return time.time() < self._new_pairing_allowed_until

    def _trusted_session_allowed(self, device_id: str) -> bool:
        with self._lock:
            manually_disconnected = device_id in self._manual_disconnects
        if manually_disconnected:
            return False
        if not self.safe_wifi_store.is_current_wifi_allowed():
            self.on_log("Trusted reconnect blocked because desktop Safe Wi-Fi is enabled and this Wi-Fi is not allowed.")
            return False
        return True

    def _disconnect_requested(self, device_id: str) -> bool:
        with self._lock:
            return device_id in self._manual_disconnects or device_id in self._disconnect_requests

    def _mark_device_connected(self, device: ActiveDevice) -> None:
        changed = False
        should_request_bluetooth_status = False
        with self._lock:
            previous = self._active_devices.get(device.device_id)
            endpoint = device.endpoint
            if endpoint == "connected" and previous is not None:
                endpoint = previous.endpoint
            if endpoint == "connected":
                endpoint = self._known_device_endpoints.get(device.device_id, endpoint)
            if extract_ipv4_host(endpoint):
                self._known_device_endpoints[device.device_id] = endpoint
                self._last_connected_device_id = device.device_id
            changed = previous is None or previous.device_name != device.device_name or previous.endpoint != endpoint
            should_request_bluetooth_status = changed and extract_ipv4_host(endpoint) != ""
            self._active_devices[device.device_id] = ActiveDevice(
                device_id=device.device_id,
                device_name=device.device_name,
                endpoint=endpoint,
                last_seen_epoch=device.last_seen_epoch,
            )
            if changed:
                self._contacts_status = "Phone connected. Preparing recent contacts."
        if changed:
            self.request_recent_contacts(limit=20)
            self.on_devices_changed()
        if should_request_bluetooth_status:
            self._queue_bluetooth_status_request(expected_phone_name=device.device_name)

    def _mark_device_closed(self, device_id: str) -> None:
        with self._lock:
            self._active_devices.pop(device_id, None)
            self._disconnect_requests.discard(device_id)
            self._contacts_status = "Connect a phone to search contacts."
        self.on_devices_changed()
        self.on_contacts_changed()

    def _queue_bluetooth_status_request(self, *, expected_phone_name: str = "") -> None:
        try:
            status = self.hfp_manager.status()
            adapter = status.adapter
            request = bluetooth_pb2.BluetoothAssistDesktopStatus(
                request_id=f"bt-{time.time_ns()}",
                adapter_available=adapter.available,
                powered=adapter.powered,
                pairable=adapter.pairable,
                discoverable=adapter.discoverable,
                adapter_address=adapter.address,
                adapter_alias=adapter.alias,
                hfp_audio_ready=status.hfp_audio_ready,
                auto_start_bonding=False,
                detail=status.format(),
                generated_at=_timestamp(),
                expected_phone_name=expected_phone_name,
            )
        except Exception as exc:  # noqa: BLE001
            request = bluetooth_pb2.BluetoothAssistDesktopStatus(
                request_id=f"bt-{time.time_ns()}",
                adapter_available=False,
                detail=f"desktop Bluetooth status unavailable: {exc}",
                generated_at=_timestamp(),
                expected_phone_name=expected_phone_name,
            )
        self._enqueue_outgoing(self._pending_bluetooth_status_requests, request)

    def _record_bluetooth_status(self, device_id: str, status: bluetooth_pb2.BluetoothAssistPhoneStatus) -> None:
        changed = False
        with self._lock:
            if status.desktop_connected:
                changed = device_id not in self._bluetooth_connected_devices
                self._bluetooth_connected_devices.add(device_id)
            else:
                changed = device_id in self._bluetooth_connected_devices
                self._bluetooth_connected_devices.discard(device_id)
        if changed:
            self.on_devices_changed()

    def _record_notification(self, notification: notifications_pb2.NotificationPosted) -> None:
        fingerprint = _notification_fingerprint(notification)
        history_changed = False
        with self._lock:
            if self._notification_fingerprints.get(notification.notification_id) == fingerprint:
                return
            self._notifications[notification.notification_id] = notification
            self._notification_history[notification.notification_id] = notification
            self._notification_fingerprints[notification.notification_id] = fingerprint
            self._trim_notification_history_locked()
            if notification.call_like:
                self._record_app_call_actions_locked(notification)
                history_changed = self._append_call_history_locked(_call_entry_from_notification(notification))
        self.on_notifications_changed()
        if history_changed:
            self.on_devices_changed()

    def _remove_notification(self, notification_id: str) -> None:
        changed = False
        history_changed = False
        with self._lock:
            notification = self._notifications.get(notification_id)
            if notification is not None and notification.call_like:
                self._notifications.pop(notification_id, None)
                changed = True
                self._notification_fingerprints.pop(notification_id, None)
                self._clear_app_call_if_current_locked(notification_id)
                history_changed = self._append_call_history_locked(
                    _call_entry_from_notification(notification, state_override="ended")
                )
        if changed:
            self.on_notifications_changed()
        if history_changed:
            self.on_devices_changed()

    def _record_clipboard_update(self, update: clipboard_pb2.ClipboardUpdate) -> None:
        if not update.text:
            return
        text = update.text[:8192]
        fingerprint = hashlib.sha256(
            f"{update.source_device_id}:{text}".encode("utf-8", errors="replace")
        ).hexdigest()
        update_id = update.update_id or fingerprint
        with self._lock:
            if update_id in self._clipboard_updates or fingerprint in self._clipboard_fingerprints:
                return
            self._clipboard_updates[update_id] = update
            self._clipboard_update_order.append(update_id)
            self._clipboard_fingerprints.add(fingerprint)
            while len(self._clipboard_update_order) > 30:
                old_id = self._clipboard_update_order.pop(0)
                old_update = self._clipboard_updates.pop(old_id, None)
                if old_update is not None:
                    old_text = old_update.text[:8192]
                    old_fingerprint = hashlib.sha256(
                        f"{old_update.source_device_id}:{old_text}".encode("utf-8", errors="replace")
                    ).hexdigest()
                    self._clipboard_fingerprints.discard(old_fingerprint)
        self.on_clipboard_changed()

    def _record_shared_apps(self, snapshot: apps_pb2.SharedAppsSnapshot) -> None:
        fingerprint = _shared_apps_fingerprint(snapshot.apps)
        with self._lock:
            if self._shared_apps_fingerprint == fingerprint:
                return
            self._shared_apps = {app.package_name: app for app in snapshot.apps}
            self._shared_apps_fingerprint = fingerprint
        self.on_shared_apps_changed()

    def _record_shared_app_launch_result(self, result: apps_pb2.SharedAppLaunchResult) -> None:
        status = "started" if result.success else "failed"
        self.on_log(f"Shared app launch {status}: {result.package_name}; {result.detail}")

    def _record_phone_file_list(self, response: storage_pb2.PhoneFileListResponse) -> None:
        with self._lock:
            self._phone_file_listing = response
            self._phone_file_status = response.detail
        self.on_phone_files_changed()

    def _record_phone_file_pull_result(self, result: storage_pb2.PhoneFilePullResult) -> None:
        with self._lock:
            self._phone_file_status = result.detail
        self.on_phone_files_changed()

    def _record_file_received(self, result: files_pb2.FileTransferResult) -> None:
        if not result.saved_path:
            return
        with self._lock:
            self._phone_file_status = result.detail
        self.on_phone_files_changed()

    def _record_contacts(self, response: contacts_pb2.PhoneContactsResponse) -> None:
        with self._lock:
            self._contact_results = list(response.contacts)
            self._contacts_status = response.detail
        self.on_contacts_changed()

    def _record_recent_contacts(self, response: contacts_pb2.PhoneRecentContactsResponse) -> None:
        with self._lock:
            self._recent_contacts = list(response.contacts)
            self._contacts_status = response.detail
        self.on_contacts_changed()

    def _record_camera_capability(self, response: camera_pb2.CameraCapabilityResponse) -> None:
        camera_count = len(response.cameras)
        with self._lock:
            self._camera_status = response.detail or f"Phone reported {camera_count} camera(s)."
        self.on_log(f"[camera capabilities {'ok' if response.success else 'failed'}] {self._camera_status}")
        self.on_devices_changed()

    def _record_camera_start_result(self, result: camera_pb2.CameraStreamStartResult) -> None:
        status = "ok" if result.success else "failed"
        with self._lock:
            self._camera_status = result.detail
            handle = self._camera_handle
            receiver = self._camera_receiver
            should_stop_receiver = not result.success and handle is not None and handle.token == result.session_token
        if should_stop_receiver and receiver is not None:
            receiver.stop()
            with self._lock:
                self._camera_receiver = None
                self._camera_handle = None
                self._camera_frame_callback = None
                self._camera_status_callback = None
        elif should_stop_receiver:
            with self._lock:
                self._camera_handle = None
                self._camera_frame_callback = None
                self._camera_status_callback = None
        self.on_log(f"[camera start {status}] {result.detail}")
        self.on_devices_changed()

    def _record_camera_stop_result(self, result: camera_pb2.CameraStreamStopResult) -> None:
        status = "ok" if result.success else "failed"
        with self._lock:
            self._camera_status = result.detail
        self.on_log(f"[camera stop {status}] {result.detail}")
        self.on_devices_changed()

    def _record_camera_status(self, event: camera_pb2.CameraStreamStatusEvent) -> None:
        state = "active" if event.active else "idle"
        with self._lock:
            handle = self._camera_handle
            if handle is None or event.session_token != handle.token:
                return
            self._camera_status = f"{state}: {event.detail}; frames={event.frames_sent}"
            callback = self._camera_status_callback
        self.on_log(f"[camera status] {self._camera_status}")
        if callback is not None:
            callback(self._camera_status)
        self.on_devices_changed()

    def _record_camera_frame(self, frame: camera_pb2.CameraFrame) -> None:
        with self._lock:
            handle = self._camera_handle
            callback = self._camera_frame_callback
        if handle is None or callback is None or frame.session_token != handle.token:
            return
        callback(bytes(frame.frame_bytes))

    def _set_camera_status_from_receiver(self, message: str, callback: CameraStatusCallback) -> None:
        with self._lock:
            self._camera_status = message
        self.on_log(f"[camera receiver] {message}")
        callback(message)
        self.on_devices_changed()

    def _set_call_status(self, message: str) -> None:
        changed = False
        history_changed = False
        entry = _call_entry_from_status(message)
        with self._lock:
            changed = self._call_status != message
            self._call_status = message
            if changed and entry is not None:
                history_changed = self._append_call_history_locked(entry)
        if changed:
            self.on_devices_changed()
            self.on_notifications_changed()
        elif history_changed:
            self.on_notifications_changed()

    def _append_call_history_locked(self, entry: CallHistoryEntry) -> bool:
        fingerprint = _call_history_fingerprint(entry)
        for existing in self._call_history[:12]:
            if _call_history_fingerprint(existing) == fingerprint:
                return False
        self._call_history.insert(0, entry)
        del self._call_history[160:]
        return True

    def _record_app_call_actions_locked(self, notification: notifications_pb2.NotificationPosted) -> None:
        call_actions = {
            action.semantic: action.action_id
            for action in notification.actions
            if action.supports_plain_intent
            and action.semantic
            in {
                notifications_pb2.NOTIFICATION_ACTION_SEMANTIC_ANSWER_CALL,
                notifications_pb2.NOTIFICATION_ACTION_SEMANTIC_DECLINE_CALL,
                notifications_pb2.NOTIFICATION_ACTION_SEMANTIC_HANG_UP_CALL,
            }
        }
        if not call_actions:
            return
        self._latest_app_call_notification_id = notification.notification_id
        self._latest_app_call_label = notification.app_name or notification.package_name
        self._latest_app_call_state = notification.call_state_hint
        self._latest_app_call_actions = call_actions

    def _clear_app_call_if_current_locked(self, notification_id: str) -> None:
        if notification_id != self._latest_app_call_notification_id:
            return
        self._latest_app_call_notification_id = ""
        self._latest_app_call_label = ""
        self._latest_app_call_state = ""
        self._latest_app_call_actions = {}

    def _trim_notification_history_locked(self) -> None:
        if len(self._notification_history) <= 200:
            return
        ordered = sorted(
            self._notification_history.items(),
            key=lambda item: item[1].posted_at.unix_epoch_ms,
            reverse=True,
        )
        self._notification_history = dict(ordered[:200])

    def _enqueue_outgoing(self, queue: Queue, request: object) -> None:
        """Queue one desktop command and wake the encrypted writer immediately."""

        queue.put(request)
        server = self.pairing_server
        if server is not None:
            server.wake_outgoing()

    def _next_send_file_request(self) -> SendFileRequest | None:
        return _queue_get(self._pending_send_files)

    def _next_ring_phone_request(self) -> utilities_pb2.RingPhoneRequest | None:
        return _queue_get(self._pending_ring_requests)

    def _next_call_control_request(self) -> calls_pb2.CallControlRequest | None:
        return _queue_get(self._pending_call_control_requests)

    def _next_dial_request(self) -> calls_pb2.DialRequest | None:
        return _queue_get(self._pending_dial_requests)

    def _next_telephony_diagnostics_request(self) -> calls_pb2.TelephonyDiagnosticsRequest | None:
        return _queue_get(self._pending_telephony_diagnostics_requests)

    def _next_notification_reply_request(self) -> notifications_pb2.NotificationReplyRequest | None:
        return _queue_get(self._pending_notification_reply_requests)

    def _next_notification_action_request(self) -> notifications_pb2.NotificationActionRequest | None:
        return _queue_get(self._pending_notification_action_requests)

    def _next_shared_app_launch_request(self) -> apps_pb2.SharedAppLaunchRequest | None:
        return _queue_get(self._pending_shared_app_launch_requests)

    def _next_phone_file_list_request(self) -> storage_pb2.PhoneFileListRequest | None:
        return _queue_get(self._pending_phone_file_list_requests)

    def _next_phone_file_pull_request(self) -> storage_pb2.PhoneFilePullRequest | None:
        return _queue_get(self._pending_phone_file_pull_requests)

    def _next_contacts_request(self) -> contacts_pb2.PhoneContactsRequest | None:
        return _queue_get(self._pending_contacts_requests)

    def _next_recent_contacts_request(self) -> contacts_pb2.PhoneRecentContactsRequest | None:
        return _queue_get(self._pending_recent_contacts_requests)

    def _next_bluetooth_status_request(self) -> bluetooth_pb2.BluetoothAssistDesktopStatus | None:
        return _queue_get(self._pending_bluetooth_status_requests)

    def _next_camera_capability_request(self) -> camera_pb2.CameraCapabilityRequest | None:
        return _queue_get(self._pending_camera_capability_requests)

    def _next_camera_start_request(self) -> camera_pb2.CameraStreamStartRequest | None:
        return _queue_get(self._pending_camera_start_requests)

    def _next_camera_ack(self) -> camera_pb2.CameraStreamAck | None:
        return _queue_get(self._pending_camera_acks)

    def _next_camera_stop_request(self) -> camera_pb2.CameraStreamStopRequest | None:
        return _queue_get(self._pending_camera_stop_requests)

    def _active_phone_host(self) -> str:
        with self._lock:
            devices = list(self._active_devices.values())
            known_endpoint = self._known_device_endpoints.get(self._last_connected_device_id, "")
        for device in devices:
            host = extract_ipv4_host(device.endpoint)
            if host:
                return host
        host = extract_ipv4_host(known_endpoint)
        if host:
            return host
        return ""

    def _record_mirror_launch(self, launch: MirrorLaunch) -> None:
        status = "started" if launch.result.ok else "failed"
        detail = launch.result.compact_output()
        self._last_mirror_status = f"Mirror {status}: {detail}"
        self.on_log(self._last_mirror_status)

    def _prepare_camera_usb_reverse(self, port: int) -> tuple[bool, str]:
        adb = self.scrcpy_manager.adb_path()
        if not adb:
            return False, "adb not found"
        device = self.scrcpy_manager.first_usb_device()
        if device is None:
            return False, "no authorized USB ADB device found"
        result = _run_command((adb, "-s", device.serial, "reverse", f"tcp:{port}", f"tcp:{port}"))
        if result.success:
            return True, f"adb reverse tcp:{port} prepared for {device.serial}"
        return False, result.detail

    def _remove_camera_usb_reverse(self, port: int) -> None:
        adb = self.scrcpy_manager.adb_path()
        device = self.scrcpy_manager.first_usb_device()
        if not adb or device is None:
            return
        result = _run_command((adb, "-s", device.serial, "reverse", "--remove", f"tcp:{port}"))
        self.on_log(f"[camera usb reverse removed] {result.detail}")


def _timestamp() -> common_pb2.Timestamp:
    return common_pb2.Timestamp(unix_epoch_ms=int(time.time() * 1000))


def _queue_get(queue: Queue[object]) -> object | None:
    try:
        return queue.get_nowait()
    except Empty:
        return None


def _call_entry_from_notification(
    notification: notifications_pb2.NotificationPosted,
    *,
    state_override: str = "",
) -> CallHistoryEntry:
    state = state_override or notification.call_state_hint or "notification"
    source = notification.app_name or notification.package_name or "Phone app"
    caller = notification.title or notification.body or "Unknown caller"
    detail_parts = [notification.body, notification.category, notification.package_name]
    detail = "; ".join(part for part in detail_parts if part)
    return CallHistoryEntry(
        event_id=f"call-notification-{notification.notification_id}-{state}-{time.time_ns()}",
        timestamp_ms=notification.posted_at.unix_epoch_ms or int(time.time() * 1000),
        source=source,
        caller=caller,
        state=state,
        direction="app notification",
        route="notification action",
        sim="",
        detail=detail,
        raw=notification.__repr__(),
    )


def _call_entry_from_status(message: str) -> CallHistoryEntry | None:
    if not message.startswith(("[call]", "[call metadata]")):
        return None
    timestamp_ms = int(time.time() * 1000)
    state = _metadata_value(message, "state") or "unknown"
    direction = _metadata_value(message, "direction")
    source = _metadata_value(message, "source") or "SIM call"
    caller = _metadata_value(message, "caller") or "Unavailable"
    route = _metadata_value(message, "route")
    detail = _metadata_value(message, "detail") or message
    if (
        state == "PHONE_CALL_STATE_IDLE"
        and caller.lower() in {"unavailable", "unknown caller", ""}
        and direction in {"", "CALL_DIRECTION_UNSPECIFIED"}
    ):
        return None
    sim_match = re.search(r"(SIM\s+\d+[^;]*)", message)
    sim = sim_match.group(1).strip() if sim_match else ""
    return CallHistoryEntry(
        event_id=f"call-status-{timestamp_ms}-{hashlib.sha1(message.encode('utf-8', errors='replace')).hexdigest()[:12]}",
        timestamp_ms=timestamp_ms,
        source=source,
        caller=caller,
        state=state,
        direction=direction,
        route=route,
        sim=sim,
        detail=detail,
        raw=message,
    )


def _metadata_value(message: str, key: str) -> str:
    if key == "detail":
        match = re.search(r"\bdetail=(.+)$", message)
    else:
        match = re.search(rf"\b{re.escape(key)}=([^;\s]+(?: [^;]+?)?)(?=;|$|\s+\w+=)", message)
    return match.group(1).strip() if match else ""


def _call_history_fingerprint(entry: CallHistoryEntry) -> str:
    digest = hashlib.sha256()
    for part in (
        entry.source,
        entry.caller,
        entry.state,
        entry.direction,
        entry.route,
        entry.sim,
        entry.detail,
    ):
        digest.update(part.encode("utf-8", errors="replace"))
        digest.update(b"\0")
    return digest.hexdigest()


def _notification_fingerprint(notification: notifications_pb2.NotificationPosted) -> str:
    digest = hashlib.sha256()
    parts = (
        notification.package_name,
        notification.app_name,
        notification.title,
        notification.body,
        notification.channel_id,
        notification.category,
        notification.call_state_hint,
        str(notification.call_like),
        str(notification.silent),
    )
    for part in parts:
        digest.update(part.encode("utf-8", errors="replace"))
        digest.update(b"\0")
    for action in notification.actions:
        digest.update(action.action_id.encode("utf-8", errors="replace"))
        digest.update(action.title.encode("utf-8", errors="replace"))
        digest.update(str(action.semantic).encode("ascii"))
        digest.update(str(action.supports_remote_input).encode("ascii"))
        digest.update(str(action.supports_plain_intent).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _shared_apps_fingerprint(apps: object) -> str:
    digest = hashlib.sha256()
    for app in sorted(apps, key=lambda item: item.package_name):
        digest.update(app.package_name.encode("utf-8", errors="replace"))
        digest.update(app.label.encode("utf-8", errors="replace"))
        digest.update(app.category.encode("utf-8", errors="replace"))
        digest.update(hashlib.sha256(bytes(app.icon_png)).digest())
        digest.update(b"\0")
    return digest.hexdigest()


def _set_audio_volume(percent: int, *, source: bool) -> InputCommandResult:
    clamped = max(0, min(150, int(percent)))
    wpctl = shutil.which("wpctl") or ""
    pactl = shutil.which("pactl") or ""
    if wpctl:
        target = "@DEFAULT_AUDIO_SOURCE@" if source else "@DEFAULT_AUDIO_SINK@"
        return _run_command((wpctl, "set-volume", target, f"{clamped}%"))
    if pactl:
        target = "@DEFAULT_SOURCE@" if source else "@DEFAULT_SINK@"
        action = "set-source-volume" if source else "set-sink-volume"
        return _run_command((pactl, action, target, f"{clamped}%"))
    return InputCommandResult(False, "wpctl or pactl is required for audio volume control")


def _run_command(command: tuple[str, ...]) -> InputCommandResult:
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return InputCommandResult(False, str(exc))
    output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
    if completed.returncode == 0:
        return InputCommandResult(True, output or "ok")
    return InputCommandResult(False, output or f"exit={completed.returncode}")


class BlockingPromptBridge:
    """Queue-backed prompt bridge useful for non-Qt tests and fallback runs."""

    def __init__(self) -> None:
        self.pairing_requests: Queue[tuple[str, str, str]] = Queue()

    def confirm_pairing(self, phone_name: str, device_id: str, address: str) -> bool:
        self.pairing_requests.put((phone_name, device_id, address))
        return False

    def prompt_code(self) -> str:
        return ""
