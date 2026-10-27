"""Build a self-contained application folder with PyInstaller (no runtime downloads).

    python scripts/package_app.py            # build for the current OS into dist/
    python scripts/package_app.py --dmg      # macOS: also create a .dmg disk image
    python scripts/package_app.py --no-test  # skip the post-build smoke test

macOS produces ``dist/Offline Sticker Studio.app`` (a windowless app that
opens the browser) plus the ``dist/OfflineStickerStudio`` folder. Windows and
Linux produce ``dist/OfflineStickerStudio/`` with the executable inside, and
an archive next to it. A one-folder build is used on purpose: bundled
resources stay as plain files and start-up is fast and reliable.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "OfflineStickerStudio"
DATA = [("frontend", "frontend"), ("assets", "assets"), ("config", "config"), ("models/README.md", "models"),
        ("LICENSES.md", "."), ("README.md", ".")]


def make_icns() -> Path | None:
    """macOS: render the SVG app icon to an .icns with iconutil (both ship with macOS/Python deps)."""
    if sys.platform != "darwin" or not shutil.which("iconutil"):
        return None
    sys.path.insert(0, str(ROOT))
    from app.services.asset_service import rasterize_svg

    svg = (ROOT / "frontend" / "static" / "icons" / "app-icon.svg").read_text(encoding="utf-8")
    iconset = ROOT / "build" / "AppIcon.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        rasterize_svg(svg, size, size).save(iconset / f"icon_{size}x{size}.png")
        rasterize_svg(svg, size * 2, size * 2).save(iconset / f"icon_{size}x{size}@2x.png")
    out = ROOT / "build" / "AppIcon.icns"
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)
    return out


def build(clean: bool = True) -> Path:
    sep = ";" if os.name == "nt" else ":"
    args = [sys.executable, "-m", "PyInstaller", str(ROOT / "app.py"), "--name", NAME, "--noconfirm", "--onedir",
            "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build")]
    if clean:
        args.append("--clean")
    for src, dst in DATA:
        if (ROOT / src).exists():
            args += ["--add-data", f"{ROOT / src}{sep}{dst}"]
    for mod in ("resvg_py", "waitress", "defusedxml", "app.routes.assets", "app.routes.exports", "app.routes.jobs",
                "app.routes.layouts", "app.routes.photos", "app.routes.projects", "app.routes.stickers",
                "app.routes.system", "app.routes.themes"):
        args += ["--hidden-import", mod]
    args += ["--collect-data", "reportlab", "--collect-data", "cv2", "--exclude-module", "tkinter", "--exclude-module", "pytest",
             "--exclude-module", "playwright"]
    for optional in ("pillow_heif", "onnxruntime"):
        try:
            __import__(optional)
            args += ["--collect-all", optional]
        except ImportError:
            pass
    if sys.platform == "darwin":
        args += ["--windowed", "--osx-bundle-identifier", "app.offlinestickerstudio"]
        icon = make_icns()
        if icon:
            args += ["--icon", str(icon)]
    print("Running:", " ".join(args))
    subprocess.run(args, check=True, cwd=ROOT)
    return ROOT / "dist" / NAME


def executable(folder: Path) -> Path:
    exe = folder / (NAME + (".exe" if os.name == "nt" else ""))
    if not exe.exists():
        raise SystemExit(f"Build output not found: {exe}")
    return exe


def smoke_test(folder: Path) -> None:
    """Start the built app without a browser and check that it serves the UI and its resources."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    data = ROOT / "build" / "smoke-data"
    shutil.rmtree(data, ignore_errors=True)
    proc = subprocess.Popen([str(executable(folder)), "--no-browser", "--port", str(port), "--data-dir", str(data)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):
            try:
                with urllib.request.urlopen(base + "/api/status", timeout=1) as r:
                    import json

                    status = json.loads(r.read())
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise SystemExit("Smoke test failed: the packaged app did not start.\n" + (proc.stdout.read() if proc.stdout else ""))
        if status["missingResources"]:
            raise SystemExit(f"Smoke test failed: missing resources {status['missingResources']}")
        with urllib.request.urlopen(base + "/api/assets/crown_gold/png?w=64") as r:
            assert r.read(8) == b"\x89PNG\r\n\x1a\n"
        print(f"Smoke test passed: {status['resources']}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def archive(folder: Path, dmg: bool) -> Path:
    system = {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")
    stem = ROOT / "dist" / f"{NAME}-1.0.0-{system}-{platform.machine().lower()}"
    if sys.platform == "darwin" and dmg:
        app = ROOT / "dist" / f"{NAME}.app"
        out = stem.with_suffix(".dmg")
        subprocess.run(["hdiutil", "create", "-volname", "Offline Sticker Studio", "-srcfolder", str(app), "-ov", "-format", "UDZO", str(out)], check=True)
        return out
    if os.name == "nt":
        out = stem.with_suffix(".zip")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for f in folder.rglob("*"):
                z.write(f, f.relative_to(folder.parent))
        return out
    out = Path(str(stem) + ".tar.gz")
    with tarfile.open(out, "w:gz") as t:
        t.add(folder, arcname=folder.name)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dmg", action="store_true", help="macOS: create a .dmg")
    ap.add_argument("--no-test", action="store_true")
    ap.add_argument("--no-archive", action="store_true")
    args = ap.parse_args()
    folder = build()
    if not args.no_test:
        smoke_test(folder)
    if not args.no_archive:
        print("Archive:", archive(folder, args.dmg))
    print("Built:", folder)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
