"""A4 sheet layout documents. All positions are millimetres from the page's top-left."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..utils.image_dimensions import a4
from .base import dc_from_dict, dc_to_dict, new_id

# Cricut Design Space limits Print Then Cut images to 6.75 x 9.25 in on most
# machines (check your machine / Design Space version). Centred on A4 this
# leaves the margins below. Users can always override them.
PTC_W_MM, PTC_H_MM = 6.75 * 25.4, 9.25 * 25.4

PRINTABLE_PRESETS = {
    "full": (0.0, 0.0, 0.0, 0.0),
    "printer": (5.0, 5.0, 5.0, 5.0),
    "cricut_ptc": None,  # computed for orientation
}


@dataclass
class Printable:
    preset: str = "printer"
    top_mm: float = 5.0
    right_mm: float = 5.0
    bottom_mm: float = 5.0
    left_mm: float = 5.0


@dataclass
class SheetItem:
    id: str = field(default_factory=lambda: new_id("it_"))
    sticker_id: str = ""
    x_mm: float = 0.0
    y_mm: float = 0.0
    width_mm: float = 50.0
    height_mm: float = 50.0
    rotation: float = 0.0  # degrees clockwise around the item centre

    def bbox(self) -> tuple[float, float, float, float]:
        """Axis-aligned bounds (x0, y0, x1, y1) including rotation."""
        import math

        cx, cy = self.x_mm + self.width_mm / 2, self.y_mm + self.height_mm / 2
        a = math.radians(self.rotation)
        c, s = abs(math.cos(a)), abs(math.sin(a))
        hw = (self.width_mm * c + self.height_mm * s) / 2
        hh = (self.width_mm * s + self.height_mm * c) / 2
        return cx - hw, cy - hh, cx + hw, cy + hh


@dataclass
class SheetPage:
    id: str = field(default_factory=lambda: new_id("pg_"))
    items: list[SheetItem] = field(default_factory=list)


@dataclass
class Sheet:
    id: str = field(default_factory=lambda: new_id("sh_"))
    name: str = "A4 sheet"
    orientation: str = "portrait"
    dpi: int = 300
    margin_mm: float = 8.0
    gap_mm: float = 4.0
    printable: Printable = field(default_factory=Printable)
    background: str = "#ffffff"
    show_cut_lines: bool = False
    label: str = ""
    pages: list[SheetPage] = field(default_factory=lambda: [SheetPage()])
    extra: dict = field(default_factory=dict)

    @property
    def page_size(self):
        return a4(self.orientation)

    def printable_rect(self) -> tuple[float, float, float, float]:
        """Printable area (x0, y0, x1, y1) in mm."""
        pw, ph = self.page_size.width_mm, self.page_size.height_mm
        p = self.printable
        if p.preset == "cricut_ptc":
            w, h = (PTC_W_MM, PTC_H_MM) if self.orientation == "portrait" else (PTC_H_MM, PTC_W_MM)
            x0, y0 = (pw - w) / 2, (ph - h) / 2
            return x0, y0, x0 + w, y0 + h
        if p.preset == "full":
            return 0.0, 0.0, pw, ph
        return p.left_mm, p.top_mm, pw - p.right_mm, ph - p.bottom_mm

    def content_rect(self) -> tuple[float, float, float, float]:
        """Area available for stickers: printable area shrunk by the margin."""
        x0, y0, x1, y1 = self.printable_rect()
        m = self.margin_mm
        return x0 + m, y0 + m, max(x0 + m, x1 - m), max(y0 + m, y1 - m)

    def to_dict(self) -> dict:
        return dc_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Sheet":
        sheet = dc_from_dict(cls, data)
        if sheet.orientation not in ("portrait", "landscape"):
            sheet.orientation = "portrait"
        if not sheet.pages:
            sheet.pages = [SheetPage()]
        return sheet
