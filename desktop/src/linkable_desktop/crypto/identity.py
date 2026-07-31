from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _device_id_from_public_key(public_key_bytes: bytes) -> str:
    digest = hashlib.sha256(public_key_bytes).digest()
    return base64.b32encode(digest[:10]).decode("ascii").rstrip("=")


@dataclass(slots=True)
class PeerIdentity:
    device_id: str
    device_name: str
    public_key_bytes: bytes

    def verify(self, payload: bytes, signature: bytes) -> bool:
        public_key = serialization.load_der_public_key(self.public_key_bytes)
        try:
            public_key.verify(signature, payload, ec.ECDSA(hashes.SHA256()))
            return True
        except InvalidSignature:
            return False


class DeviceIdentity:
    def __init__(self, *, device_name: str, private_key: ec.EllipticCurvePrivateKey) -> None:
        self.device_name = device_name
        self._private_key = private_key
        self._public_key = private_key.public_key()
        self.public_key_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.device_id = _device_id_from_public_key(self.public_key_bytes)

    @classmethod
    def load_or_create(cls, path: Path, *, device_name: str) -> "DeviceIdentity":
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            private_key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        else:
            private_key = ec.generate_private_key(ec.SECP256R1())
            path.write_bytes(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
        return cls(device_name=device_name, private_key=private_key)

    def sign(self, payload: bytes) -> bytes:
        return self._private_key.sign(payload, ec.ECDSA(hashes.SHA256()))

    def to_peer_identity(self) -> PeerIdentity:
        return PeerIdentity(
            device_id=self.device_id,
            device_name=self.device_name,
            public_key_bytes=self.public_key_bytes,
        )

