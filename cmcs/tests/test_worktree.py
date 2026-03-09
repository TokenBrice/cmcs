"""Tests for cmcs.worktree."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from cmcs.config import CmcsConfig
from cmcs.db import Database
from cmcs.worktree import cleanup_worktree, create_worktree, list_worktrees, reconcile_worktrees


def test_create_worktree(git_repo: Path, db: Database) -> None:
    config = CmcsConfig()
    wt_path = create_worktree(git_repo, "test-branch", config, db)

    assert wt_path.exists()
    assert (wt_path / "README.md").exists()

    worktrees = list_worktrees(db)
    assert len(worktrees) == 1
    assert worktrees[0]["path"] == str(wt_path)
    assert worktrees[0]["branch"] == "test-branch"


def test_create_worktree_creates_tickets_dir(git_repo: Path, db: Database) -> None:
    config = CmcsConfig()
    wt_path = create_worktree(git_repo, "test-branch", config, db)

    assert (wt_path / ".cmcs" / "tickets").is_dir()


def test_cleanup_worktree(git_repo: Path, db: Database) -> None:
    config = CmcsConfig()
    wt_path = create_worktree(git_repo, "test-branch", config, db)

    cleanup_worktree(git_repo, "test-branch", db)

    assert not wt_path.exists()
    worktrees = db.list_worktrees()
    assert len(worktrees) == 1
    assert worktrees[0]["status"] == "archived"


def test_cleanup_worktree_safe_delete_fails_on_unmerged(
    git_repo: Path, db: Database
) -> None:
    cfg = CmcsConfig()
    wt_path = create_worktree(git_repo, "unmerged-branch", cfg, db)

    (wt_path / "newfile.txt").write_text("content", encoding="utf-8")

    subprocess.run(
        ["git", "-C", str(wt_path), "add", "."],
        capture_output=True,
        check=True,
    )

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    subprocess.run(
        ["git", "-C", str(wt_path), "commit", "-m", "unmerged"],
        capture_output=True,
        check=True,
        env=env,
    )

    with pytest.raises(RuntimeError, match="unmerged"):
        cleanup_worktree(git_repo, "unmerged-branch", db, force=False)

    # Worktree was removed but branch persists (unmerged); DB was archived
    assert not wt_path.exists()
    worktrees = db.list_worktrees()
    assert any(w["branch"] == "unmerged-branch" and w["status"] == "archived" for w in worktrees)

    # Force-delete the branch directly (cleanup already archived the DB entry)
    subprocess.run(
        ["git", "branch", "-D", "unmerged-branch"],
        cwd=git_repo,
        capture_output=True,
        check=True,
    )


def test_reconcile_registers_orphaned_worktrees(
    git_repo: Path, db: Database, tmp_path: Path
) -> None:
    """After a DB reset, reconcile re-registers worktrees found on disk."""
    config = CmcsConfig()

    # Create a worktree with one DB, then throw away the DB
    wt_path = create_worktree(git_repo, "orphan-branch", config, db)
    assert wt_path.exists()

    # Fresh DB — simulates rm cmcs.db && cmcs init
    fresh_db = Database(tmp_path / "fresh.db")
    fresh_db.initialize()
    assert len(fresh_db.list_worktrees()) == 0

    # Reconcile should find the worktree on disk and register it
    count = reconcile_worktrees(git_repo, config, fresh_db)
    assert count == 1

    worktrees = fresh_db.list_worktrees()
    assert len(worktrees) == 1
    assert worktrees[0]["path"] == str(wt_path)
    assert worktrees[0]["branch"] == "orphan-branch"
    fresh_db.close()


def test_reconcile_skips_already_registered(git_repo: Path, db: Database) -> None:
    """Reconcile does not duplicate worktrees that are already in the DB."""
    config = CmcsConfig()

    create_worktree(git_repo, "existing-branch", config, db)
    count = reconcile_worktrees(git_repo, config, db)
    assert count == 0
    assert len(db.list_worktrees()) == 1


def test_reconcile_skips_non_worktree_dirs(git_repo: Path, db: Database) -> None:
    """Reconcile ignores directories that aren't git worktrees."""
    config = CmcsConfig()

    # Create a plain directory (not a git worktree) in worktrees/
    wt_root = git_repo / config.worktrees.root
    wt_root.mkdir(parents=True, exist_ok=True)
    (wt_root / "not-a-worktree").mkdir()

    count = reconcile_worktrees(git_repo, config, db)
    assert count == 0
    assert len(db.list_worktrees()) == 0


def test_reconcile_noop_without_worktrees_dir(git_repo: Path, db: Database) -> None:
    """Reconcile returns 0 when the worktrees directory doesn't exist."""
    config = CmcsConfig()

    count = reconcile_worktrees(git_repo, config, db)
    assert count == 0
