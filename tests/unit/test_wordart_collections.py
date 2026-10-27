"""Word art, multi-colour letters and mixed themed collections."""
from pathlib import Path

import numpy as np
import pytest

from app.models.layer import Layer
from app.services import variation_service as vs
from app.services.asset_service import AssetLibrary
from app.services.text_service import FontRegistry, render_text
from app.services.theme_service import ThemeService

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    return AssetLibrary(ROOT / "assets", tmp_path_factory.mktemp("lib"))


@pytest.fixture(scope="module")
def themes(tmp_path_factory):
    return ThemeService(ROOT / "assets" / "themes", tmp_path_factory.mktemp("t"))


def test_letter_colors_cycle_per_letter():
    reg = FontRegistry(ROOT / "assets" / "fonts", include_system=False)
    img = render_text(Layer(type="text", text="AB", font_family="Luckiest Guy", font_size=80, letter_colors=["#ff0000", "#0000ff"]), reg)
    arr = np.asarray(img).astype(int)
    opaque = arr[..., 3] > 250
    left, right = opaque[:, : arr.shape[1] // 2], opaque[:, arr.shape[1] // 2:]
    lred = arr[:, : arr.shape[1] // 2][left]
    rblue = arr[:, arr.shape[1] // 2:][right]
    assert (lred[:, 0] > 200).mean() > 0.8 and (rblue[:, 2] > 200).mean() > 0.8


def test_word_art_templates_reference_local_assets(lib, themes):
    ids = {a["id"] for a in lib.list()}
    for tid in ("birthday", "gentleman", "princess", "fairytale_blue"):
        t = themes.get(tid)
        assert t["wordArt"], tid
        for w in t["wordArt"]:
            assert all(d["asset"] in ids for d in w["decor"])


def test_wordart_layers_stack_lines(lib, themes):
    t = next(w for w in themes.get("birthday")["wordArt"] if w["id"] == "birthday_boy")
    layers = vs.wordart_layers(t, 300, 300, 600, {a["id"]: a for a in lib.list()})
    texts = [l for l in layers if l.type == "text"]
    assert [l.text for l in texts] == ["Birthday", "BOY"]
    assert texts[0].y < texts[1].y and texts[1].letter_colors


def test_mixed_collection_without_photos_and_number_only_when_chosen(lib, themes):
    assets = {a["id"]: a for a in lib.list()}
    theme = themes.get("birthday")
    opts = vs.CollectionOptions(photo_ids=[], theme_id="birthday", text_stickers=3, decor_stickers=3, seed=2)
    docs = vs.generate_collection(opts, theme, [], assets)
    kinds = [d["variant"]["composition"] for d in docs]
    assert kinds.count("wordart") == 3 and kinds.count("decoration") == 3
    used = {l.get("assetId") for d in docs for l in d["layers"]}
    assert not any(str(a).startswith("balloon_number_") for a in used if a), "ages must never be guessed"
    opts.number = "7"
    docs = vs.generate_collection(opts, theme, [], assets)
    assert any(l.get("assetId") == "balloon_number_7" for d in docs for l in d["layers"])


def test_matching_phrase_uses_word_art(lib, themes):
    theme = themes.get("birthday")
    assert vs._match_wordart("Happy Birthday", theme)["id"] == "happy_birthday"
    assert vs._match_wordart("Maya", theme) is None
