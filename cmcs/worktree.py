"""Git worktree management with automatic DB registration."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from cmcs.config import CmcsConfig
from cmcs.db import Database


def create_worktree(
    repo_root: Path, branch: str, config: CmcsConfig, db: Database
) -> Path:
    """Create and register a git worktree for a branch."""
    wt_root = repo_root / config.worktrees.root
    wt_root.mkdir(parents=True, exist_ok=True)
    wt_path = wt_root / branch

    subprocess.run(
        [
            "git",
            "worktree",
            "add",
            "-b",
            branch,
            str(wt_path),
            config.worktrees.start_point,
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )

    (wt_path / ".cmcs" / "tickets").mkdir(parents=True, exist_ok=True)
    db.register_worktree(str(wt_path), branch)
    return wt_path


def list_worktrees(db: Database) -> list[dict[str, Any]]:
    """Return all worktrees from the database."""
    return db.list_worktrees()


def cleanup_worktree(repo_root: Path, branch: str, db: Database) -> None:
    """Remove a worktree, delete its branch, and archive it in the database."""
    wt_path: str | None = None
    for worktree in db.list_worktrees():
        if worktree["branch"] == branch:
            wt_path = worktree["path"]
            break

    if wt_path is None:
        raise ValueError(f"No worktree found for branch '{branch}'")

    subprocess.run(
        ["git", "worktree", "remove", wt_path, "--force"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )

    subprocess.run(
        ["git", "branch", "-D", branch],
        cwd=repo_root,
        capture_output=True,
    )

    db.archive_worktree(wt_path)
