#!/usr/bin/env bash
# Build "Offline Sticker Studio.app" and a .dmg on macOS (run on the target architecture: arm64 or x86_64).
set -euo pipefail
cd "$(dirname "$0")/../.."
[ -x .venv/bin/python ] || ./scripts/setup_dev.sh
.venv/bin/python scripts/package_app.py --dmg
echo "Open dist/ to find the .app and the .dmg."
echo "The app is not code-signed. On first launch, right-click the app and choose Open, or sign it with your Developer ID."
