"""Tests for cmcs.cli."""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cmcs.cli import _repo_root, _tail_text, app


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


def test_repo_root_resolves_from_worktree(tmp_path: Path) -> None:
    """_repo_root() returns the main repo even when CWD is inside a worktree."""
    repo = _make_git_repo(tmp_path)
    previous = Path.cwd()
    os.chdir(repo)
    try:
        runner = CliRunner()
        runner.invoke(app, ["init"])
        runner.invoke(app, ["worktree", "create", "wt-test"])
        wt_path = repo / "worktrees" / "wt-test"
        assert wt_path.exists()

        # cd into the worktree — _repo_root should still point to main repo
        os.chdir(wt_path)
        resolved = _repo_root()
        assert resolved == repo.resolve()
    finally:
        os.chdir(previous)


def test_init_reconciles_orphaned_worktrees(tmp_path: Path) -> None:
    """cmcs init re-registers worktrees after a DB reset."""
    repo = _make_git_repo(tmp_path)
    runner = CliRunner()
    previous = Path.cwd()
    os.chdir(repo)
    try:
        runner.invoke(app, ["init"])
        runner.invoke(app, ["worktree", "create", "orphan-test"])

        # Simulate DB reset
        db_path = repo / ".cmcs" / "cmcs.db"
        db_path.unlink()

        # Re-init should reconcile
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0, result.output
        assert "Re-registered 1 orphaned worktree" in result.output
    finally:
        os.chdir(previous)


def test_run_auto_registers_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run command should auto-register unregistered paths, preventing FK violations."""
    repo = _make_git_repo(tmp_path)
    monkeypatch.chdir(repo)

    (repo / ".cmcs" / "tickets").mkdir(parents=True, exist_ok=True)

    runner = CliRunner()
    result = runner.invoke(app, ["run", str(repo)])
    assert result.exit_code == 0, result.output
    assert "finished with status: completed" in result.output


def test_logs_resolves_worktree_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """logs command should look in the worktree's .cmcs/logs/, not main repo."""
    repo = _make_git_repo(tmp_path)
    monkeypatch.chdir(repo)

    from cmcs.db import Database

    db = Database(repo / ".cmcs" / "cmcs.db")
    db.initialize()

    # Simulate a worktree run: register a worktree and create a run.
    wt_path = repo / "worktrees" / "feature-a"
    wt_path.mkdir(parents=True)
    db.register_worktree(str(wt_path), "feature-a")
    run_id = db.create_run(str(wt_path), worker_pid=1)
    db.finish_run(run_id, "completed")

    # Create log files in the worktree's log directory (where runner.py writes them).
    log_dir = wt_path / ".cmcs" / "logs" / str(run_id)
    log_dir.mkdir(parents=True)
    (log_dir / "TICKET-001.stdout").write_text("hello from worktree")

    db.close()

    runner = CliRunner()
    result = runner.invoke(app, ["logs", str(wt_path)])
    assert result.exit_code == 0, result.output
    assert "hello from worktree" in result.output


def test_logs_calls_recover_orphans(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The logs command should call recover_orphans before displaying."""
    repo = _make_git_repo(tmp_path)
    monkeypatch.chdir(repo)

    from unittest.mock import patch
    from typer.testing import CliRunner
    from cmcs.cli import app

    runner = CliRunner()
    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0, init_result.output
    with patch("cmcs.cli.recover_orphans") as mock_recover:
        result = runner.invoke(app, ["logs", str(repo)])
    mock_recover.assert_called_once()
    assert result.exit_code in (0, 1)


def test_stop_verifies_termination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stop command should verify the process died after SIGTERM."""
    from unittest.mock import call, patch

    from cmcs.db import Database

    repo = _make_git_repo(tmp_path)
    monkeypatch.chdir(repo)

    db = Database(repo / ".cmcs" / "cmcs.db")
    db.initialize()
    db.register_worktree(str(repo), "master")
    run_id = db.create_run(str(repo), worker_pid=99999)
    db.close()

    runner = CliRunner()
    with patch("cmcs.cli.recover_orphans") as mock_recover:
        with patch("cmcs.cli.os.kill") as mock_kill:
            with patch("cmcs.cli.time.sleep") as mock_sleep:
                result = runner.invoke(app, ["stop", str(repo)])

    assert result.exit_code == 0, result.output
    assert "Stopped run" in result.output
    mock_recover.assert_called_once()
    assert mock_sleep.call_count == 10
    assert mock_kill.call_count == 12
    assert mock_kill.call_args_list[0] == call(99999, signal.SIGTERM)
    assert mock_kill.call_args_list[-1] == call(99999, signal.SIGKILL)
    for kill_call in mock_kill.call_args_list[1:11]:
        assert kill_call == call(99999, 0)

    db = Database(repo / ".cmcs" / "cmcs.db")
    db.initialize()
    run_row = db.get_run(run_id)
    db.close()
    assert run_row is not None
    assert run_row["status"] == "stopped"


def test_tail_text_utf8_boundary(tmp_path: Path) -> None:
    """_tail_text should handle multi-byte UTF-8 at the seek boundary."""
    content = "\U0001f600" + "a" * 4093
    test_file = tmp_path / "test.log"
    test_file.write_text(content, encoding="utf-8")

    result = _tail_text(test_file, size=4096)

    assert "\ufffd" not in result
    assert "a" * 100 in result


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
