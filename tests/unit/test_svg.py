import xml.etree.ElementTree as ET

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.services import svg_cut_service as svc
from app.utils.svg_sanitize import SvgSanitizeError, sanitize_svg

EVIL = b"""<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100" height="100" onload="alert(1)">
  <script>alert('x')</script>
  <foreignObject><iframe src="https://evil.example"></iframe></foreignObject>
  <image href="https://evil.example/track.png" width="10" height="10"/>
  <use xlink:href="https://evil.example/sprite.svg#a"/>
  <a href="javascript:alert(1)"><circle r="5"/></a>
  <rect width="10" height="10" fill="url(https://evil.example/p)" onclick="x()" style="fill:red;background:url(http://evil)"/>
  <circle cx="50" cy="50" r="40" fill="#ff0000" data-recolor="primary"/>
</svg>"""


def test_sanitizer_removes_active_and_external_content():
    clean = sanitize_svg(EVIL)
    low = clean.lower()
    for bad in ("script", "onload", "onclick", "foreignobject", "iframe", "evil.example", "javascript:"):
        assert bad not in low, bad
    root = ET.fromstring(clean)
    circles = [e for e in root.iter() if e.tag.endswith("circle")]
    assert any(c.get("data-recolor") == "primary" for c in circles)


def test_sanitizer_rejects_entities_and_non_svg():
    bomb = b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;">]><svg xmlns="http://www.w3.org/2000/svg">&lol2;</svg>'
    with pytest.raises(SvgSanitizeError):
        sanitize_svg(bomb)
    with pytest.raises(SvgSanitizeError):
        sanitize_svg(b"<html><body/></html>")
    with pytest.raises(SvgSanitizeError):
        sanitize_svg(b"not xml at all <")


def test_sanitizer_keeps_embedded_data_images():
    png = "data:image/png;base64,iVBORw0KGgo="
    clean = sanitize_svg(f'<svg xmlns="http://www.w3.org/2000/svg"><image href="{png}" width="1" height="1"/></svg>')
    assert png in clean


def disc_mask(size=400, r=120, px_per_mm=10):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).ellipse((size / 2 - r, size / 2 - r, size / 2 + r, size / 2 + r), fill=255)
    return np.asarray(m)


def test_cut_path_geometry_in_mm():
    paths = svc.trace_cut_paths(disc_mask(), 10.0)
    assert len(paths) == 1
    x0, y0, x1, y1 = svc.paths_bbox(paths)
    assert x1 - x0 == pytest.approx(24.0, abs=0.3)  # 240 px / 10 px per mm
    assert y1 - y0 == pytest.approx(24.0, abs=0.3)
    assert not svc._segments_intersect(np.array(paths[0].points))


def test_holes_and_multiple_pieces():
    m = disc_mask().copy()
    m[180:220, 180:220] = 0
    m[10:40, 10:40] = 255
    outer = svc.trace_cut_paths(m, 10, include_holes=False)
    assert len(outer) == 2
    with_holes = svc.trace_cut_paths(m, 10, include_holes=True)
    assert sum(p.is_hole for p in with_holes) == 1


def test_self_intersection_detector():
    bowtie = np.array([[0, 0], [10, 10], [10, 0], [0, 10]], float)
    square = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)
    assert svc._segments_intersect(bowtie)
    assert not svc._segments_intersect(square)


def test_sticker_svg_is_valid_and_physical():
    img = Image.new("RGBA", (300, 200), (255, 0, 0, 255))
    paths = svc.trace_cut_paths(np.full((200, 300), 255, np.uint8), 300 / 25.4)
    text = svc.sticker_svg(img, paths, 300 / 25.4, title="Test")
    root = ET.fromstring(text.split("\n", 1)[1])
    assert root.get("width") == "25.400mm" and root.get("height") == "16.933mm"
    groups = {g.get("id"): g for g in root.iter() if g.tag.endswith("g")}
    assert "artwork" in groups and "cut-lines" in groups
    assert groups["cut-lines"].get("stroke") == svc.CUT_COLOR
    cut_only = svc.sticker_svg(img, paths, 300 / 25.4, include_artwork=False)
    assert "<image" not in cut_only and "<path" in cut_only


def test_sheet_svg_places_and_rotates_paths():
    img = Image.new("RGBA", (100, 100), (0, 0, 255, 255))
    paths = svc.trace_cut_paths(np.full((100, 100), 255, np.uint8), 10)  # 10 x 10 mm square
    p = svc.Placement(img, paths, 50, 60, 20, 20, 90, "S", 10, 10)
    text = svc.sheet_svg(210, 297, [p])
    root = ET.fromstring(text.split("\n", 1)[1])
    d = next(e for e in root.iter() if e.tag.endswith("path")).get("d")
    nums = [float(v) for v in d.replace("M", " ").replace("L", " ").replace("Z", " ").replace(",", " ").split()]
    xs, ys = nums[0::2], nums[1::2]
    assert min(xs) == pytest.approx(50, abs=0.6) and max(xs) == pytest.approx(70, abs=0.6)
    assert min(ys) == pytest.approx(60, abs=0.6) and max(ys) == pytest.approx(80, abs=0.6)
    assert root.get("viewBox") == "0 0 210.000 297.000"
