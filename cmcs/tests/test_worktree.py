"""Tests for cmcs.worktree."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from cmcs.config import CmcsConfig
from cmcs.db import Database
from cmcs.worktree import cleanup_worktree, create_worktree, list_worktrees, reconcile_worktrees


def git_repo(tmp_path: Path) -> Path:
    """Create a real git repository with an initial commit on master."""
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "checkout", "-B", "master"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    (repo / "README.md").write_text("init\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, capture_output=True, check=True)

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        env=env,
        capture_output=True,
        check=True,
    )

    return repo


def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "cmcs.db")
    database.initialize()
    return database


def test_create_worktree(tmp_path: Path) -> None:
    repo = git_repo(tmp_path)
    database = db(tmp_path)
    config = CmcsConfig()
    wt_path = create_worktree(repo, "test-branch", config, database)

    assert wt_path.exists()
    assert (wt_path / "README.md").exists()

    worktrees = list_worktrees(database)
    assert len(worktrees) == 1
    assert worktrees[0]["path"] == str(wt_path)
    assert worktrees[0]["branch"] == "test-branch"


def test_create_worktree_creates_tickets_dir(tmp_path: Path) -> None:
    repo = git_repo(tmp_path)
    database = db(tmp_path)
    config = CmcsConfig()
    wt_path = create_worktree(repo, "test-branch", config, database)

    assert (wt_path / ".cmcs" / "tickets").is_dir()


def test_cleanup_worktree(tmp_path: Path) -> None:
    repo = git_repo(tmp_path)
    database = db(tmp_path)
    config = CmcsConfig()
    wt_path = create_worktree(repo, "test-branch", config, database)

    cleanup_worktree(repo, "test-branch", database)

    assert not wt_path.exists()
    worktrees = database.list_worktrees()
    assert len(worktrees) == 1
    assert worktrees[0]["status"] == "archived"


def test_reconcile_registers_orphaned_worktrees(tmp_path: Path) -> None:
    """After a DB reset, reconcile re-registers worktrees found on disk."""
    repo = git_repo(tmp_path)
    config = CmcsConfig()

    # Create a worktree with one DB, then throw away the DB
    database1 = db(tmp_path)
    wt_path = create_worktree(repo, "orphan-branch", config, database1)
    assert wt_path.exists()
    database1.close()

    # Fresh DB — simulates rm cmcs.db && cmcs init
    fresh_db = Database(tmp_path / "fresh.db")
    fresh_db.initialize()
    assert len(fresh_db.list_worktrees()) == 0

    # Reconcile should find the worktree on disk and register it
    count = reconcile_worktrees(repo, config, fresh_db)
    assert count == 1

    worktrees = fresh_db.list_worktrees()
    assert len(worktrees) == 1
    assert worktrees[0]["path"] == str(wt_path)
    assert worktrees[0]["branch"] == "orphan-branch"
    fresh_db.close()


def test_reconcile_skips_already_registered(tmp_path: Path) -> None:
    """Reconcile does not duplicate worktrees that are already in the DB."""
    repo = git_repo(tmp_path)
    config = CmcsConfig()
    database = db(tmp_path)

    create_worktree(repo, "existing-branch", config, database)
    count = reconcile_worktrees(repo, config, database)
    assert count == 0
    assert len(database.list_worktrees()) == 1


def test_reconcile_skips_non_worktree_dirs(tmp_path: Path) -> None:
    """Reconcile ignores directories that aren't git worktrees."""
    repo = git_repo(tmp_path)
    config = CmcsConfig()
    database = db(tmp_path)

    # Create a plain directory (not a git worktree) in worktrees/
    wt_root = repo / config.worktrees.root
    wt_root.mkdir(parents=True, exist_ok=True)
    (wt_root / "not-a-worktree").mkdir()

    count = reconcile_worktrees(repo, config, database)
    assert count == 0
    assert len(database.list_worktrees()) == 0


def test_reconcile_noop_without_worktrees_dir(tmp_path: Path) -> None:
    """Reconcile returns 0 when the worktrees directory doesn't exist."""
    repo = git_repo(tmp_path)
    config = CmcsConfig()
    database = db(tmp_path)

    count = reconcile_worktrees(repo, config, database)
    assert count == 0
