from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

from linkable_desktop.proto import common_pb2, files_pb2


@dataclass(slots=True)
class _ActiveReceive:
    offer: files_pb2.FileOffer
    temp_path: Path
    final_path: Path
    bytes_received: int = 0


class FileReceiver:
    def __init__(self, download_dir: Path | None = None) -> None:
        self.download_dir = download_dir or (Path.home() / "Downloads" / "Linkable")
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._active: dict[str, _ActiveReceive] = {}

    def handle_offer(self, offer: files_pb2.FileOffer) -> files_pb2.FileTransferResult:
        safe_name = self._safe_file_name(offer.file_name)
        final_path = self._unique_path(self.download_dir / safe_name)
        temp_path = final_path.with_name(f"{final_path.name}.{offer.transfer_id}.part")
        if temp_path.exists():
            temp_path.unlink()
        self._active[offer.transfer_id] = _ActiveReceive(
            offer=offer,
            temp_path=temp_path,
            final_path=final_path,
        )
        return self._result(
            transfer_id=offer.transfer_id,
            success=True,
            detail=f"accepted {offer.file_name}",
            saved_path=str(final_path),
            bytes_received=0,
        )

    def handle_chunk(self, chunk: files_pb2.FileChunk) -> files_pb2.FileTransferResult | None:
        active = self._active.get(chunk.transfer_id)
        if active is None:
            return self._result(
                transfer_id=chunk.transfer_id,
                success=False,
                detail="unknown transfer",
                saved_path="",
                bytes_received=0,
            )
        if chunk.offset != active.bytes_received:
            self._active.pop(chunk.transfer_id, None)
            active.temp_path.unlink(missing_ok=True)
            return self._result(
                transfer_id=chunk.transfer_id,
                success=False,
                detail=f"unexpected chunk offset {chunk.offset}, expected {active.bytes_received}",
                saved_path=str(active.final_path),
                bytes_received=active.bytes_received,
            )
        with active.temp_path.open("ab") as output:
            output.write(chunk.data)
        active.bytes_received += len(chunk.data)
        return None

    def handle_complete(self, complete: files_pb2.FileComplete) -> files_pb2.FileTransferResult:
        active = self._active.pop(complete.transfer_id, None)
        if active is None:
            return self._result(
                transfer_id=complete.transfer_id,
                success=False,
                detail="unknown transfer",
                saved_path="",
                bytes_received=0,
            )
        if active.bytes_received != active.offer.size_bytes:
            active.temp_path.unlink(missing_ok=True)
            return self._result(
                transfer_id=complete.transfer_id,
                success=False,
                detail=f"size mismatch {active.bytes_received}/{active.offer.size_bytes}",
                saved_path=str(active.final_path),
                bytes_received=active.bytes_received,
            )
        actual_sha = self._sha256_hex(active.temp_path)
        if actual_sha.lower() != complete.sha256_hex.lower():
            active.temp_path.unlink(missing_ok=True)
            return self._result(
                transfer_id=complete.transfer_id,
                success=False,
                detail="sha256 mismatch",
                saved_path=str(active.final_path),
                bytes_received=active.bytes_received,
            )
        active.temp_path.replace(active.final_path)
        return self._result(
            transfer_id=complete.transfer_id,
            success=True,
            detail=f"received {active.offer.file_name}",
            saved_path=str(active.final_path),
            bytes_received=active.bytes_received,
        )

    def _result(
        self,
        *,
        transfer_id: str,
        success: bool,
        detail: str,
        saved_path: str,
        bytes_received: int,
    ) -> files_pb2.FileTransferResult:
        return files_pb2.FileTransferResult(
            transfer_id=transfer_id,
            success=success,
            detail=detail,
            saved_path=saved_path,
            bytes_received=bytes_received,
            completed_at=common_pb2.Timestamp(unix_epoch_ms=int(time.time() * 1000)),
        )

    def _safe_file_name(self, file_name: str) -> str:
        cleaned = Path(file_name).name.strip()
        safe = "".join(char if char.isalnum() or char in "._- " else "_" for char in cleaned)
        return safe or "linkable-transfer.bin"

    def _unique_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        index = 1
        while True:
            candidate = path.with_name(f"{stem}-{index}{suffix}")
            if not candidate.exists():
                return candidate
            index += 1

    def _sha256_hex(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
