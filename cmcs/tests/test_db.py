"""Tests for cmcs.db."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from cmcs.db import Database


def make_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "cmcs.db")
    db.initialize()
    return db


def test_register_worktree() -> None:
    with TemporaryDirectory() as tmp_dir:
        db = make_db(Path(tmp_dir))

        db.register_worktree("/tmp/worktree-a", "main")
        worktrees = db.list_worktrees()

        assert len(worktrees) == 1
        assert worktrees[0]["path"] == "/tmp/worktree-a"
        assert worktrees[0]["branch"] == "main"
        assert worktrees[0]["status"] == "active"


def test_archive_worktree() -> None:
    with TemporaryDirectory() as tmp_dir:
        db = make_db(Path(tmp_dir))
        db.register_worktree("/tmp/worktree-a", "main")

        db.archive_worktree("/tmp/worktree-a")
        worktrees = db.list_worktrees()

        assert len(worktrees) == 1
        assert worktrees[0]["status"] == "archived"


def test_create_run() -> None:
    with TemporaryDirectory() as tmp_dir:
        db = make_db(Path(tmp_dir))
        db.register_worktree("/tmp/worktree-a", "main")

        run_id = db.create_run("/tmp/worktree-a", worker_pid=12345)
        run = db.get_run(run_id)

        assert isinstance(run_id, int)
        assert run is not None
        assert run["status"] == "running"
        assert run["worker_pid"] == 12345
        assert run["worktree"] == "/tmp/worktree-a"


def test_finish_run() -> None:
    with TemporaryDirectory() as tmp_dir:
        db = make_db(Path(tmp_dir))
        db.register_worktree("/tmp/worktree-a", "main")
        run_id = db.create_run("/tmp/worktree-a", worker_pid=23456)

        db.finish_run(run_id, "completed")
        run = db.get_run(run_id)

        assert run is not None
        assert run["status"] == "completed"
        assert run["finished_at"] is not None


def test_finish_run_no_double_finish(tmp_path: Path) -> None:
    """finish_run should not overwrite a terminal status."""
    db = Database(tmp_path / "test.db")
    db.initialize()
    db.register_worktree("/tmp/wt", "main")
    run_id = db.create_run("/tmp/wt", worker_pid=1)

    db.finish_run(run_id, "completed")
    assert db.get_run(run_id)["status"] == "completed"

    # Second finish should be a no-op
    db.finish_run(run_id, "failed")
    assert db.get_run(run_id)["status"] == "completed"
    db.close()


def test_database_busy_timeout_set(tmp_path: Path) -> None:
    """Database should configure busy_timeout for concurrent access."""
    db = Database(tmp_path / "test.db")
    db.initialize()

    row = db._conn.execute("PRAGMA busy_timeout").fetchone()

    assert row[0] == 5000
    db.close()


def test_parallel_run_creation(tmp_path: Path) -> None:
    """Multiple threads creating runs simultaneously should not crash."""
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    db.initialize()
    db.register_worktree("/tmp/wt1", "branch1")
    db.register_worktree("/tmp/wt2", "branch2")
    db.close()

    errors: list[Exception] = []
    run_ids: list[int] = []

    def create_runs(worktree: str, count: int) -> None:
        try:
            thread_db = Database(db_path)
            thread_db.initialize()
            for _ in range(count):
                run_id = thread_db.create_run(worktree, worker_pid=1)
                run_ids.append(run_id)
            thread_db.close()
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=create_runs, args=("/tmp/wt1", 10))
    t2 = threading.Thread(target=create_runs, args=("/tmp/wt2", 10))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(errors) == 0, f"Errors during parallel access: {errors}"
    assert len(run_ids) == 20


def test_parallel_finish_run(tmp_path: Path) -> None:
    """Multiple threads finishing different runs should not crash."""
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    db.initialize()
    db.register_worktree("/tmp/wt", "main")
    run_ids = [db.create_run("/tmp/wt", worker_pid=i) for i in range(10)]
    db.close()

    errors: list[Exception] = []

    def finish_run(run_id: int, status: str) -> None:
        try:
            thread_db = Database(db_path)
            thread_db.initialize()
            thread_db.finish_run(run_id, status)
            thread_db.close()
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=finish_run, args=(run_id, "completed"))
        for run_id in run_ids
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(errors) == 0, f"Errors during parallel finish: {errors}"

    db = Database(db_path)
    db.initialize()
    for run_id in run_ids:
        run = db.get_run(run_id)
        assert run["status"] == "completed"
    db.close()


def test_record_event() -> None:
    with TemporaryDirectory() as tmp_dir:
        db = make_db(Path(tmp_dir))
        db.register_worktree("/tmp/worktree-a", "main")
        run_id = db.create_run("/tmp/worktree-a", worker_pid=34567)

        db.record_event(run_id, ticket="TICKET-001", event="started", model="gpt-5")
        db.record_event(
            run_id,
            ticket="TICKET-001",
            event="completed",
            model="gpt-5",
            exit_code=0,
            duration_s=1.75,
        )

        events = db.get_events(run_id)
        assert len(events) == 2
        assert events[0]["event"] == "started"
        assert events[0]["model"] == "gpt-5"
        assert events[0]["exit_code"] is None
        assert events[1]["event"] == "completed"
        assert events[1]["exit_code"] == 0
        assert events[1]["duration_s"] == 1.75


def test_get_running_runs() -> None:
    with TemporaryDirectory() as tmp_dir:
        db = make_db(Path(tmp_dir))
        db.register_worktree("/tmp/worktree-a", "main")
        db.register_worktree("/tmp/worktree-b", "feature")

        finished_id = db.create_run("/tmp/worktree-a", worker_pid=11111)
        running_id = db.create_run("/tmp/worktree-b", worker_pid=22222)
        db.finish_run(finished_id, "completed")

        running_runs = db.get_running_runs()

        assert len(running_runs) == 1
        assert running_runs[0]["id"] == running_id
        assert running_runs[0]["status"] == "running"


def test_get_latest_run_for_worktree() -> None:
    with TemporaryDirectory() as tmp_dir:
        db = make_db(Path(tmp_dir))
        worktree = "/tmp/worktree-a"
        db.register_worktree(worktree, "main")

        first_run_id = db.create_run(worktree, worker_pid=100)
        second_run_id = db.create_run(worktree, worker_pid=200)

        latest = db.get_latest_run(worktree)

        assert latest is not None
        assert latest["id"] in (first_run_id, second_run_id)
        assert latest["id"] == second_run_id


def test_all_runs() -> None:
    with TemporaryDirectory() as tmp_dir:
        db = make_db(Path(tmp_dir))
        db.register_worktree("/tmp/worktree-a", "main")
        db.register_worktree("/tmp/worktree-b", "feature")

        run_id_1 = db.create_run("/tmp/worktree-a", worker_pid=111)
        run_id_2 = db.create_run("/tmp/worktree-b", worker_pid=222)
        run_id_3 = db.create_run("/tmp/worktree-a", worker_pid=333)

        runs = db.all_runs()

        assert len(runs) == 3
        assert [run["id"] for run in runs] == [run_id_1, run_id_2, run_id_3]


def test_database_context_manager(tmp_path: Path) -> None:
    """Database should work as a context manager and close on exit."""
    db_path = tmp_path / "test.db"

    with Database(db_path) as db:
        db.initialize()
        db.register_worktree("/tmp/test", "main")
        worktrees = db.list_worktrees()

        assert len(worktrees) == 1

    with pytest.raises(sqlite3.ProgrammingError):
        db.list_worktrees()
