import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.services.asset_service import AssetLibrary, recolor_svg
from app.services.text_service import FontRegistry
from app.services.theme_service import REQUIRED_KEYS, ThemeService
from app.utils.validation import ValidationError

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_THEMES = ["birthday", "gentleman", "superhero", "space", "jungle", "dinosaur", "princess", "animals", "school", "sports",
                   "christmas", "halloween", "diwali", "pongal", "wedding", "minimal", "hearts", "rainbow", "retro", "custom"]


@pytest.fixture()
def lib(tmp_path):
    return AssetLibrary(ROOT / "assets", tmp_path / "lib", ROOT / "assets" / "fonts")


def test_all_builtin_assets_render(lib):
    assets = lib.list()
    assert len(assets) >= 100
    for a in assets:
        img = lib.raster(a["id"], 64, 64)
        assert img.size == (64, 64)
        assert np.asarray(img)[..., 3].max() > 0, a["id"]
        assert a["license"].startswith("CC0")


def test_required_categories_present(lib):
    cats = {a["category"] for a in lib.list()}
    for c in ("crowns", "party-hats", "balloons", "confetti", "stars", "hearts", "sunglasses", "bowties", "hats", "flowers",
              "cakes", "gifts", "ribbons", "banners", "frames", "speech", "school", "sports", "seasonal", "shapes", "badges"):
        assert c in cats, c


def test_search(lib):
    ids = {a["id"] for a in lib.list("party hat")}
    assert "party_hat_stripes" in ids and "crown_gold" not in ids
    assert all(a["category"] == "frames" for a in lib.list(category="frames"))


def test_recolor():
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect fill="#111111" data-recolor="primary"/><path stroke="#222222" fill="none" data-recolor="secondary"/></svg>'
    out = recolor_svg(svg, {"primary": "#00ff00", "secondary": "#0000ff"})
    assert 'fill="#00ff00"' in out and 'stroke="#0000ff"' in out


def test_import_png_and_svg(lib):
    buf = io.BytesIO()
    Image.new("RGBA", (40, 20), (255, 0, 0, 128)).save(buf, "PNG")
    a = lib.import_asset(buf.getvalue(), "dog.png", category="animals", tags=["dog"])
    assert a["kind"] == "png" and a["aspect"] == 2.0 and not a["builtin"]
    s = lib.import_asset(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><script>x</script><circle cx="5" cy="5" r="4"/></svg>', "c.svg")
    stored = (lib.library_dir / "decorations" / f"{s['id']}.svg").read_text()
    assert "script" not in stored
    assert lib.raster(s["id"], 20, 20).size == (20, 20)
    lib.delete_user_asset(a["id"])
    assert a["id"] not in {x["id"] for x in lib.list()}


def test_import_rejects_bad_files(lib):
    with pytest.raises(ValidationError):
        lib.import_asset(b"\x89PNG\r\n\x1a\nnot really", "x.png")
    with pytest.raises(ValidationError):
        lib.import_asset(b"<svg><unclosed", "x.svg")


def test_all_themes_valid_and_reference_local_assets(lib, tmp_path):
    ts = ThemeService(ROOT / "assets" / "themes", tmp_path / "themes")
    ids = {a["id"] for a in lib.list()}
    themes = {t["id"]: t for t in ts.list()}
    for tid in REQUIRED_THEMES:
        t = themes[tid]
        assert ThemeService.validate(t) == [], tid
        for ref in t["decorations"] + t["frames"] + [x for v in t["accessorySets"].values() for x in v]:
            assert ref in ids, (tid, ref)
        for key in REQUIRED_KEYS:
            assert key in t
    assert len(themes) >= 20


def test_custom_theme_save(lib, tmp_path):
    ts = ThemeService(ROOT / "assets" / "themes", tmp_path / "themes")
    t = ts.save_custom({"name": "Mine", "palette": ["#112233", "nope", "#445566"], "decorations": ["star_basic", "missing"]}, {a["id"] for a in lib.list()})
    assert t["palette"] == ["#112233", "#445566"] and t["decorations"] == ["star_basic"]
    assert ts.get(t["id"])["name"] == "Mine"
    ts.delete_custom(t["id"])


def test_bundled_fonts_registered_with_licenses():
    reg = FontRegistry(ROOT / "assets" / "fonts", include_system=False)
    fams = {f["family"] for f in reg.list()}
    for f in ("Poppins", "Luckiest Guy", "Bangers", "Pacifico", "Lobster", "Chewy"):
        assert f in fams
    assert reg.resolve("Poppins", "bold").weight == 700
    assert reg.resolve("Does Not Exist").family == "Poppins"
    lic = list((ROOT / "assets" / "fonts" / "licenses").glob("*"))
    assert len(lic) >= 9
    _ = json
