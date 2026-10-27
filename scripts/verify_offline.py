"""Verify that Offline Sticker Studio works without network access.

1. Static check: no remote URLs are referenced by the interface (HTML/CSS/JS)
   and the Python code imports no HTTP client libraries.
2. Runtime check: run the integration workflow and the browser end-to-end
   tests inside a Linux network namespace that has only a loopback device
   (``unshare -rn``), so any network request fails at the OS level. Where
   namespaces are unavailable (macOS, Windows), the socket-guard offline
   tests run instead.

Writes a report to docs/test-results/offline-verification.txt.

    python scripts/verify_offline.py [--static-only]
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL_RE = re.compile(r"""(?:https?:)?//[a-z0-9.-]+\.[a-z]{2,}[^\s"')]*""", re.I)
# XML namespace identifiers are names, not network requests.
ALLOWED_URLS = ("http://www.w3.org/2000/svg", "http://www.w3.org/1999/xlink", "http://www.w3.org/XML/1998/namespace")
CLIENT_IMPORTS = re.compile(r"^\s*(import|from)\s+(requests|httpx|urllib3|aiohttp|http\.client|urllib\.request|socket)\b", re.M)


def static_check() -> list[str]:
    problems = []
    for path in sorted((ROOT / "frontend").rglob("*")):
        if path.suffix not in (".html", ".js", ".css") or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "vendor" in path.parts:
            # Vendored libraries keep licence/banner comments with URLs; make sure
            # none is used as a resource (src/href/url()/import/fetch).
            if re.search(r"""(src|href)\s*=\s*["']https?://|url\(\s*["']?https?://|import\s*\(\s*["']https?://|fetch\(\s*["']https?://""", text):
                problems.append(f"{path.relative_to(ROOT)}: vendored file loads a remote resource")
            continue
        for m in URL_RE.finditer(text):
            url = m.group(0)
            if url.startswith(ALLOWED_URLS):
                continue
            problems.append(f"{path.relative_to(ROOT)}: remote URL {url}")
    for path in sorted((ROOT / "app").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for m in CLIENT_IMPORTS.finditer(text):
            problems.append(f"{path.relative_to(ROOT)}: imports network client '{m.group(2)}'")
    return problems


def runtime_check() -> tuple[bool, str]:
    pytest_cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/integration", "tests/e2e"]
    if sys.platform.startswith("linux") and shutil.which("unshare"):
        probe = subprocess.run(["unshare", "-rn", "true"], capture_output=True)
        if probe.returncode == 0:
            inner = (f"{sys.executable} {ROOT / 'scripts' / '_netns_lo_up.py'} && "
                     f"{sys.executable} -c \"import socket,sys; s=socket.socket(); s.settimeout(2); "
                     f"sys.exit(0 if s.connect_ex(('1.1.1.1', 80)) != 0 else 1)\" && " + " ".join(pytest_cmd))
            proc = subprocess.run(["unshare", "-rn", "sh", "-c", inner], cwd=ROOT, capture_output=True, text=True)
            return proc.returncode == 0, "network namespace (no internet route)\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/integration/test_offline.py"],
                          cwd=ROOT, capture_output=True, text=True)
    return proc.returncode == 0, "socket guard (network namespaces unavailable on this OS)\n" + proc.stdout[-4000:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--static-only", action="store_true")
    args = ap.parse_args()
    lines = [f"Offline verification — {dt.datetime.now().isoformat(timespec='seconds')}", f"Python {sys.version.split()[0]} on {sys.platform}", ""]
    problems = static_check()
    lines.append("Static check: " + ("PASS" if not problems else "FAIL"))
    lines += [f"  - {p}" for p in problems]
    ok = not problems
    if not args.static_only:
        passed, output = runtime_check()
        ok = ok and passed
        lines += ["", "Runtime check: " + ("PASS" if passed else "FAIL"), output]
    report = "\n".join(lines)
    out = ROOT / "docs" / "test-results" / "offline-verification.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
