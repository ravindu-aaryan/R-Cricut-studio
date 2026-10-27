# Offline Sticker Studio

Offline Sticker Studio turns your own photos into die-cut stickers, themed
sticker collections and print-ready A4 sheets for Cricut *Print Then Cut*
or any printer.

It runs entirely on your computer. There is no cloud service, no generative
AI, no account, no API key and no telemetry. Photos never leave the machine.
The interface is a local web page served from `127.0.0.1`, and every font,
script, icon, theme and decoration is bundled.

## What it does

| Step | Features |
| --- | --- |
| **Photos** | Import JPEG, PNG, WebP, TIFF (and HEIC with the optional local decoder). Contents are validated (magic bytes plus a full decode) and size-limited. EXIF orientation is corrected and transparency is preserved. The original file is stored byte for byte; a separate working copy is derived from it. |
| **Cut out** | Four local engines. *Auto*: OpenCV GrabCut with a rectangle and red/blue keep/remove hint brushes. *Manual*: paint the mask directly. *Plain background*: colour key. *Model*: an optional local ONNX model, never downloaded. Brush sizes, eraser, undo/redo, zoom/pan. Refinement: feather, smooth, grow/shrink, hole filling, speck removal, guided-filter edge refinement for hair, and edge colour decontamination. Preview on light and dark backgrounds. Export as a transparent PNG. |
| **Adjust** | Crop, rotate 90°, straighten, flip, downscale. Exposure, brightness, contrast, highlights, shadows, saturation, temperature, sharpness, blur and vignette. Filters: grayscale, sepia, black and white, posterize, cartoon (bilateral + ink edges), duotone. Adjust the whole photo, only the subject, or only the background. Background replacement: transparent, solid, gradient or pattern. Everything is non-destructive, stored as settings and re-applied to the original. |
| **Face safety** | Face regions (suggested by OpenCV's bundled Haar cascade, editable by hand) stay untouched by colour filters and are never cut by automatic crops. Photo layers always scale uniformly. Accessories are separate layers placed using the face region; faces are never warped. |
| **Themes** | 21 themes: Birthday, Mr. Gentleman, Superhero, Space, Jungle Adventure, Dinosaur, Princess and Fairytale, Cute Animals, School, Sports, Christmas, Halloween, Diwali, Pongal, Wedding and Celebration, Minimalist Labels, Hearts and Friendship, Rainbow and Pastel, Retro Pop, Fairytale Ball (blue), Custom. Each defines a palette, fonts, decorations, accessory sets, frames, border/shadow defaults, layout presets, sizes, text ideas and licence information. You can also create your own. |
| **Assets** | 161 original SVG decorations and 11 frames (crowns, party hats, hats, balloons, confetti, stars, hearts, sunglasses, bow ties, mustaches, flowers, cakes, gifts, ribbons, banners, speech bubbles, school, sports, seasonal, Diwali/Pongal, space, jungle, dinosaurs, animals, fairytale, wedding, shapes, badges, gold number balloons 0–9, gift stacks, teddy, party glasses, fedora, mustache-on-a-stick, vintage car, castle, glass slipper, pumpkin carriage, roses, ornate/floral/gold-heart frames, scroll banners, emphasis "action lines"), plus 12 recolourable patterns. Searchable by name, category and tag. Import your own PNG or SVG; SVGs are sanitised. |
| **Editor** | Konva canvas with an explicit JSON document model: move, resize, rotate, flip, duplicate, delete, layer order, lock, hide, opacity, recolour, align, group/ungroup, marquee and multi-select, snapping guides, rulers in mm, safe-area and shape guides, zoom/pan, in-app copy/paste, context menu, keyboard shortcuts, undo/redo, in-place text editing, reusable presets, a variant tray, and a live server-rendered border preview. Autosave with crash recovery. |
| **Word art** | Multi-colour lettering (each letter cycles through a palette, with a dark outline), and theme word-art designs such as "Birthday BOY", "HAPPY BIRTHDAY", "PARTY MODE ON", "Make a Wish", "Mr. Gentleman", "Little Gentleman", "Little Princess" on a scroll, "Born to be a Princess" and "Princess Vibes". Add one to a sticker or make it its own sticker in one click. Phrases only appear if you pick them, and gendered wording is never pre-selected. |
| **Text** | Bundled OFL/Apache fonts plus installed system fonts. Size, weight, letter spacing, line height, alignment, wrapping, colour, outline, shadow, background badge and curved text. Theme text presets; only text you choose is used. |
| **Shapes & borders** | Die-cut silhouette, circle, oval, rounded rectangle, rectangle, square, heart, star, speech bubble, or a custom shape from any asset. White border of any width, multiple coloured outline rings with adjustable gaps, smoothing, hole filling, joining separate pieces into one sticker, a printed shadow (art on the border) or a preview-only shadow, and a cut-line offset. |
| **Variants** | Deterministic, seeded generation from photos × shapes × borders × compositions (full, word art under the photo, photo + prop, emphasis lines, face close-up, title on top, framed, scattered, round badge) × accessories × decorations × backgrounds × text × colour treatments. It can also add word-art-only and decoration-only stickers, and a number balloon, but only the digit you choose; ages are never guessed. **Full themed sheet in one click** builds a mixed collection like a professional party sheet and places it on A4. Preview, edit, duplicate, remove, add to the project or send straight to an A4 sheet. It never claims to create new poses, faces or outfits. |
| **A4 sheets** | Portrait/landscape A4 (210 × 297 mm; 2480 × 3508 px at 300 DPI). Printable-area presets: printer margins, Cricut Print Then Cut 6.75 × 9.25 in, or borderless. Margins, gaps, page colour, footer label. Grid, space-efficient packing (MaxRects with 90° rotation), fill page, fit to page, and manual drag/resize/rotate with snapping. Alignment, duplicate, multi-page. Live validation: overlaps, outside printable area, off page, low resolution, enlarged photos. Server-rendered print preview. |
| **Export** | Individual transparent PNG stickers (DPI stored, true size) plus ZIP. A4 PNG pages. Exact-A4 PDF (transparent images, optional cut lines, embedded footer font). A4 SVG with artwork and a separate cut-path group. Cut-only SVG. Individual SVG stickers. A Cricut bundle. A `.ossproj` project archive. Export history and in-app previews. |

## Requirements

* **OS:** macOS 12+ (Apple Silicon or Intel), Windows 10/11, or a modern Linux.
* **Python:** 3.11 or newer, for running from source (tested with 3.12.3).
* **Hardware:** any laptop from the last ~7 years. 8 GB RAM is recommended; 4 GB works for photos up to about 12 MP. No GPU, CUDA or internet connection is needed.
* **Disk:** about 350 MB for the packaged app (about 600 MB for a source install with dev tools). Projects need roughly 3–5× the size of their photos: original, working copy, cut-out, previews and exports. Exports refuse to start below 200 MB free.
* **Browser:** the interface opens in your default browser (Chrome, Edge, Firefox or Safari, current versions).

## Quick start (from source)

### macOS / Linux

```bash
./scripts/setup_dev.sh            # creates .venv, installs pinned deps, initialises the database
.venv/bin/python app.py           # starts on http://127.0.0.1:5173 and opens the browser
```

On macOS you can also double-click `scripts/macos/Offline Sticker Studio.command`.

### Windows (PowerShell)

```powershell
.\scripts\windows\setup_dev.ps1
.\.venv\Scripts\python app.py
```

### Manual setup

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt     # or requirements.txt for runtime only
.venv/bin/python scripts/init_db.py               # creates the data folder and SQLite schema
.venv/bin/python app.py [--port 5173] [--data-dir PATH] [--no-browser]
```

`python scripts/run_local.py --dev` starts the Flask development server with
auto-reload. The interactive debugger stays disabled even in development.

Optional extras (`requirements-optional.txt`): `pillow-heif` for HEIC photos,
and `onnxruntime` plus a model file in `models/` for the model engine (see
`models/README.md`).

## Where your files are

| What | Location (source install) | Location (packaged app) |
| --- | --- | --- |
| Projects | `./data/projects/<id>/` | macOS `~/Library/Application Support/OfflineStickerStudio/projects`, Windows `%APPDATA%\OfflineStickerStudio\projects`, Linux `~/.local/share/offline-sticker-studio/projects` |
| Imported assets, presets, custom themes | `./data/library/` | `…/library/` |
| Metadata database | `./data/studio.sqlite3` | `…/studio.sqlite3` |
| Logs (local only) | `./data/logs/app.log` | `…/logs/app.log` |

Override the location with `--data-dir` or the `OSS_DATA_DIR` environment
variable. Each project folder contains `project.json` (the editable
document), `originals/` (untouched uploads), `working/`, `previews/`,
`thumbs/`, `masks/`, `subjects/` and `exports/`. Large images are never
stored in SQLite. **Settings → Delete all local data** removes everything.

## Packaging

PyInstaller builds a self-contained application **folder** rather than a
single file. Bundled fonts, themes and assets stay as plain files, and the
app starts quickly and reliably. Nothing is downloaded at runtime.

```bash
# macOS (build on the architecture you target; produces .app and .dmg)
./scripts/macos/build_macos.sh

# Windows
.\scripts\windows\build_windows.ps1        # dist\OfflineStickerStudio\OfflineStickerStudio.exe + .zip

# Linux
.venv/bin/python scripts/package_app.py    # dist/OfflineStickerStudio/ + .tar.gz
```

The build script starts the packaged app with no browser and checks that the
interface and every bundled resource load (a smoke test). The macOS app is
not code-signed: on first launch, right-click it and choose **Open**, or sign
it with your own Developer ID. The packaged app shows a **Quit** button in
Settings.

## Cricut Print Then Cut workflow

1. **Recommended:** export *Individual PNG stickers*. In Cricut Design Space,
   choose *Upload → Upload Image*, select a PNG, choose *Complex* and keep the
   transparent background, then save it as a *Print Then Cut image*.
2. Check the size on the canvas. The PNGs carry 300 DPI, but some Design Space
   versions ignore it, so enter the width in mm or inches if needed. Then
   duplicate the stickers and click *Make It*. Design Space lays out the page
   and adds its own registration marks.
3. Print from Design Space with bleed on and scaling at 100 %, then cut.
4. **SVG route:** the sticker SVGs contain the artwork as an embedded image
   and the cut path as a separate magenta group, in millimetres. Design
   Space may import them as separate layers that you need to *Flatten*.
5. **A4 PDF/PNG** are for normal printing and cutting by hand or with other
   machines. Print Then Cut limits the printable area (6.75 × 9.25 in on
   many machines), so use the *Cricut Print Then Cut* printable-area preset
   on the sheet if you want to stay inside it.

Compatibility depends on your machine and Design Space version. No file is
guaranteed to work in every version, so always test with one sheet first.
Always print at **100 % / Actual size**.

## Architecture

```
app.py                         launcher: waitress on 127.0.0.1, opens the browser
app/
  __init__.py                  Flask factory, Host/Origin/CSRF guards, security headers
  config.py  version.py        settings (JSON + env), resource/data locations
  routes/                      thin HTTP layer: projects, photos, stickers, themes, assets, layouts, exports, jobs, system
  services/                    image processing and domain logic, independent of Flask
    photo_service.py           import, validation, EXIF, working copies, previews, face suggestions
    segmentation_service.py    manual / GrabCut / colour key / optional ONNX, mask refinement, decontamination
    image_adjustments.py       non-destructive adjustment and filter pipeline
    outline_service.py         shape masks, die-cut borders, outlines, shadows (distance transform, morphology)
    text_service.py            font registry and text rendering (wrap, spacing, outline, shadow, curve)
    asset_service.py           asset library, recolouring, resvg rasterising, user imports
    theme_service.py           themes and custom themes
    sticker_service.py         authoritative renderer: layers → affine composition → border → cut mask
    variation_service.py       seeded, template-based collection generation
    layout_service.py          grid, MaxRects packing, fit/fill, validation (SAT overlap tests)
    print_service.py           page PNG and exact-size ReportLab PDF
    svg_cut_service.py         contour tracing, simplification with self-intersection guard, SVG output
    export_service.py          export orchestration and render cache
    project_service.py         project folders, versioned documents, migration, autosave/recovery, archives
    job_service.py             bounded worker pool, progress, cancellation, timeouts, error mapping
  models/                      typed dataclasses for layers, stickers and sheets (camelCase JSON)
  repositories/                SQLite metadata: projects, export history, preferences (versioned schema)
  utils/                       units, paths, validation, SVG sanitiser, security, disk checks
frontend/                      HTML shell, CSS design system, ES-module views, vendored Konva
assets/                        fonts (+licences), themes, decorations, frames, patterns (CC0, generated by scripts/build_assets.py)
scripts/                       run_local, init_db, package_app, verify_offline, build_assets, platform helpers
tests/                         unit, integration, e2e (Playwright), synthetic fixtures
```

* The **server-side renderer is authoritative**. Previews, exports and print
  all use it. The browser editor draws the same document with Konva, using
  the same font files (`/fonts.css`) and SVG assets, and shows the
  server-rendered border underneath the live artwork.
* **Heavy work runs on the job pool** (2 threads by default) and is polled
  by the UI with progress and a working Cancel button. Small previews use the
  same pool synchronously, so request threads never do CPU-heavy work.
* The segmentation engine and the canvas library are behind narrow
  interfaces (`run_segmentation(method, …)` and `StickerCanvas`), so either
  can be replaced independently.

### Project format

`project.json` holds `formatVersion` (currently 2), `appVersion`, photos
(server-authoritative file references plus editable adjustments), stickers
(artboard in mm, DPI, shape, border, shadow, background, cut offset and
layers), sheets (orientation, printable area, margins, gaps and pages of
items in mm), the collection options and seed, presets and export settings.
Older formats are migrated on load (v1 → v2 is implemented and tested).
Newer formats are refused with a clear message. A `.ossproj` archive is a ZIP
with `project.json`, `manifest.json` and the project's images (relative
paths), plus any user-imported assets it references. The manifest records
the project and app versions, canvas and page dimensions, asset references,
layer counts, theme and export settings. Import ignores unexpected or
path-traversing entries.

## Security & privacy

* The server binds to **127.0.0.1** by default and runs waitress. The Flask
  debugger is never enabled.
* State-changing requests need a per-launch **CSRF token**. The **Host**
  header must be a local name (protects against DNS rebinding), and foreign
  **Origin** headers are rejected.
* A strict **Content-Security-Policy** applies (`default-src 'self'`, no
  remote scripts or fonts, no framing). SVG responses are additionally
  sandboxed.
* Uploads are validated by their actual contents and size-limited. File
  names are sanitised. API parameters are opaque ids, never paths, and every
  file access goes through `safe_join` (blocks `..` and symlink escapes).
  Imported SVGs are rebuilt from an allow-list using defusedxml: scripts,
  event handlers, `foreignObject`, external references and entities are
  removed.
* Error responses never contain tracebacks; details go to the local log.
* No telemetry and no network requests. Binding to localhost does **not**
  remove every risk: other software running on your computer can still reach
  the local port, which is why the CSRF and Host checks exist.

## Tests

```bash
.venv/bin/python -m pytest                    # unit + integration + browser e2e
.venv/bin/python -m pytest tests/unit         # fast
.venv/bin/python scripts/verify_offline.py    # static scan + tests inside a no-network namespace (Linux)
```

* **Unit:** mm/px/pt conversion, A4 sizes, EXIF orientation, transparency,
  validation, path sanitising, mask processing, GrabCut accuracy (IoU),
  border width and outline geometry, compositing and layer order, group
  transforms, text, serialisation and migration, recovery, photo-record
  integrity, SVG sanitising, cut-path geometry and self-intersection, layout
  packing and validation, jobs (cancel, timeout, concurrency), assets and
  themes, and an optional ONNX model path using a tiny generated model.
* **Integration:** the full HTTP workflow: create project → import →
  GrabCut → generate stickers from local assets → save/reopen → A4 layout →
  PNG/PDF/SVG/ZIP/archive exports. It checks real pixel sizes and DPI
  metadata, PDF MediaBox (595.276 × 841.89 pt), SVG mm units and cut groups,
  archive round-trips with user assets, malicious archives, and security
  behaviour.
* **Offline:** the same workflow with a socket guard that blocks every
  non-loopback connection and DNS lookup. `verify_offline.py` also runs the
  integration and browser tests inside `unshare -rn`, a network namespace
  with only loopback, where the internet is unreachable at the OS level.
* **End-to-end:** Playwright drives the real packaged server (waitress via
  `app.py`) through import → cut-out → editor (add text, undo/redo, asset,
  shortcuts, preview, save) → variants → A4 sheet → PDF and PNG export →
  reload. Every non-local request is aborted and fails the test, as does any
  JavaScript error. A second test opens every screen, including rapid
  navigation.

Recorded results are in `docs/test-results/`.

## Limitations

* **Automatic segmentation** (GrabCut, colour key) is classic computer
  vision. It works well when the subject contrasts with the background, but
  needs brush touch-ups for busy scenes, similar colours or wispy hair. The
  optional model engine is only as good as the model you install.
* **No new poses, outfits or expressions.** Professional sheets that show a
  child in many different poses, costumes, hugging a teddy or holding gifts
  are either separate photos or generated images. This app composites:
  every pose comes from a photo you import, and props are placed beside or
  in front of the child. For a varied sheet, import 4–8 photos with
  different poses and expressions.
* **Face detection** (Haar cascade) only makes suggestions: it misses
  profiles, small or partly covered faces. Check and edit the face regions.
* Canvas text preview uses the same fonts as the renderer, but browser and
  FreeType layout can differ by a pixel or two. Curved text may sit slightly
  differently. The Preview tab shows the exact result.
* HEIC needs the optional `pillow-heif` decoder. RAW camera files are not
  supported.
* The PDF contains stickers as high-resolution images. Text is rasterised
  into the artwork, not live text.
* Cricut Design Space behaviour varies by version and machine (see above).
* Packaging was built and smoke-tested on **Linux only** (including a run of
  the packaged app with no network). The macOS `.app`/`.dmg` and Windows
  builds use the same `package_app.py` (`--windowed` + `hdiutil` on macOS)
  but have not been built in this environment. Build and test them on the
  target OS; PyInstaller cannot cross-compile.

## Development notes

* `python scripts/build_assets.py` regenerates the decoration SVGs, patterns
  and theme files.
* Logs: `<data>/logs/app.log`. The Status page shows versions, model
  availability, storage and resource checks.

## Licence

MIT for the application code. See [LICENSES.md](LICENSES.md) for bundled
fonts, artwork and dependencies.
