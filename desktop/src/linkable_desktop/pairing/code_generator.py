from __future__ import annotations

import hashlib
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


PAIRING_CODE_INFO = b"linkable-pair-code-v1"
PAIR_CONFIRM_PREFIX = b"PAIR_CONFIRM_V1"


def derive_pairing_code(
    *,
    pairing_nonce: bytes,
    challenge_nonce: bytes,
    initiator_public_key: bytes,
    acceptor_public_key: bytes,
    code_length: int = 6,
) -> str:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=8,
        salt=initiator_public_key + acceptor_public_key,
        info=PAIRING_CODE_INFO,
    )
    raw = hkdf.derive(pairing_nonce + challenge_nonce)
    value = int.from_bytes(raw, byteorder="big") % (10**code_length)
    return str(value).zfill(code_length)


def compute_transcript_hash(
    *,
    pairing_nonce: bytes,
    challenge_nonce: bytes,
    initiator_device_id: str,
    acceptor_device_id: str,
    verification_code: str,
) -> bytes:
    digest = hashlib.sha256()
    digest.update(PAIR_CONFIRM_PREFIX)
    digest.update(pairing_nonce)
    digest.update(challenge_nonce)
    digest.update(initiator_device_id.encode("utf-8"))
    digest.update(acceptor_device_id.encode("utf-8"))
    digest.update(verification_code.encode("utf-8"))
    return digest.digest()


@dataclass(slots=True)
class PairingChallengeMaterial:
    pairing_nonce: bytes
    challenge_nonce: bytes
    initiator_public_key: bytes
    acceptor_public_key: bytes
    initiator_device_id: str
    acceptor_device_id: str
    code_length: int = 6

    def pairing_code(self) -> str:
        return derive_pairing_code(
            pairing_nonce=self.pairing_nonce,
            challenge_nonce=self.challenge_nonce,
            initiator_public_key=self.initiator_public_key,
            acceptor_public_key=self.acceptor_public_key,
            code_length=self.code_length,
        )

    def transcript_hash(self) -> bytes:
        return compute_transcript_hash(
            pairing_nonce=self.pairing_nonce,
            challenge_nonce=self.challenge_nonce,
            initiator_device_id=self.initiator_device_id,
            acceptor_device_id=self.acceptor_device_id,
            verification_code=self.pairing_code(),
        )

