"""Shared test fixtures for cmcs test suite."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from cmcs.db import Database


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with cmcs initialized. Returns the repo path.

    Note: Tests that verify `cmcs init` behavior should NOT use this fixture
    since it pre-creates `.cmcs`. Use raw `tmp_path` for those tests.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@test.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@test.com",
    }

    subprocess.run(
        ["git", "init", str(repo)],
        capture_output=True,
        check=True,
        env=env,
    )
    subprocess.run(
        ["git", "-C", str(repo), "checkout", "-B", "master"],
        capture_output=True,
        check=True,
        env=env,
    )
    (repo / "README.md").write_text("init\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "README.md"],
        capture_output=True,
        check=True,
        env=env,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "init"],
        capture_output=True,
        check=True,
        env=env,
    )

    cmcs_dir = repo / ".cmcs"
    cmcs_dir.mkdir()
    (cmcs_dir / "tickets").mkdir()
    (cmcs_dir / "logs").mkdir()
    return repo


@pytest.fixture
def db(git_repo: Path) -> Database:
    """Create and initialize a Database for the git_repo fixture."""
    database = Database(git_repo / ".cmcs" / "cmcs.db")
    database.initialize()
    yield database
    database.close()
