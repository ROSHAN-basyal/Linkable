from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
PACKAGED_PROTO_GENERATED_DIR = Path(__file__).resolve().parent / "generated_proto"
REPO_PROTO_GENERATED_DIR = ROOT_DIR / "protocol" / "generated" / "python"
PROTO_GENERATED_DIR = (
    PACKAGED_PROTO_GENERATED_DIR
    if PACKAGED_PROTO_GENERATED_DIR.exists()
    else REPO_PROTO_GENERATED_DIR
)

if str(PROTO_GENERATED_DIR) not in sys.path:
    sys.path.insert(0, str(PROTO_GENERATED_DIR))

import calls_pb2  # noqa: E402
import apps_pb2  # noqa: E402
import bluetooth_pb2  # noqa: E402
import camera_pb2  # noqa: E402
import clipboard_pb2  # noqa: E402
import common_pb2  # noqa: E402
import contacts_pb2  # noqa: E402
import errors_pb2  # noqa: E402
import files_pb2  # noqa: E402
import input_pb2  # noqa: E402
import notifications_pb2  # noqa: E402
import pairing_pb2  # noqa: E402
import session_pb2  # noqa: E402
import storage_pb2  # noqa: E402
import transport_pb2  # noqa: E402
import utilities_pb2  # noqa: E402


PROTOCOL_VERSION = common_pb2.ProtocolVersion(major=1, minor=0, patch=0)

PACKET_TO_MESSAGE = {
    common_pb2.PACKET_TYPE_PAIRING_REQUEST: pairing_pb2.PairingRequest,
    common_pb2.PACKET_TYPE_PAIRING_CHALLENGE: pairing_pb2.PairingChallenge,
    common_pb2.PACKET_TYPE_PAIRING_CONFIRM: pairing_pb2.PairingConfirm,
    common_pb2.PACKET_TYPE_PAIRING_COMPLETE: pairing_pb2.PairingComplete,
    common_pb2.PACKET_TYPE_PAIRING_REJECT: pairing_pb2.PairingReject,
    common_pb2.PACKET_TYPE_SESSION_INIT: session_pb2.SessionInit,
    common_pb2.PACKET_TYPE_SESSION_ACK: session_pb2.SessionAck,
    common_pb2.PACKET_TYPE_SESSION_ROTATE: session_pb2.SessionRotate,
    common_pb2.PACKET_TYPE_SESSION_CLOSE: session_pb2.SessionClose,
    common_pb2.PACKET_TYPE_PING: transport_pb2.Ping,
    common_pb2.PACKET_TYPE_PONG: transport_pb2.Pong,
    common_pb2.PACKET_TYPE_DEVICE_INFO_REQUEST: transport_pb2.DeviceInfoRequest,
    common_pb2.PACKET_TYPE_DEVICE_INFO_RESPONSE: transport_pb2.DeviceInfoResponse,
    common_pb2.PACKET_TYPE_CAPABILITIES_REQUEST: transport_pb2.CapabilitiesRequest,
    common_pb2.PACKET_TYPE_CAPABILITIES_RESPONSE: transport_pb2.CapabilitiesResponse,
    common_pb2.PACKET_TYPE_HEARTBEAT: transport_pb2.Heartbeat,
    common_pb2.PACKET_TYPE_NOTIFICATION_POSTED: notifications_pb2.NotificationPosted,
    common_pb2.PACKET_TYPE_NOTIFICATION_REMOVED: notifications_pb2.NotificationRemoved,
    common_pb2.PACKET_TYPE_NOTIFICATION_REPLY_REQUEST: notifications_pb2.NotificationReplyRequest,
    common_pb2.PACKET_TYPE_NOTIFICATION_REPLY_RESULT: notifications_pb2.NotificationReplyResult,
    common_pb2.PACKET_TYPE_NOTIFICATION_ACTION_REQUEST: notifications_pb2.NotificationActionRequest,
    common_pb2.PACKET_TYPE_NOTIFICATION_ACTION_RESULT: notifications_pb2.NotificationActionResult,
    common_pb2.PACKET_TYPE_FILE_OFFER: files_pb2.FileOffer,
    common_pb2.PACKET_TYPE_FILE_CHUNK: files_pb2.FileChunk,
    common_pb2.PACKET_TYPE_FILE_COMPLETE: files_pb2.FileComplete,
    common_pb2.PACKET_TYPE_FILE_TRANSFER_RESULT: files_pb2.FileTransferResult,
    common_pb2.PACKET_TYPE_RING_PHONE_REQUEST: utilities_pb2.RingPhoneRequest,
    common_pb2.PACKET_TYPE_RING_PHONE_RESULT: utilities_pb2.RingPhoneResult,
    common_pb2.PACKET_TYPE_CALL_STATE_EVENT: calls_pb2.CallStateEvent,
    common_pb2.PACKET_TYPE_CALL_CONTROL_REQUEST: calls_pb2.CallControlRequest,
    common_pb2.PACKET_TYPE_CALL_CONTROL_RESULT: calls_pb2.CallControlResult,
    common_pb2.PACKET_TYPE_DIAL_REQUEST: calls_pb2.DialRequest,
    common_pb2.PACKET_TYPE_DIAL_RESULT: calls_pb2.DialResult,
    common_pb2.PACKET_TYPE_TELEPHONY_DIAGNOSTICS_REQUEST: calls_pb2.TelephonyDiagnosticsRequest,
    common_pb2.PACKET_TYPE_TELEPHONY_DIAGNOSTICS_RESULT: calls_pb2.TelephonyDiagnosticsResult,
    common_pb2.PACKET_TYPE_CALL_METADATA_EVENT: calls_pb2.CallMetadataEvent,
    common_pb2.PACKET_TYPE_PHONE_CAPABILITY_SNAPSHOT: calls_pb2.PhoneCapabilitySnapshot,
    common_pb2.PACKET_TYPE_BLUETOOTH_ASSIST_DESKTOP_STATUS: bluetooth_pb2.BluetoothAssistDesktopStatus,
    common_pb2.PACKET_TYPE_BLUETOOTH_ASSIST_PHONE_STATUS: bluetooth_pb2.BluetoothAssistPhoneStatus,
    common_pb2.PACKET_TYPE_DESKTOP_INPUT_REQUEST: input_pb2.DesktopInputRequest,
    common_pb2.PACKET_TYPE_DESKTOP_INPUT_RESULT: input_pb2.DesktopInputResult,
    common_pb2.PACKET_TYPE_SHARED_APPS_SNAPSHOT: apps_pb2.SharedAppsSnapshot,
    common_pb2.PACKET_TYPE_SHARED_APP_LAUNCH_REQUEST: apps_pb2.SharedAppLaunchRequest,
    common_pb2.PACKET_TYPE_SHARED_APP_LAUNCH_RESULT: apps_pb2.SharedAppLaunchResult,
    common_pb2.PACKET_TYPE_PHONE_FILE_LIST_REQUEST: storage_pb2.PhoneFileListRequest,
    common_pb2.PACKET_TYPE_PHONE_FILE_LIST_RESPONSE: storage_pb2.PhoneFileListResponse,
    common_pb2.PACKET_TYPE_PHONE_FILE_PULL_REQUEST: storage_pb2.PhoneFilePullRequest,
    common_pb2.PACKET_TYPE_PHONE_FILE_PULL_RESULT: storage_pb2.PhoneFilePullResult,
    common_pb2.PACKET_TYPE_PHONE_CONTACTS_REQUEST: contacts_pb2.PhoneContactsRequest,
    common_pb2.PACKET_TYPE_PHONE_CONTACTS_RESPONSE: contacts_pb2.PhoneContactsResponse,
    common_pb2.PACKET_TYPE_PHONE_RECENT_CONTACTS_REQUEST: contacts_pb2.PhoneRecentContactsRequest,
    common_pb2.PACKET_TYPE_PHONE_RECENT_CONTACTS_RESPONSE: contacts_pb2.PhoneRecentContactsResponse,
    common_pb2.PACKET_TYPE_CAMERA_CAPABILITY_REQUEST: camera_pb2.CameraCapabilityRequest,
    common_pb2.PACKET_TYPE_CAMERA_CAPABILITY_RESPONSE: camera_pb2.CameraCapabilityResponse,
    common_pb2.PACKET_TYPE_CAMERA_STREAM_START_REQUEST: camera_pb2.CameraStreamStartRequest,
    common_pb2.PACKET_TYPE_CAMERA_STREAM_START_RESULT: camera_pb2.CameraStreamStartResult,
    common_pb2.PACKET_TYPE_CAMERA_STREAM_ACK: camera_pb2.CameraStreamAck,
    common_pb2.PACKET_TYPE_CAMERA_STREAM_STOP_REQUEST: camera_pb2.CameraStreamStopRequest,
    common_pb2.PACKET_TYPE_CAMERA_STREAM_STOP_RESULT: camera_pb2.CameraStreamStopResult,
    common_pb2.PACKET_TYPE_CAMERA_STREAM_STATUS_EVENT: camera_pb2.CameraStreamStatusEvent,
    common_pb2.PACKET_TYPE_CAMERA_FRAME: camera_pb2.CameraFrame,
    common_pb2.PACKET_TYPE_CLIPBOARD_UPDATE: clipboard_pb2.ClipboardUpdate,
    common_pb2.PACKET_TYPE_ERROR: errors_pb2.ErrorPayload,
}


def build_envelope(packet_type: int, message: object, sequence_number: int) -> common_pb2.Envelope:
    envelope = common_pb2.Envelope()
    envelope.protocol_version.CopyFrom(PROTOCOL_VERSION)
    envelope.packet_type = packet_type
    envelope.sequence_number = sequence_number
    envelope.payload = message.SerializeToString()
    return envelope


def decode_payload(envelope: common_pb2.Envelope) -> object:
    message_cls = PACKET_TO_MESSAGE.get(envelope.packet_type)
    if message_cls is None:
        raise ValueError(f"unsupported packet type: {envelope.packet_type}")
    message = message_cls()
    message.ParseFromString(envelope.payload)
    return message
