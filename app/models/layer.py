"""Canvas layers of a sticker document.

Coordinates are pixels of the sticker artboard at the document DPI.
``x``/``y`` are the layer centre; ``width``/``height`` are the unscaled
content size. Rotation is in degrees, clockwise, around the centre.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .base import dc_from_dict, dc_to_dict, new_id

LAYER_TYPES = ("image", "asset", "text", "shape", "group")


@dataclass
class Layer:
    id: str = field(default_factory=lambda: new_id("ly_"))
    type: str = "shape"
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 100.0
    height: float = 100.0
    rotation: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    flip_x: bool = False
    flip_y: bool = False
    opacity: float = 1.0
    visible: bool = True
    locked: bool = False
    # image
    photo_id: str | None = None
    source: str = "subject"  # "subject" (extracted) or "working" (full photo)
    crop: dict | None = None  # normalised {x, y, w, h} in 0..1
    treatment: dict = field(default_factory=dict)  # per-layer colour treatment
    keep_aspect: bool = True
    # asset
    asset_id: str | None = None
    colors: dict = field(default_factory=dict)
    # text
    text: str = ""
    font_family: str = "Poppins"
    font_size: float = 64.0
    font_weight: str = "normal"
    letter_spacing: float = 0.0
    line_height: float = 1.15
    align: str = "center"
    fill: str = "#222222"
    stroke: str = "#ffffff"
    stroke_width: float = 0.0
    shadow: dict | None = None
    background: dict | None = None
    curve: float = 0.0  # arc in degrees; 0 = straight
    wrap_width: float = 0.0  # 0 = no wrapping
    # shape
    shape: str = "rect"
    corner_radius: float = 0.0
    # group
    children: list["Layer"] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return dc_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Layer":
        layer = dc_from_dict(cls, data)
        if layer.type not in LAYER_TYPES:
            raise ValueError(f"unknown layer type {layer.type!r}")
        layer.children = [c if isinstance(c, Layer) else Layer.from_dict(c) for c in (data.get("children") or [])]
        if layer.type == "image" and layer.keep_aspect:
            # Photo layers always scale uniformly so faces are never distorted.
            s = (abs(layer.scale_x) + abs(layer.scale_y)) / 2 or 1.0
            layer.scale_x = layer.scale_y = s
        return layer


def ordered_layers(layers: list[Layer]) -> list[Layer]:
    """Layers in paint order (first = bottom). Kept explicit for clarity."""
    return list(layers)


def move_layer(layers: list[Layer], layer_id: str, to_index: int) -> list[Layer]:
    idx = next((i for i, l in enumerate(layers) if l.id == layer_id), None)
    if idx is None:
        raise KeyError(layer_id)
    out = list(layers)
    item = out.pop(idx)
    to_index = max(0, min(len(out), to_index))
    out.insert(to_index, item)
    return out
