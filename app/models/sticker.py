"""Sticker document: an artboard of layers plus shape/border/shadow settings."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..utils.image_dimensions import mm_to_px_int
from .base import dc_from_dict, dc_to_dict, new_id
from .layer import Layer

SHAPES = ("silhouette", "circle", "oval", "rounded", "rect", "square", "heart", "star", "speech", "custom")


@dataclass
class Outline:
    width_mm: float = 1.0
    color: str = "#ff4f8b"
    gap_mm: float = 0.0


@dataclass
class Border:
    width_mm: float = 3.0
    color: str = "#ffffff"
    outlines: list[Outline] = field(default_factory=list)
    smoothing: float = 0.5  # 0..1, rounds jagged silhouettes
    fill_holes: bool = True
    bridge_gaps: bool = True


@dataclass
class Shadow:
    enabled: bool = False
    offset_x_mm: float = 0.6
    offset_y_mm: float = 0.8
    blur_mm: float = 1.2
    color: str = "#000000"
    opacity: float = 0.35
    # "art": the artwork casts a shadow onto the sticker border (printed).
    # "sticker": shadow around the whole sticker (on-screen preview only,
    # because it would fall outside the cut line).
    target: str = "art"


@dataclass
class ShapeSpec:
    type: str = "silhouette"
    corner_radius_mm: float = 6.0
    star_points: int = 5
    custom_asset_id: str | None = None
    padding_mm: float = 0.0


@dataclass
class Background:
    type: str = "none"  # none | solid | gradient | pattern
    color: str = "#ffffff"
    color2: str = "#ffd6e7"
    angle: float = 90.0
    pattern_id: str | None = None
    pattern_color: str = "#ffffff"
    pattern_scale: float = 1.0


@dataclass
class StickerDoc:
    id: str = field(default_factory=lambda: new_id("st_"))
    name: str = "Sticker"
    width_mm: float = 60.0
    height_mm: float = 60.0
    dpi: int = 300
    shape: ShapeSpec = field(default_factory=ShapeSpec)
    border: Border = field(default_factory=Border)
    shadow: Shadow = field(default_factory=Shadow)
    background: Background = field(default_factory=Background)
    cut_offset_mm: float = 0.0
    layers: list[Layer] = field(default_factory=list)
    theme_id: str | None = None
    variant: dict = field(default_factory=dict)
    render_info: dict = field(default_factory=dict)
    canvas_background: str = "#f3f4f8"
    extra: dict = field(default_factory=dict)

    @property
    def width_px(self) -> int:
        return mm_to_px_int(self.width_mm, self.dpi)

    @property
    def height_px(self) -> int:
        return mm_to_px_int(self.height_mm, self.dpi)

    def to_dict(self) -> dict:
        d = dc_to_dict(self)
        d["layers"] = [l.to_dict() for l in self.layers]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "StickerDoc":
        doc = dc_from_dict(cls, {k: v for k, v in data.items() if k != "layers"})
        doc.layers = [Layer.from_dict(l) for l in data.get("layers") or []]
        if doc.shape.type not in SHAPES:
            doc.shape.type = "silhouette"
        doc.width_mm = max(5.0, min(297.0, float(doc.width_mm)))
        doc.height_mm = max(5.0, min(297.0, float(doc.height_mm)))
        doc.dpi = int(max(72, min(600, int(doc.dpi))))
        return doc
