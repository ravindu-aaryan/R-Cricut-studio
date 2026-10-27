"""Text and typography rendering with locally bundled (or installed) fonts.

Text is rendered with Pillow/FreeType into the sticker artwork. The same
font files are served to the browser editor through ``@font-face`` so the
on-screen preview uses identical glyphs.
"""
from __future__ import annotations

import math
import os
import sys
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..utils.validation import as_float, parse_color

WEIGHT_NAMES = {"Thin": 100, "ExtraLight": 200, "Light": 300, "Regular": 400, "Book": 400, "Medium": 500,
                "SemiBold": 600, "DemiBold": 600, "Bold": 700, "ExtraBold": 800, "Black": 900, "Heavy": 900}


@dataclass
class FontFace:
    id: str
    family: str
    style: str
    weight: int
    path: Path
    bundled: bool
    license: str = ""


@dataclass
class FontFamily:
    family: str
    faces: dict[int, FontFace] = field(default_factory=dict)
    bundled: bool = True
    category: str = "display"

    def face_for(self, weight: str | int) -> FontFace:
        w = 700 if str(weight) == "bold" else 400 if str(weight) in ("normal", "") else int(as_float(weight, 400))
        best = min(self.faces.values(), key=lambda f: (abs(f.weight - w), f.style != "Regular"))
        return best

    def to_dict(self) -> dict:
        return {
            "family": self.family,
            "bundled": self.bundled,
            "category": self.category,
            "weights": sorted(self.faces),
            "faces": [{"id": f.id, "weight": f.weight, "style": f.style} for f in self.faces.values()],
        }


BUNDLED_FONT_CATEGORIES = {
    "Poppins": "sans", "Pacifico": "script", "Lobster": "script", "Great Vibes": "script",
    "Bangers": "comic", "Luckiest Guy": "display", "Chewy": "display", "Permanent Marker": "handwritten",
    "Creepster": "spooky",
}

BUNDLED_LICENSES = {
    "Poppins": "SIL OFL 1.1", "Pacifico": "SIL OFL 1.1", "Lobster": "SIL OFL 1.1", "Great Vibes": "SIL OFL 1.1",
    "Bangers": "SIL OFL 1.1", "Creepster": "SIL OFL 1.1", "Luckiest Guy": "Apache 2.0", "Chewy": "Apache 2.0",
    "Permanent Marker": "Apache 2.0",
}


def _system_font_dirs() -> list[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        return [Path("/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"), home / "Library/Fonts"]
    if os.name == "nt":
        return [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"]
    return [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), home / ".fonts", home / ".local/share/fonts"]


class FontRegistry:
    """Index of available fonts. Fonts are referenced by family name in documents."""

    FALLBACK = "Poppins"

    def __init__(self, bundled_dir: Path, include_system: bool = True, max_system: int = 300):
        self.bundled_dir = bundled_dir
        self.families: dict[str, FontFamily] = {}
        self.faces: dict[str, FontFace] = {}
        self._lock = threading.Lock()
        self._scan(bundled_dir, bundled=True)
        if include_system:
            count = 0
            for d in _system_font_dirs():
                if d.exists():
                    count += self._scan(d, bundled=False, limit=max_system - count)
                if count >= max_system:
                    break

    def _scan(self, directory: Path, bundled: bool, limit: int = 10_000) -> int:
        added = 0
        paths = sorted(p for p in directory.rglob("*") if p.suffix.lower() in (".ttf", ".otf"))
        for p in paths:
            if added >= limit:
                break
            try:
                font = ImageFont.truetype(str(p), 20)
                family, style = font.getname()
            except Exception:
                continue
            if not family or (not bundled and family in self.families and self.families[family].bundled):
                continue
            style = style or "Regular"
            if "Italic" in style or "Oblique" in style:
                continue  # keep the picker focused on upright faces
            weight = WEIGHT_NAMES.get(style.replace(" ", ""), 400)
            fid = ("b-" if bundled else "s-") + "".join(c if c.isalnum() else "-" for c in f"{family}-{style}").lower()
            face = FontFace(fid, family, style, weight, p, bundled, BUNDLED_LICENSES.get(family, "") if bundled else "system font")
            fam = self.families.setdefault(family, FontFamily(family, bundled=bundled,
                                                              category=BUNDLED_FONT_CATEGORIES.get(family, "system" if not bundled else "display")))
            if weight not in fam.faces:
                fam.faces[weight] = face
                self.faces[fid] = face
                added += 1
        return added

    def resolve(self, family: str, weight: str | int = "normal") -> FontFace:
        fam = self.families.get(family) or self.families.get(self.FALLBACK) or next(iter(self.families.values()))
        return fam.face_for(weight)

    def font(self, family: str, weight: str | int, size_px: float) -> ImageFont.FreeTypeFont:
        face = self.resolve(family, weight)
        return _load_font(str(face.path), max(1, int(round(size_px))))

    def list(self) -> list[dict]:
        fams = sorted(self.families.values(), key=lambda f: (not f.bundled, f.family.lower()))
        return [f.to_dict() for f in fams]


@lru_cache(maxsize=128)
def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------

def _line_width(font: ImageFont.FreeTypeFont, text: str, spacing: float) -> float:
    if not text:
        return 0.0
    if spacing == 0:
        return font.getlength(text)
    return sum(font.getlength(c) for c in text) + spacing * max(0, len(text) - 1)


def wrap_lines(text: str, font: ImageFont.FreeTypeFont, max_width: float, spacing: float = 0.0) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        if max_width <= 0:
            lines.append(para)
            continue
        words = para.split(" ")
        cur = ""
        for word in words:
            trial = word if not cur else f"{cur} {word}"
            if _line_width(font, trial, spacing) <= max_width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def _draw_line(draw: ImageDraw.ImageDraw, xy, text, font, fill, spacing, stroke_width=0, stroke_fill=None):
    x, y = xy
    if spacing == 0:
        draw.text((x, y), text, font=font, fill=fill, anchor="lm", stroke_width=stroke_width, stroke_fill=stroke_fill)
        return
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, anchor="lm", stroke_width=stroke_width, stroke_fill=stroke_fill)
        x += font.getlength(ch) + spacing


def text_block_size(layer, registry: FontRegistry, scale: float = 1.0) -> tuple[int, int]:
    img = render_text(layer, registry, scale)
    return img.size


def render_text(layer, registry: FontRegistry, scale: float = 1.0) -> Image.Image:
    """Render a text layer into a tightly sized RGBA image (before transforms).

    ``scale`` is the output pixel scale (1.0 = document pixels).
    """
    size = max(4.0, as_float(layer.font_size, 64, 4, 2000)) * scale
    font = registry.font(layer.font_family, layer.font_weight, size)
    spacing = as_float(layer.letter_spacing, 0, -50, 500) * scale
    line_h = size * as_float(layer.line_height, 1.15, 0.6, 4)
    stroke_w = int(round(as_float(layer.stroke_width, 0, 0, 200) * scale))
    fill = parse_color(layer.fill, (34, 34, 34, 255))
    stroke = parse_color(layer.stroke, (255, 255, 255, 255))
    text = (layer.text or "").replace("\r", "")
    if not text.strip():
        return Image.new("RGBA", (max(1, int(size)), max(1, int(line_h))), (0, 0, 0, 0))
    if abs(as_float(layer.curve, 0, -360, 360)) >= 1:
        return _render_curved(layer, text.replace("\n", " "), font, size, spacing, fill, stroke, stroke_w, scale)

    lines = wrap_lines(text, font, as_float(layer.wrap_width, 0, 0, 20000) * scale, spacing)
    widths = [_line_width(font, ln, spacing) for ln in lines]
    bg = layer.background or {}
    pad = as_float(bg.get("padding"), 0, 0, 500) * scale if bg.get("color") else 0
    shadow = layer.shadow or {}
    sh_blur = as_float(shadow.get("blur"), 0, 0, 200) * scale if shadow.get("color") else 0
    sh_dx = as_float(shadow.get("offsetX"), 0, -500, 500) * scale if shadow.get("color") else 0
    sh_dy = as_float(shadow.get("offsetY"), 0, -500, 500) * scale if shadow.get("color") else 0
    content_w = max(widths) + 2 * stroke_w
    content_h = line_h * len(lines) + 2 * stroke_w
    margin = int(math.ceil(pad + 2 * sh_blur + max(abs(sh_dx), abs(sh_dy)) + 2))
    W = int(math.ceil(content_w + 2 * pad)) + 2 * margin
    H = int(math.ceil(content_h + 2 * pad)) + 2 * margin
    text_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(text_img)
    ox, oy = margin + pad + stroke_w, margin + pad + stroke_w
    align = layer.align if layer.align in ("left", "center", "right") else "center"
    for i, (ln, lw) in enumerate(zip(lines, widths)):
        if align == "center":
            x = ox + (max(widths) - lw) / 2
        elif align == "right":
            x = ox + max(widths) - lw
        else:
            x = ox
        y = oy + line_h * i + line_h / 2
        _draw_line(d, (x, y), ln, font, fill, spacing, stroke_w, stroke if stroke_w else None)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if pad or bg.get("color"):
        if bg.get("color"):
            radius = as_float(bg.get("radius"), 0, 0, 1000) * scale
            ImageDraw.Draw(out).rounded_rectangle(
                (margin, margin, W - margin, H - margin), radius=radius, fill=parse_color(bg["color"]))
    if shadow.get("color"):
        a = text_img.getchannel("A")
        sh = Image.new("RGBA", (W, H), parse_color(shadow["color"], (0, 0, 0, 120)))
        alpha = Image.new("L", (W, H), 0)
        alpha.paste(a, (int(round(sh_dx)), int(round(sh_dy))))
        if sh_blur > 0:
            alpha = alpha.filter(ImageFilter.GaussianBlur(sh_blur))
        sh_alpha = alpha.point(lambda v, k=parse_color(shadow["color"], (0, 0, 0, 120))[3]: v * k // 255)
        sh.putalpha(sh_alpha)
        out.alpha_composite(sh)
    out.alpha_composite(text_img)
    return out


def _render_curved(layer, text, font, size, spacing, fill, stroke, stroke_w, scale) -> Image.Image:
    """Lay glyphs along a circular arc. Positive curve bends upward (smile = negative)."""
    arc = math.radians(as_float(layer.curve, 0, -360, 360))
    widths = [font.getlength(c) + spacing for c in text]
    total = sum(widths) - spacing
    radius = total / abs(arc)
    cell = int(math.ceil(size * 1.6 + 2 * stroke_w))
    R = radius + cell
    W = H = int(math.ceil(2 * R)) + 4
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cx = cy = W / 2
    sign = 1 if arc > 0 else -1
    angle = -abs(arc) / 2
    for ch, w in zip(text, widths):
        mid = angle + (w - spacing) / 2 / radius
        glyph = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
        ImageDraw.Draw(glyph).text((cell / 2, cell / 2), ch, font=font, fill=fill, anchor="mm",
                                   stroke_width=stroke_w, stroke_fill=stroke if stroke_w else None)
        if sign > 0:  # along the top of a circle (a "frown"), reading left to right
            px, py = cx + radius * math.sin(mid), cy - radius * math.cos(mid)
            rot = glyph.rotate(-math.degrees(mid), resample=Image.Resampling.BICUBIC, expand=True)
        else:  # along the bottom of a circle (a "smile")
            px, py = cx + radius * math.sin(mid), cy + radius * math.cos(mid)
            rot = glyph.rotate(math.degrees(mid), resample=Image.Resampling.BICUBIC, expand=True)
        img.alpha_composite(rot, (int(round(px - rot.width / 2)), int(round(py - rot.height / 2))))
        angle += w / radius
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img
