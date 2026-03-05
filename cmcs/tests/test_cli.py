"""Tests for cmcs.cli."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from cmcs.cli import app


def _make_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "checkout", "-B", "master"], cwd=repo, capture_output=True, check=True)

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


def test_init_creates_structure(tmp_path: Path) -> None:
    runner = CliRunner()
    previous = Path.cwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0, result.output
        assert (tmp_path / ".cmcs").is_dir()
        assert (tmp_path / ".cmcs" / "cmcs.db").is_file()
        assert (tmp_path / ".cmcs" / "tickets").is_dir()
    finally:
        os.chdir(previous)


def test_config_show(tmp_path: Path) -> None:
    runner = CliRunner()
    previous = Path.cwd()
    os.chdir(tmp_path)
    try:
        init_result = runner.invoke(app, ["init"])
        assert init_result.exit_code == 0, init_result.output

        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0, result.output
        assert "gpt-5.3-codex" in result.output
    finally:
        os.chdir(previous)


def test_worktree_create_and_list(tmp_path: Path) -> None:
    runner = CliRunner()
    repo = _make_git_repo(tmp_path)

    previous = Path.cwd()
    os.chdir(repo)
    try:
        init_result = runner.invoke(app, ["init"])
        assert init_result.exit_code == 0, init_result.output

        create_result = runner.invoke(app, ["worktree", "create", "feature-test"])
        assert create_result.exit_code == 0, create_result.output

        list_result = runner.invoke(app, ["worktree", "list"])
        assert list_result.exit_code == 0, list_result.output
        assert "feature-test" in list_result.output
    finally:
        os.chdir(previous)


def test_status_no_runs(tmp_path: Path) -> None:
    runner = CliRunner()
    previous = Path.cwd()
    os.chdir(tmp_path)
    try:
        init_result = runner.invoke(app, ["init"])
        assert init_result.exit_code == 0, init_result.output

        status_result = runner.invoke(app, ["status"])
        assert status_result.exit_code == 0, status_result.output
        assert "No runs" in status_result.output
    finally:
        os.chdir(previous)
