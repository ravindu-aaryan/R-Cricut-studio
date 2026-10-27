# Licences

Offline Sticker Studio bundles only resources whose licences allow
redistribution. This file lists them; full licence texts for the fonts are in
`assets/fonts/licenses/`, and Konva's licence is in
`frontend/static/vendor/KONVA-LICENSE.txt`.

## Application code

The Offline Sticker Studio source code in this repository is released under
the **MIT licence**.

## Bundled artwork (decorations, frames, patterns, themes, app icon)

Every SVG in `assets/decorations`, `assets/frames` and `assets/patterns`, the
theme definitions in `assets/themes`, and the app icon were drawn for this
project from simple geometric primitives (`scripts/build_assets.py`). They are
dedicated to the public domain under **CC0 1.0**. They contain no copyrighted
characters, logos or commercial artwork: the "Superhero" theme uses generic
capes, masks, lightning bolts and comic bursts, not any franchise's designs.

User-imported assets keep whatever licence they came with. Only import
artwork you have the right to use.

## Fonts (`assets/fonts`)

| Font | Licence | Copyright |
| --- | --- | --- |
| Poppins (Regular, SemiBold, Bold) | SIL Open Font License 1.1 | © 2020 The Poppins Project Authors |
| Pacifico | SIL OFL 1.1 | © 2018 The Pacifico Project Authors |
| Lobster | SIL OFL 1.1 (Reserved Font Name "Lobster") | © 2010 The Lobster Project Authors |
| Bangers | SIL OFL 1.1 | © 2010 The Bangers Project Authors |
| Great Vibes | SIL OFL 1.1 | © 2015 The Great Vibes Pro Project Authors |
| Creepster | SIL OFL 1.1 | © 2011 Font Diner, Inc |
| Luckiest Guy | Apache License 2.0 | Astigmatic |
| Chewy | Apache License 2.0 | Sideshow |
| Permanent Marker | Apache License 2.0 | Font Diner, Inc |

All of them allow embedding in documents. The PDF footer label embeds a
subset of Poppins. Sticker text is rasterised into the artwork.

## Frontend library (vendored, no CDN)

| Library | Version | Licence |
| --- | --- | --- |
| Konva | 9.3.22 | MIT |

## Python runtime dependencies

| Package | Version | Licence |
| --- | --- | --- |
| Flask | 3.1.3 | BSD-3-Clause |
| Werkzeug | 3.1.9 | BSD-3-Clause |
| Jinja2 | 3.1.6 | BSD-3-Clause |
| itsdangerous | 2.2.0 | BSD-3-Clause |
| click | 8.5.0 | BSD-3-Clause |
| blinker | 1.9.0 | MIT |
| MarkupSafe | 3.0.4 | BSD-3-Clause |
| waitress | 3.0.2 | Zope Public License 2.1 |
| Pillow | 13.0.0 | MIT-CMU (HPND) |
| NumPy | 2.2.6 | BSD-3-Clause |
| opencv-python-headless | 4.12.0.88 | Apache 2.0 (includes OpenCV's Haar cascade data under the Intel/BSD licence) |
| ReportLab | 5.1.0 | BSD |
| resvg-py | 0.5.0 | MIT (wraps resvg, Apache-2.0 OR MIT) |
| defusedxml | 0.7.1 | PSF |

Optional: `pillow-heif` 1.8.1 (BSD-3-Clause; uses libheif, LGPL-3.0) for
HEIC photos, and `onnxruntime` 1.31.1 (MIT) for a local segmentation model.

Development only: pytest (MIT), pypdf (BSD), Playwright (Apache-2.0),
PyInstaller (GPL-2.0-or-later with a bootloader exception, so applications
built with it may use any licence).

## Segmentation models

No segmentation model is bundled. If you add one to `models/`, its licence
applies. Check that it allows your use.
