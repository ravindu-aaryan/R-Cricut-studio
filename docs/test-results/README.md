# Recorded test results

Environment: Linux x86_64 container, 4 CPU cores, no GPU, Python 3.12.3,
Chromium 1243 driven by Playwright 1.63.0.

| Run | Command | Result |
| --- | --- | --- |
| Full suite | `python -m pytest -q -rA` | **205 passed** in ~55 s ([pytest-full.txt](pytest-full.txt), [junit.xml](junit.xml)) |
| Offline verification | `python scripts/verify_offline.py` | Static scan **PASS**; integration + browser tests in a network namespace with no internet route: **31 passed** ([offline-verification.txt](offline-verification.txt)) |
| Packaging (Linux) | `python scripts/package_app.py` | PyInstaller one-folder build plus smoke test **passed** ([packaging-linux.txt](packaging-linux.txt)); the packaged binary was also run inside the no-network namespace (status, project creation and asset rendering all worked) |

Breakdown of the full suite:

| File | Tests |
| --- | --- |
| tests/unit/test_adjustments.py | 22 |
| tests/unit/test_paths_security.py | 20 |
| tests/unit/test_outline.py | 17 |
| tests/unit/test_project_model.py | 13 |
| tests/unit/test_segmentation.py | 12 (includes a tiny generated ONNX model) |
| tests/unit/test_sticker_render.py | 11 |
| tests/unit/test_validation.py | 10 |
| tests/unit/test_layout.py | 9 |
| tests/unit/test_assets_themes.py | 9 |
| tests/unit/test_photo_service.py | 8 |
| tests/unit/test_svg.py | 8 |
| tests/unit/test_units.py | 6 |
| tests/unit/test_jobs.py | 5 |
| tests/unit/test_offline_static.py | 2 |
| tests/unit/test_disk.py | 1 |
| tests/unit/test_wordart_collections.py | 5 |
| tests/integration/test_security.py | 19 |
| tests/integration/test_workflow.py | 7 (includes HEIC import via the optional decoder) |
| tests/integration/test_offline.py | 3 |
| tests/e2e/test_browser.py | 3 (main workflow, every screen + rapid navigation, one-click themed sheet) |

The two `ERROR` log lines in `pytest-full.txt` come from tests that trigger
errors on purpose (a failing job and a hidden internal error); both tests
pass.

Not covered here: macOS and Windows packaging (they must be built on those
systems) and printing on a physical printer or Cricut machine.
