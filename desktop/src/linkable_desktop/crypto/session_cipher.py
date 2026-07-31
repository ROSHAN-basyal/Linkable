from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field
from threading import Lock

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from linkable_desktop.proto import common_pb2


SESSION_KEY_SALT_LABEL = b"linkable-session-keys-v1"
CLIENT_TO_SERVER_INFO = b"linkable-c2s-v1"
SERVER_TO_CLIENT_INFO = b"linkable-s2c-v1"


@dataclass(frozen=True, slots=True)
class DirectionalSessionKeys:
    client_to_server: bytes
    server_to_client: bytes


@dataclass(slots=True)
class ReplayGuard:
    _seen: set[int] = field(default_factory=set)

    def check_and_mark(self, counter: int) -> None:
        if counter in self._seen:
            raise ValueError(f"replayed encrypted frame counter: {counter}")
        self._seen.add(counter)


def _nonce(counter: int) -> bytes:
    return b"\x00\x00\x00\x00" + counter.to_bytes(8, "big")


def _derive_key(shared_secret: bytes, *, salt: bytes, info: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=info,
    ).derive(shared_secret)


def derive_directional_keys(
    *,
    private_key: ec.EllipticCurvePrivateKey,
    peer_public_key_bytes: bytes,
    initiator_public_key_bytes: bytes,
    acceptor_public_key_bytes: bytes,
) -> DirectionalSessionKeys:
    peer_public_key = serialization.load_der_public_key(peer_public_key_bytes)
    if not isinstance(peer_public_key, ec.EllipticCurvePublicKey):
        raise TypeError("peer ephemeral key is not an EC public key")
    shared_secret = private_key.exchange(ec.ECDH(), peer_public_key)
    salt = SESSION_KEY_SALT_LABEL + initiator_public_key_bytes + acceptor_public_key_bytes
    return DirectionalSessionKeys(
        client_to_server=_derive_key(shared_secret, salt=salt, info=CLIENT_TO_SERVER_INFO),
        server_to_client=_derive_key(shared_secret, salt=salt, info=SERVER_TO_CLIENT_INFO),
    )


@dataclass(slots=True)
class EncryptedEnvelopeChannel:
    stream: io.BufferedIOBase
    send_key: bytes
    receive_key: bytes
    max_frame_size: int = 1_048_576
    _send_counter: int = 0
    _replay_guard: ReplayGuard = field(default_factory=ReplayGuard)
    _write_lock: Lock = field(default_factory=Lock)

    def write_envelope(self, envelope: common_pb2.Envelope) -> None:
        with self._write_lock:
            plaintext = envelope.SerializeToString()
            ciphertext = AESGCM(self.send_key).encrypt(_nonce(self._send_counter), plaintext, None)
            frame = self._send_counter.to_bytes(8, "big") + ciphertext
            self.stream.write(struct.pack(">I", len(frame)))
            self.stream.write(frame)
            self.stream.flush()
            self._send_counter += 1

    def read_envelope(self) -> common_pb2.Envelope:
        header = _read_exact(self.stream, 4)
        (size,) = struct.unpack(">I", header)
        if size <= 8 or size > self.max_frame_size:
            raise ValueError(f"invalid encrypted frame size: {size}")
        frame = _read_exact(self.stream, size)
        counter = int.from_bytes(frame[:8], "big")
        self._replay_guard.check_and_mark(counter)
        plaintext = AESGCM(self.receive_key).decrypt(_nonce(counter), frame[8:], None)
        envelope = common_pb2.Envelope()
        envelope.ParseFromString(plaintext)
        return envelope


def _read_exact(stream: io.BufferedIOBase, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = stream.read(length - len(data))
        if not chunk:
            raise EOFError("unexpected end of encrypted stream")
        data.extend(chunk)
    return bytes(data)
