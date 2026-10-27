"""Console entry point (``offline-sticker-studio``) that mirrors ``python app.py``."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def main() -> int:
    launcher = Path(__file__).resolve().parent.parent / "app.py"
    spec = importlib.util.spec_from_file_location("oss_launcher", launcher)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.main()
