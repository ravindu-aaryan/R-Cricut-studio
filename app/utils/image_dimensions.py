"""Physical-unit conversion and standard page sizes.

All conversions use ``pixels = millimetres / 25.4 * dpi``.
"""
from __future__ import annotations

from dataclasses import dataclass

MM_PER_INCH = 25.4
POINTS_PER_INCH = 72.0
DEFAULT_DPI = 300

A4_PORTRAIT_MM = (210.0, 297.0)
A4_LANDSCAPE_MM = (297.0, 210.0)


def mm_to_px(mm: float, dpi: float = DEFAULT_DPI) -> float:
    """Convert millimetres to (fractional) pixels at ``dpi``."""
    return mm / MM_PER_INCH * dpi


def mm_to_px_int(mm: float, dpi: float = DEFAULT_DPI) -> int:
    """Convert millimetres to a whole pixel count (rounded to nearest)."""
    return int(round(mm_to_px(mm, dpi)))


def px_to_mm(px: float, dpi: float = DEFAULT_DPI) -> float:
    return px / dpi * MM_PER_INCH


def mm_to_pt(mm: float) -> float:
    """Millimetres to PostScript points (1/72 inch), as used by PDF."""
    return mm / MM_PER_INCH * POINTS_PER_INCH


def pt_to_mm(pt: float) -> float:
    return pt / POINTS_PER_INCH * MM_PER_INCH


@dataclass(frozen=True)
class PageSize:
    width_mm: float
    height_mm: float

    def px(self, dpi: float = DEFAULT_DPI) -> tuple[int, int]:
        return mm_to_px_int(self.width_mm, dpi), mm_to_px_int(self.height_mm, dpi)

    def pt(self) -> tuple[float, float]:
        return mm_to_pt(self.width_mm), mm_to_pt(self.height_mm)


def a4(orientation: str = "portrait") -> PageSize:
    if orientation not in ("portrait", "landscape"):
        raise ValueError(f"unknown orientation: {orientation!r}")
    w, h = A4_PORTRAIT_MM if orientation == "portrait" else A4_LANDSCAPE_MM
    return PageSize(w, h)


def effective_dpi(source_px: float, printed_mm: float) -> float:
    """DPI that ``source_px`` pixels achieve when printed ``printed_mm`` wide."""
    if printed_mm <= 0:
        return float("inf")
    return source_px / (printed_mm / MM_PER_INCH)
