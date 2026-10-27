"""Development launcher.

    python scripts/run_local.py            # waitress, like the packaged app
    python scripts/run_local.py --dev      # Flask dev server with auto-reload (debugger stays off)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true", help="use the Flask reloader")
    parser.add_argument("--port", type=int, default=int(os.environ.get("OSS_PORT", 5173)))
    parser.add_argument("--data-dir", default=os.environ.get("OSS_DATA_DIR"))
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not args.dev:
        import importlib.util

        # app.py shares its name with the app/ package, so load it by path.
        spec = importlib.util.spec_from_file_location("oss_launcher", ROOT / "app.py")
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        argv = ["--port", str(args.port)] + (["--data-dir", args.data_dir] if args.data_dir else []) + (["--no-browser"] if args.no_browser else [])
        return entry.main(argv)
    from app import create_app

    application = create_app({"data_dir": args.data_dir} if args.data_dir else None)
    # The interactive debugger is never enabled: it would allow code execution.
    application.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=True, use_debugger=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
