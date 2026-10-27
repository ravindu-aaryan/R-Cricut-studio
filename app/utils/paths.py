"""Filesystem path safety helpers.

API parameters never carry filesystem paths. Routes accept opaque ids which
are validated here and resolved under a known root directory.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._ -]+")


class UnsafePathError(ValueError):
    """Raised when a path would escape its allowed root."""


def is_safe_id(value: str) -> bool:
    return bool(value) and bool(_ID_RE.match(value))


def require_safe_id(value: str, what: str = "id") -> str:
    if not isinstance(value, str) or not is_safe_id(value):
        raise UnsafePathError(f"invalid {what}")
    return value


def sanitize_filename(name: str, default: str = "file", max_len: int = 120) -> str:
    """Return a filename safe to use on every desktop OS.

    Strips directories, control characters, and reserved characters, and
    never returns an empty name, '.' or '..'.
    """
    name = unicodedata.normalize("NFKD", str(name or ""))
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.replace("\\", "/").split("/")[-1]
    name = _UNSAFE_CHARS.sub("_", name).strip(" ._")
    name = re.sub(r"_+", "_", name)
    if not name or name in (".", ".."):
        name = default
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if name.split(".")[0].upper() in reserved:
        name = f"_{name}"
    if len(name) > max_len:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 10:
            name = stem[: max_len - len(ext) - 1] + "." + ext
        else:
            name = name[:max_len]
    return name


def safe_join(root: Path, *parts: str) -> Path:
    """Join ``parts`` onto ``root`` and guarantee the result stays inside it."""
    root_resolved = Path(root).resolve()
    candidate = root_resolved.joinpath(*parts).resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise UnsafePathError("path escapes allowed directory")
    return candidate
