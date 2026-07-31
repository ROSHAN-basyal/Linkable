from __future__ import annotations

import os
import tempfile
from pathlib import Path


PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def ensure_private_directory(path: Path) -> Path:
    """Create a state directory and restrict it to the current Linux user."""

    path.mkdir(mode=PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True)
    os.chmod(path, PRIVATE_DIRECTORY_MODE)
    return path


def enforce_private_file(path: Path) -> Path:
    """Restrict an existing state file to owner read/write access."""

    if path.exists():
        os.chmod(path, PRIVATE_FILE_MODE)
    return path


def atomic_write_private(path: Path, data: str | bytes) -> None:
    """Atomically replace a private state file with mode 0600."""

    ensure_private_directory(path.parent)
    payload = data.encode("utf-8") if isinstance(data, str) else data
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, PRIVATE_FILE_MODE)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise
