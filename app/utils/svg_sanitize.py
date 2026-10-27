"""Allow-list based SVG sanitiser.

Imported SVG files are parsed with defusedxml (no entity expansion or
external DTDs), then rebuilt keeping only known-safe elements and
attributes. Scripts, event handlers, foreignObject, external references
and CSS ``url()`` values that point outside the document are removed.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from defusedxml import ElementTree as SafeET

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

ALLOWED_ELEMENTS = {
    "svg", "g", "defs", "title", "desc", "symbol", "use",
    "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "text", "tspan", "textPath",
    "linearGradient", "radialGradient", "stop", "pattern",
    "clipPath", "mask", "filter",
    "feGaussianBlur", "feOffset", "feBlend", "feColorMatrix", "feComposite",
    "feFlood", "feMerge", "feMergeNode", "feDropShadow", "feMorphology",
    "image",
}

ALLOWED_ATTRS = {
    "id", "class", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "fx", "fy", "width", "height", "d", "points", "transform", "viewBox",
    "preserveAspectRatio", "fill", "fill-opacity", "fill-rule", "stroke",
    "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-miterlimit",
    "stroke-dasharray", "stroke-dashoffset", "stroke-opacity", "opacity",
    "clip-path", "clip-rule", "mask", "filter", "offset", "stop-color",
    "stop-opacity", "gradientUnits", "gradientTransform", "spreadMethod",
    "patternUnits", "patternContentUnits", "patternTransform", "clipPathUnits",
    "maskUnits", "maskContentUnits", "filterUnits", "primitiveUnits",
    "stdDeviation", "dx", "dy", "in", "in2", "result", "mode", "type", "values",
    "operator", "k1", "k2", "k3", "k4", "flood-color", "flood-opacity", "radius",
    "font-family", "font-size", "font-weight", "font-style", "text-anchor",
    "dominant-baseline", "letter-spacing", "startOffset", "visibility",
    "display", "style", "href", "version", "color", "vector-effect",
    "paint-order", "mix-blend-mode", "data-recolor",
}

SAFE_STYLE_PROPS = {
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-linecap",
    "stroke-linejoin", "stroke-opacity", "stroke-dasharray", "opacity", "stop-color",
    "stop-opacity", "font-family", "font-size", "font-weight", "font-style",
    "text-anchor", "display", "visibility", "color", "mix-blend-mode", "paint-order",
}

_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
_DATA_IMAGE_RE = re.compile(r"^data:image/(png|jpeg|jpg|webp|gif);base64,[A-Za-z0-9+/=\s]+$", re.IGNORECASE)


class SvgSanitizeError(ValueError):
    pass


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _safe_url_values(value: str) -> bool:
    for match in _URL_RE.finditer(value):
        if not match.group(2).strip().startswith("#"):
            return False
    return "javascript:" not in value.lower() and "expression(" not in value.lower()


def _clean_style(style: str) -> str:
    kept = []
    for decl in style.split(";"):
        if ":" not in decl:
            continue
        prop, val = (s.strip() for s in decl.split(":", 1))
        if prop.lower() in SAFE_STYLE_PROPS and _safe_url_values(val) and "@import" not in val.lower():
            kept.append(f"{prop}:{val}")
    return ";".join(kept)


def _clean_element(src: ET.Element, *, allow_embedded_images: bool) -> ET.Element | None:
    name = _local(src.tag)
    if name not in ALLOWED_ELEMENTS:
        return None
    dst = ET.Element(f"{{{SVG_NS}}}{name}")
    for key, value in src.attrib.items():
        attr = _local(key)
        low = attr.lower()
        if low.startswith("on") or attr not in ALLOWED_ATTRS:
            continue
        if attr == "href":
            v = value.strip()
            if name == "image":
                if not (allow_embedded_images and _DATA_IMAGE_RE.match(v)):
                    continue
            elif not v.startswith("#"):
                continue
            dst.set(attr, v)
            continue
        if attr == "style":
            cleaned = _clean_style(value)
            if cleaned:
                dst.set("style", cleaned)
            continue
        if not _safe_url_values(value):
            continue
        dst.set(attr, value)
    if name == "image" and "href" not in dst.attrib:
        return None
    dst.text = src.text if name in ("text", "tspan", "textPath", "title", "desc") else None
    for child in src:
        cleaned = _clean_element(child, allow_embedded_images=allow_embedded_images)
        if cleaned is not None:
            cleaned.tail = child.tail if name in ("text", "tspan", "textPath") else None
            dst.append(cleaned)
    return dst


def sanitize_svg(data: bytes | str, *, max_bytes: int = 5_000_000, allow_embedded_images: bool = True) -> str:
    """Return a sanitised SVG document as a string or raise ``SvgSanitizeError``."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    if len(raw) > max_bytes:
        raise SvgSanitizeError("SVG file is too large.")
    if b"<!ENTITY" in raw or b"<!DOCTYPE" in raw.upper():
        # defusedxml would reject entities anyway; DOCTYPEs are never needed.
        raw = re.sub(rb"<!DOCTYPE[^>\[]*(\[[^\]]*\])?\s*>", b"", raw, flags=re.IGNORECASE)
        if b"<!ENTITY" in raw:
            raise SvgSanitizeError("SVG entities are not allowed.")
    try:
        root = SafeET.fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except Exception as exc:
        raise SvgSanitizeError(f"Invalid SVG: {exc}") from None
    if _local(root.tag) != "svg":
        raise SvgSanitizeError("The file is not an SVG image.")
    cleaned = _clean_element(root, allow_embedded_images=allow_embedded_images)
    if cleaned is None:  # pragma: no cover - root already checked
        raise SvgSanitizeError("The file is not an SVG image.")
    if "viewBox" not in cleaned.attrib:
        w, h = cleaned.get("width"), cleaned.get("height")
        try:
            cleaned.set("viewBox", f"0 0 {float(str(w).rstrip('px'))} {float(str(h).rstrip('px'))}")
        except (TypeError, ValueError):
            pass
    ET.register_namespace("", SVG_NS)
    return ET.tostring(cleaned, encoding="unicode")


def svg_viewbox_size(svg_text: str) -> tuple[float, float]:
    """Return (width, height) from the viewBox (or width/height attributes)."""
    root = SafeET.fromstring(svg_text.encode("utf-8"))
    vb = root.get("viewBox")
    if vb:
        parts = re.split(r"[\s,]+", vb.strip())
        if len(parts) == 4:
            return float(parts[2]), float(parts[3])
    try:
        return float(str(root.get("width", "100")).rstrip("px")), float(str(root.get("height", "100")).rstrip("px"))
    except ValueError:
        return 100.0, 100.0
