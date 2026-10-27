"""Small helpers to map dataclasses to/from camelCase JSON dictionaries."""
from __future__ import annotations

import dataclasses
import re
import uuid
from typing import Any, TypeVar, get_type_hints

T = TypeVar("T")


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def to_camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(p[:1].upper() + p[1:] for p in rest)


def to_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def dc_to_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out = {}
        for f in dataclasses.fields(obj):
            out[to_camel(f.name)] = dc_to_dict(getattr(obj, f.name))
        extra = getattr(obj, "extra", None)
        if isinstance(extra, dict):
            out.pop("extra", None)
            for k, v in extra.items():
                out.setdefault(k, v)
        return out
    if isinstance(obj, list):
        return [dc_to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: dc_to_dict(v) for k, v in obj.items()}
    return obj


def dc_from_dict(cls: type[T], data: dict | None) -> T:
    """Build ``cls`` from a camelCase dict, ignoring unknown keys.

    Nested dataclasses and ``list[Dataclass]`` fields are converted
    recursively. Keys that are not fields are kept in ``extra`` when the
    dataclass declares one, so newer documents survive a round trip.
    """
    data = dict(data or {})
    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    field_names = {f.name for f in dataclasses.fields(cls)}  # type: ignore[arg-type]
    leftovers = {}
    for key, value in data.items():
        name = to_snake(key) if key not in field_names else key
        if name not in field_names or name == "extra":
            leftovers[key] = value
            continue
        kwargs[name] = _convert(hints.get(name), value)
    if "extra" in field_names:
        kwargs["extra"] = leftovers
    return cls(**kwargs)  # type: ignore[call-arg]


def _convert(tp: Any, value: Any) -> Any:
    if value is None or tp is None:
        return value
    origin = getattr(tp, "__origin__", None)
    if dataclasses.is_dataclass(tp) and isinstance(value, dict):
        return dc_from_dict(tp, value)
    if origin is list and isinstance(value, list):
        (inner,) = getattr(tp, "__args__", (Any,))
        return [_convert(inner, v) for v in value]
    args = getattr(tp, "__args__", ())
    if args and type(None) in args:  # Optional[X]
        for a in args:
            if a is not type(None) and dataclasses.is_dataclass(a) and isinstance(value, dict):
                return dc_from_dict(a, value)
    return value
