"""Git worktree management with automatic DB registration."""

from __future__ import annotations

import subprocess
from pathlib import Path

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


def reconcile_worktrees(repo_root: Path, config: CmcsConfig, db: Database) -> int:
    """Auto-register worktrees found on disk but missing from the DB.

    Returns the number of newly registered worktrees.
    """
    wt_root = repo_root / config.worktrees.root
    if not wt_root.exists():
        return 0

    registered = {wt["path"] for wt in db.list_worktrees() if wt["status"] == "active"}
    count = 0

    for child in sorted(wt_root.iterdir()):
        if not child.is_dir():
            continue
        wt_path = str(child.resolve())
        if wt_path in registered:
            continue
        # Verify it's a git worktree (has a .git file pointing to the main repo)
        git_marker = child / ".git"
        if not git_marker.exists():
            continue
        # Detect the actual branch name
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=child,
        )
        branch = result.stdout.strip() if result.returncode == 0 else child.name
        db.register_worktree(wt_path, branch)
        count += 1

    return count


def cleanup_worktree(
    repo_root: Path, branch: str, db: Database, force: bool = False
) -> None:
    """Remove a worktree, delete its branch, and archive it in the database."""
    wt_path: str | None = None
    for worktree in db.list_worktrees():
        if worktree["branch"] == branch:
            wt_path = worktree["path"]
            break

    if wt_path is None:
        raise ValueError(f"No worktree found for branch '{branch}'")

    # 1. Remove worktree first (can't delete a branch in use by a worktree)
    subprocess.run(
        ["git", "worktree", "remove", wt_path, "--force"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )

    # 2. Then delete the branch (safe by default, force if requested)
    delete_flag = "-D" if force else "-d"
    result = subprocess.run(
        ["git", "branch", delete_flag, branch],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 and not force:
        db.archive_worktree(wt_path)
        raise RuntimeError(
            f"Branch '{branch}' has unmerged changes. Use --force to delete anyway. "
            f"Git says: {result.stderr.strip()}"
        )

    db.archive_worktree(wt_path)
