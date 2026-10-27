"""SQLite metadata store: projects, export history and UI preferences.

Only metadata lives here; images and documents are files in each project
folder. A connection is opened per operation, which is simple and safe
with the threaded server and background jobs.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 2

MIGRATIONS = {
    1: [
        """CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            opened_at REAL,
            archived INTEGER NOT NULL DEFAULT 0,
            theme_id TEXT,
            photo_count INTEGER NOT NULL DEFAULT 0,
            sticker_count INTEGER NOT NULL DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS exports (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            created_at REAL NOT NULL,
            folder TEXT NOT NULL,
            files TEXT NOT NULL,
            settings TEXT NOT NULL
        )""",
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    ],
    2: [
        "ALTER TABLE projects ADD COLUMN sheet_count INTEGER NOT NULL DEFAULT 0",
        "CREATE INDEX IF NOT EXISTS idx_exports_project ON exports(project_id, created_at)",
    ],
}


class ProjectRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.Lock()
        self.migrate()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def migrate(self) -> int:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            current = row["version"] if row else 0
            for version in range(current + 1, SCHEMA_VERSION + 1):
                for stmt in MIGRATIONS[version]:
                    conn.execute(stmt)
            if row is None:
                conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            else:
                conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
            return SCHEMA_VERSION

    # ---------------------------------------------------------------- projects
    def insert(self, pid: str, name: str, theme_id: str | None) -> None:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO projects (id, name, created_at, updated_at, opened_at, theme_id) VALUES (?, ?, ?, ?, ?, ?)",
                (pid, name, now, now, now, theme_id))

    def update_meta(self, pid: str, **fields) -> None:
        allowed = {"name", "updated_at", "opened_at", "archived", "theme_id", "photo_count", "sticker_count", "sheet_count"}
        cols = {k: v for k, v in fields.items() if k in allowed}
        if not cols:
            return
        sets = ", ".join(f"{k} = ?" for k in cols)
        with self.connect() as conn:
            conn.execute(f"UPDATE projects SET {sets} WHERE id = ?", (*cols.values(), pid))

    def get(self, pid: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
        return dict(row) if row else None

    def list(self, *, include_archived: bool = False, query: str = "") -> list[dict]:
        sql = "SELECT * FROM projects"
        where, args = [], []
        if not include_archived:
            where.append("archived = 0")
        if query:
            where.append("name LIKE ?")
            args.append(f"%{query}%")
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY COALESCE(opened_at, updated_at) DESC"
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    def delete(self, pid: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM exports WHERE project_id = ?", (pid,))
            conn.execute("DELETE FROM projects WHERE id = ?", (pid,))

    def delete_all(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM exports")
            conn.execute("DELETE FROM projects")
            conn.execute("DELETE FROM settings")

    # ---------------------------------------------------------------- exports
    def add_export(self, eid: str, pid: str, kind: str, folder: str, files: list[str], settings: dict) -> None:
        with self.connect() as conn:
            conn.execute("INSERT INTO exports (id, project_id, kind, created_at, folder, files, settings) VALUES (?,?,?,?,?,?,?)",
                         (eid, pid, kind, time.time(), folder, json.dumps(files), json.dumps(settings)))

    def list_exports(self, pid: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM exports WHERE project_id = ? ORDER BY created_at DESC", (pid,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["files"] = json.loads(d["files"])
            d["settings"] = json.loads(d["settings"])
            out.append(d)
        return out

    def get_export(self, eid: str) -> dict | None:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM exports WHERE id = ?", (eid,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["files"] = json.loads(d["files"])
        d["settings"] = json.loads(d["settings"])
        return d

    # ---------------------------------------------------------------- settings
    def get_setting(self, key: str, default=None):
        with self.connect() as conn:
            r = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default

    def set_setting(self, key: str, value) -> None:
        with self.connect() as conn:
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                         (key, json.dumps(value)))

    def all_settings(self) -> dict:
        with self.connect() as conn:
            return {r["key"]: json.loads(r["value"]) for r in conn.execute("SELECT key, value FROM settings")}
