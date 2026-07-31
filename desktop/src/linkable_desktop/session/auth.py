from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from io import BytesIO

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from linkable_desktop.proto import common_pb2


SESSION_INIT_LABEL = b"linkable-session-init-v1"
SESSION_ACK_LABEL = b"linkable-session-ack-v1"


@dataclass(frozen=True, slots=True)
class EphemeralKeyPair:
    private_key: ec.EllipticCurvePrivateKey
    public_key_bytes: bytes


def _append_field(buffer: BytesIO, value: bytes) -> None:
    buffer.write(struct.pack(">I", len(value)))
    buffer.write(value)


def build_session_signature_payload(
    *,
    label: bytes,
    descriptor: common_pb2.PeerDescriptor,
    ephemeral_public_key: bytes,
    issued_at_ms: int,
) -> bytes:
    buffer = BytesIO()
    _append_field(buffer, label)
    _append_field(buffer, descriptor.device_id.fingerprint.encode("utf-8"))
    _append_field(buffer, descriptor.device_name.encode("utf-8"))
    _append_field(buffer, descriptor.platform.encode("utf-8"))
    _append_field(buffer, descriptor.identity_public_key)
    _append_field(buffer, ephemeral_public_key)
    buffer.write(struct.pack(">Q", descriptor.protocol_version.major))
    buffer.write(struct.pack(">Q", descriptor.protocol_version.minor))
    buffer.write(struct.pack(">Q", descriptor.protocol_version.patch))
    buffer.write(struct.pack(">q", issued_at_ms))
    return buffer.getvalue()


def generate_ephemeral_key_pair() -> EphemeralKeyPair:
    key = ec.generate_private_key(ec.SECP256R1())
    public_key_bytes = key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return EphemeralKeyPair(private_key=key, public_key_bytes=public_key_bytes)


def generate_ephemeral_public_key_bytes() -> bytes:
    return generate_ephemeral_key_pair().public_key_bytes


def is_timestamp_fresh(issued_at_ms: int, *, max_skew_ms: int, now_ms: int | None = None) -> bool:
    reference = now_ms if now_ms is not None else int(time.time() * 1000)
    return abs(reference - issued_at_ms) <= max_skew_ms
