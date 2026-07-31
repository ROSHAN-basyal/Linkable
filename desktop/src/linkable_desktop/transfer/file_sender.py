from __future__ import annotations

import hashlib
import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

from linkable_desktop.crypto.session_cipher import EncryptedEnvelopeChannel
from linkable_desktop.proto import build_envelope, common_pb2, files_pb2


@dataclass(frozen=True, slots=True)
class SendFileRequest:
    path: Path
    chunk_size: int = 48 * 1024

    @classmethod
    def from_path(cls, path: str) -> "SendFileRequest":
        candidate = Path(path).expanduser().resolve()
        if not candidate.is_file():
            raise ValueError(f"send-file path is not a regular file: {candidate}")
        return cls(path=candidate)


def _sha256_hex(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def send_file(
    encrypted: EncryptedEnvelopeChannel,
    request: SendFileRequest,
    *,
    sequence_number: int,
    sequence_provider: Callable[[], int] | None = None,
) -> int:
    def next_sequence() -> int:
        if sequence_provider is not None:
            return sequence_provider()
        nonlocal sequence_number
        current = sequence_number
        sequence_number += 1
        return current

    transfer_id = uuid4().hex
    file_size = request.path.stat().st_size
    sha256_hex = _sha256_hex(request.path)
    mime_type = mimetypes.guess_type(request.path.name)[0] or "application/octet-stream"
    offer = files_pb2.FileOffer(
        transfer_id=transfer_id,
        file_name=request.path.name,
        size_bytes=file_size,
        sha256_hex=sha256_hex,
        mime_type=mime_type,
        chunk_size=request.chunk_size,
        offered_at=common_pb2.Timestamp(unix_epoch_ms=int(time.time() * 1000)),
    )
    encrypted.write_envelope(
        build_envelope(common_pb2.PACKET_TYPE_FILE_OFFER, offer, sequence_number=next_sequence())
    )

    offset = 0
    with request.path.open("rb") as handle:
        while True:
            data = handle.read(request.chunk_size)
            if not data:
                break
            chunk = files_pb2.FileChunk(transfer_id=transfer_id, offset=offset, data=data)
            encrypted.write_envelope(
                build_envelope(common_pb2.PACKET_TYPE_FILE_CHUNK, chunk, sequence_number=next_sequence())
            )
            offset += len(data)

    complete = files_pb2.FileComplete(transfer_id=transfer_id, sha256_hex=sha256_hex)
    encrypted.write_envelope(
        build_envelope(common_pb2.PACKET_TYPE_FILE_COMPLETE, complete, sequence_number=next_sequence())
    )
    return sequence_number
