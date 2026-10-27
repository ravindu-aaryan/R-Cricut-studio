"""Create the data folder and initialise/migrate the SQLite database.

    python scripts/init_db.py [--data-dir PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir")
    args = ap.parse_args()
    from app.config import load_settings
    from app.repositories.project_repository import ProjectRepository

    settings = load_settings({"data_dir": args.data_dir} if args.data_dir else None)
    settings.ensure_dirs()
    version = ProjectRepository(settings.db_path).migrate()
    print(f"Database ready (schema v{version}): {settings.db_path}")
    print(f"Projects folder: {settings.projects_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
