"""SQLite database access layer for worktrees, runs, and events."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Any, Optional


class Database:
    """Database helper for persisting orchestration state."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        if self.db_path.parent and not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA busy_timeout = 5000;")
        self._conn.commit()

    def __enter__(self) -> Database:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def initialize(self) -> None:
        """Create the database schema if it does not already exist."""
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS worktrees (
                path TEXT PRIMARY KEY, branch TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                status TEXT NOT NULL DEFAULT 'active'
            );
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, worktree TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT (datetime('now')), finished_at TEXT,
                status TEXT NOT NULL DEFAULT 'running', worker_pid INTEGER,
                FOREIGN KEY (worktree) REFERENCES worktrees(path)
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL,
                ticket TEXT NOT NULL, model TEXT, event TEXT NOT NULL,
                exit_code INTEGER, duration_s REAL,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (run_id) REFERENCES runs(id)
            );
            """
        )
        self._conn.commit()

    def register_worktree(self, path: str, branch: str) -> None:
        """Register a worktree path or reactivate an existing one."""
        self._conn.execute(
            """
            INSERT INTO worktrees (path, branch)
            VALUES (?, ?)
            ON CONFLICT(path) DO UPDATE SET
                branch = excluded.branch,
                status = 'active'
            """,
            (path, branch),
        )
        self._conn.commit()

    def archive_worktree(self, path: str) -> None:
        """Mark a worktree as archived."""
        self._conn.execute("UPDATE worktrees SET status = 'archived' WHERE path = ?", (path,))
        self._conn.commit()

    def list_worktrees(self) -> list[dict[str, Any]]:
        """Return all worktrees."""
        rows = self._conn.execute("SELECT * FROM worktrees ORDER BY path").fetchall()
        return [dict(row) for row in rows]

    def create_run(self, worktree: str, worker_pid: int) -> int:
        """Create a new run and return its ID."""
        cursor = self._conn.execute(
            "INSERT INTO runs (worktree, worker_pid) VALUES (?, ?)",
            (worktree, worker_pid),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def update_worker_pid(self, run_id: int, pid: int) -> None:
        """Update the worker PID for a run."""
        self._conn.execute(
            "UPDATE runs SET worker_pid = ? WHERE id = ?",
            (pid, run_id),
        )
        self._conn.commit()

    def get_run(self, run_id: int) -> Optional[dict[str, Any]]:
        """Fetch a run by ID."""
        row = self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row is not None else None

    def finish_run(self, run_id: int, status: str) -> None:
        """Finish a run with the provided status. Only updates if still running."""
        self._conn.execute(
            "UPDATE runs SET status = ?, finished_at = datetime('now') WHERE id = ? AND status = 'running'",
            (status, run_id),
        )
        self._conn.commit()

    def get_running_runs(self) -> list[dict[str, Any]]:
        """Return all runs currently marked as running."""
        rows = self._conn.execute(
            "SELECT * FROM runs WHERE status = 'running' ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_latest_run(self, worktree: str) -> Optional[dict[str, Any]]:
        """Return the latest run for a worktree."""
        row = self._conn.execute(
            """
            SELECT * FROM runs
            WHERE worktree = ?
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (worktree,),
        ).fetchone()
        return dict(row) if row is not None else None

    def all_runs(self) -> list[dict[str, Any]]:
        """Return all runs."""
        rows = self._conn.execute("SELECT * FROM runs ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def record_event(
        self,
        run_id: int,
        ticket: str,
        event: str,
        model: Optional[str] = None,
        exit_code: Optional[int] = None,
        duration_s: Optional[float] = None,
    ) -> None:
        """Record a run event."""
        self._conn.execute(
            """
            INSERT INTO events (run_id, ticket, model, event, exit_code, duration_s)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, ticket, model, event, exit_code, duration_s),
        )
        self._conn.commit()

    def get_events(self, run_id: int) -> list[dict[str, Any]]:
        """Return all events for a run."""
        rows = self._conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()
