"""Browser end-to-end test of the main workflow (Playwright + Chromium).

Every request that does not go to the local server is aborted and recorded,
and the test fails if any such request is attempted.
"""
from __future__ import annotations

import urllib.request

import pytest

from tests.fixtures.synthetic import figure_image, jpeg_bytes

pytestmark = pytest.mark.e2e


def store(page, expr):
    return page.evaluate(f"() => {{ const s = window.oss.store; return {expr}; }}")


def test_main_workflow_in_browser(page, tmp_path):
    photo_path = tmp_path / "figure.jpg"
    photo_path.write_bytes(jpeg_bytes(figure_image((800, 1000))))
    page.goto(page.base + "/")
    page.wait_for_selector("text=Turn your photos into die-cut stickers")

    # 1. create a project
    page.click("#new-project")
    page.fill("#np-name", "Browser test")
    page.select_option("#np-theme", "birthday")
    page.click("text=Create project")
    page.wait_for_url("**/photos")

    # 2. import a photo (stays on this machine)
    page.set_input_files("#file", str(photo_path))
    page.wait_for_selector(".photo-card", timeout=30000)
    assert store(page, "s.doc.photos.length") == 1

    # 3. cut out the subject with GrabCut
    page.click(".photo-card >> text=Cut out")
    page.wait_for_selector("#stage canvas")
    box = page.locator("#stage").bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.25, box["y"] + 30)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] * 0.75, box["y"] + box["height"] - 5, steps=10)
    page.mouse.up()
    page.click("#run")
    page.wait_for_selector("#result-note .note", timeout=60000)
    assert store(page, "!!s.doc.photos[0].mask")

    # 4. make a sticker and edit it: add text, undo, redo, add an asset
    page.click("#rail >> text=Photos")
    page.click(".photo-card >> text=Make sticker")
    page.wait_for_url("**/editor/**")
    page.wait_for_selector("#canvas canvas")
    n0 = store(page, "s.doc.stickers[0].layers.length")
    page.click('#left [data-tab="text"]')
    page.fill("#custom", "E2E Test")
    page.click("#add-custom")
    page.wait_for_function(f"() => window.oss.store.doc.stickers[0].layers.length === {n0 + 1}")
    assert store(page, "s.doc.stickers[0].layers.at(-1).text") == "E2E Test"
    page.click("#tb-undo")
    page.wait_for_function(f"() => window.oss.store.doc.stickers[0].layers.length === {n0}")
    page.click("#tb-redo")
    page.wait_for_function(f"() => window.oss.store.doc.stickers[0].layers.length === {n0 + 1}")
    page.click('#left [data-tab="assets"]')
    page.fill("#aq", "crown")
    page.click("#agrid .asset-tile >> nth=0")
    page.wait_for_function(f"() => window.oss.store.doc.stickers[0].layers.length === {n0 + 2}")
    # the new layer is selected once its artwork has loaded
    page.wait_for_selector("#right-body h4:has-text('crown')", timeout=15000)
    # keyboard: duplicate selected layer, then delete it again
    page.keyboard.press("Control+d")
    page.wait_for_function(f"() => window.oss.store.doc.stickers[0].layers.length === {n0 + 3}")
    page.keyboard.press("Delete")
    page.wait_for_function(f"() => window.oss.store.doc.stickers[0].layers.length === {n0 + 2}")
    # the finished-sticker preview is rendered by the local engine
    page.click('#right [data-tab="preview"]')
    page.wait_for_selector("#right-body .preview-box img", timeout=30000)
    page.keyboard.press("Control+s")
    page.wait_for_selector("#save-state:has-text('All changes saved')", timeout=15000)

    # 5. generate variants and send them to the A4 sheet
    page.click("#rail >> text=Variants")
    page.click("#generate")
    page.wait_for_selector(".variant-card img", timeout=60000)
    count = page.locator(".variant-card").count()
    assert count >= 4
    page.click("#to-sheet")
    page.wait_for_url("**/sheet", timeout=30000)
    page.wait_for_function("() => window.oss.store.doc.sheets[0].pages[0].items.length > 0", timeout=60000)
    page.wait_for_selector("#warns .note.ok, #warns .warn-item", timeout=30000)

    # 6. export an A4 PDF and individual PNG stickers
    page.click("#rail >> text=Export")
    page.click('[data-k="sheet-pdf"]')
    page.click("#go")
    page.wait_for_selector("text=Export finished", timeout=120000)
    link = page.locator('#result a[href*=".pdf"]').first.get_attribute("href")
    with urllib.request.urlopen(page.base + link) as r:
        assert r.read(5) == b"%PDF-"
    page.click('[data-k="stickers-png"]')
    page.click("#go")
    page.wait_for_selector("text=Export finished: Individual PNG stickers", timeout=120000)
    assert page.locator("#result .file-row").count() >= 2

    # 7. reopen the project after a reload: everything is still there
    stickers = store(page, "s.doc.stickers.length")
    page.reload()
    page.wait_for_selector(".export-option")
    assert store(page, "s.doc.stickers.length") == stickers
    assert store(page, "s.doc.sheets[0].pages[0].items.length") > 0

    assert page.external_requests == [], page.external_requests
    assert not [e for e in page.js_errors if "favicon" not in e], page.js_errors


def test_every_screen_renders_without_errors(page):
    page.goto(page.base + "/")
    page.click("#sample-project")
    page.click('[data-sample="space"]')
    page.wait_for_url("**/editor", timeout=60000)
    page.wait_for_selector("#canvas canvas")
    pid = page.url.split("/p/")[1].split("/")[0]
    for view in ("photos", "extract", "edit", "themes", "variants", "editor", "library", "sheet", "export"):
        page.goto(f"{page.base}/#/p/{pid}/{view}")
        page.wait_for_selector("#view > *", timeout=15000)
        page.wait_for_timeout(400)
    # Rapid navigation must not let a half-loaded view touch the next one.
    for view in ("sheet", "editor", "variants", "sheet", "export", "editor", "photos") * 2:
        page.evaluate(f"location.hash = '#/p/{pid}/{view}'")
        page.wait_for_timeout(60)
    page.wait_for_selector(".photo-grid, .empty", timeout=15000)
    page.wait_for_timeout(1500)
    for screen in ("settings", "status", "help", "projects"):
        page.goto(f"{page.base}/#/{screen}")
        page.wait_for_selector("#view h1, #view h2", timeout=15000)
    assert page.external_requests == []
    assert not page.js_errors, page.js_errors


def test_one_click_themed_sheet(page, tmp_path):
    """Photo + word art + props + decoration stickers, generated and placed on A4 in one click."""
    photo_path = tmp_path / "figure.jpg"
    photo_path.write_bytes(jpeg_bytes(figure_image((800, 1000))))
    page.goto(page.base + "/")
    page.click("#new-project")
    page.fill("#np-name", "Recipe")
    page.select_option("#np-theme", "birthday")
    page.click("text=Create project")
    page.wait_for_url("**/photos")
    page.set_input_files("#file", str(photo_path))
    page.wait_for_selector(".photo-card", timeout=30000)
    page.click("#rail >> text=Variants")
    page.select_option("#number", "6")
    page.click("#recipe")
    page.wait_for_url("**/sheet", timeout=120000)
    page.wait_for_function("() => window.oss.store.doc.sheets[0].pages[0].items.length >= 10", timeout=60000)
    kinds = store(page, "s.doc.stickers.map((x) => x.variant.composition)")
    assert {"wordart", "decoration", "wordart-under"} <= set(kinds)
    assets = store(page, "s.doc.stickers.flatMap((x) => x.layers.map((l) => l.assetId)).filter(Boolean)")
    assert "balloon_number_6" in assets and not [a for a in assets if a.startswith("balloon_number_") and a != "balloon_number_6"]
    texts = store(page, "s.doc.stickers.flatMap((x) => x.layers.filter((l) => l.type === 'text').map((l) => l.text))")
    assert not [t for t in texts if t.lower() in ("boy", "girl")], "gendered wording only when chosen"
    assert page.external_requests == [] and not page.js_errors, page.js_errors


def test_bulk_import_and_templates(page, tmp_path):
    """Import several images as stickers at once, then save/reuse a template."""
    from PIL import Image, ImageDraw

    paths = []
    for i, color in enumerate([(255, 79, 139, 255), (76, 201, 240, 255), (6, 214, 160, 255)]):
        im = Image.new("RGBA", (280, 280), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse((30, 30, 250, 250), fill=color)
        fp = tmp_path / f"s{i}.png"
        im.save(fp)
        paths.append(str(fp))

    page.goto(page.base + "/")
    page.click("#new-project")
    page.fill("#np-name", "Bulk")
    page.click("text=Create project")
    page.wait_for_url("**/photos")
    page.wait_for_function("() => window.oss.store.doc")
    pid = store(page, "s.doc.id")
    page.goto(f"{page.base}/#/p/{pid}/editor")
    page.wait_for_selector("#blank")
    page.click("#blank")
    page.wait_for_url("**/editor/**")
    page.wait_for_selector("#tray-more")

    page.click("#tray-more")
    page.click("text=Import images as stickers…")
    page.wait_for_selector(".modal-backdrop")
    page.set_input_files(".modal-backdrop input[type=file]", paths)
    page.click(".modal-foot .btn.primary")
    page.wait_for_function("() => window.oss.store.doc.stickers.length >= 4", timeout=60000)
    sources = store(page, "s.doc.stickers.map((x) => x.variant && x.variant.source)")
    assert sources.count("import") == 3
    # imported stickers each have exactly one asset layer
    assert store(page, "s.doc.stickers.filter((x) => x.variant && x.variant.source === 'import').every((x) => x.layers.length === 1 && x.layers[0].type === 'asset')")

    # save a template and instantiate it
    page.click("#tray-more")
    page.click("text=Save this sticker as a template")
    page.fill(".modal-backdrop input[type=text]", "Tpl")
    page.click(".modal-foot .btn.primary")
    page.wait_for_timeout(500)
    before = store(page, "s.doc.stickers.length")
    page.click("#tray-more")
    page.click("text=New sticker from template…")
    page.wait_for_selector("#ft-tpl")
    page.click(".modal-foot .btn.primary")
    page.wait_for_function(f"() => window.oss.store.doc.stickers.length === {before + 1}", timeout=30000)

    assert page.external_requests == [] and not page.js_errors, page.js_errors
