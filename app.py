"""Offline Sticker Studio – start the local application.

Runs a production WSGI server (waitress) bound to 127.0.0.1 and opens the
interface in the default browser. The Flask debugger is never enabled here.

    python app.py [--port 5173] [--no-browser] [--data-dir PATH]
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser


def _free_port(host: str, preferred: int) -> int:
    for port in [preferred, *range(preferred + 1, preferred + 40)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise SystemExit(f"No free port near {preferred}. Close other copies of the app and try again.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Sticker Studio")
    parser.add_argument("--port", type=int, default=None, help="port to listen on (default 5173)")
    parser.add_argument("--host", default=None, help="interface to bind (default 127.0.0.1; do not expose publicly)")
    parser.add_argument("--data-dir", default=None, help="folder for projects and settings")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    args = parser.parse_args(argv)

    from app import create_app
    from app.version import APP_NAME, APP_VERSION

    overrides = {"debug": False, "allow_quit": True}
    if args.data_dir:
        overrides["data_dir"] = args.data_dir
    if args.host:
        overrides["host"] = args.host
    try:
        application = create_app(overrides)
    except Exception as exc:  # pragma: no cover - startup diagnostics
        print(f"{APP_NAME} could not start: {exc}", file=sys.stderr)
        return 1
    settings = application.extensions["oss"].settings
    missing = []
    for path in (settings.frontend_dir / "templates" / "index.html", settings.assets_dir / "themes", settings.assets_dir / "fonts"):
        if not path.exists():
            missing.append(str(path))
    if missing:
        print("Bundled resources are missing:\n  " + "\n  ".join(missing), file=sys.stderr)
        return 2
    host = settings.host
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(f"WARNING: listening on {host}. Other devices on your network may reach the app.", file=sys.stderr)
    port = _free_port(host, args.port or settings.port)
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}/"
    print(f"{APP_NAME} {APP_VERSION}")
    print(f"  Open {url}")
    print(f"  Data folder: {settings.data_dir}")
    print("  Works offline. Press Ctrl+C to quit.")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    from waitress import serve

    serve(application, host=host, port=port, threads=8, ident=None, clear_untrusted_proxy_headers=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
