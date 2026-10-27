"""Free-space checks before writing large files."""
from __future__ import annotations

import shutil
from pathlib import Path

MIN_FREE_BYTES = 200 * 1024 * 1024


class DiskSpaceError(OSError):
    pass


def ensure_free_space(path: Path, needed_bytes: int = 0, minimum: int = MIN_FREE_BYTES) -> None:
    """Raise ``DiskSpaceError`` when less than ``minimum + needed_bytes`` is free."""
    try:
        free = shutil.disk_usage(path).free
    except OSError:
        return
    if free < minimum + needed_bytes:
        raise DiskSpaceError(
            f"Not enough free disk space ({free / 1e6:.0f} MB free). Free some space and try again.")
