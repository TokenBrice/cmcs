"""Tests for cmcs.cli."""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cmcs.cli import _repo_root, _tail_text, app
from cmcs.db import Database


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


def test_version_command(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """version command should print the package version."""
    runner = CliRunner()
    monkeypatch.chdir(git_repo)
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "cmcs" in result.output


def test_worktree_create_and_list(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(git_repo)

    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0, init_result.output

    create_result = runner.invoke(app, ["worktree", "create", "feature-test"])
    assert create_result.exit_code == 0, create_result.output

    list_result = runner.invoke(app, ["worktree", "list"])
    assert list_result.exit_code == 0, list_result.output
    assert "\t" not in list_result.output
    assert "BRANCH" in list_result.output.splitlines()[0]
    assert "STATUS" in list_result.output
    assert "LATEST" in list_result.output
    assert "PATH" in list_result.output
    assert "feature-test" in list_result.output


def test_repo_root_resolves_from_worktree(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_repo_root() returns the main repo even when CWD is inside a worktree."""
    monkeypatch.chdir(git_repo)
    runner = CliRunner()
    runner.invoke(app, ["init"])
    runner.invoke(app, ["worktree", "create", "wt-test"])
    wt_path = git_repo / "worktrees" / "wt-test"
    assert wt_path.exists()

    # cd into the worktree — _repo_root should still point to main repo
    monkeypatch.chdir(wt_path)
    resolved = _repo_root()
    assert resolved == git_repo.resolve()


def test_repo_root_caching(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_repo_root should return consistent results and cache."""
    monkeypatch.chdir(git_repo)
    from cmcs import cli

    cli._cached_repo_root = None
    r1 = cli._repo_root()
    r2 = cli._repo_root()
    assert r1 == r2


def test_init_reconciles_orphaned_worktrees(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cmcs init re-registers worktrees after a DB reset."""
    runner = CliRunner()
    monkeypatch.chdir(git_repo)
    runner.invoke(app, ["init"])
    runner.invoke(app, ["worktree", "create", "orphan-test"])

    # Simulate DB reset
    db_path = git_repo / ".cmcs" / "cmcs.db"
    db_path.unlink()

    # Re-init should reconcile
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert "Re-registered 1 orphaned worktree" in result.output


def test_run_auto_registers_worktree(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run command should auto-register unregistered paths, preventing FK violations."""
    monkeypatch.chdir(git_repo)

    (git_repo / ".cmcs" / "tickets").mkdir(parents=True, exist_ok=True)

    runner = CliRunner()
    result = runner.invoke(app, ["run", str(git_repo)])
    assert result.exit_code == 0, result.output
    assert "finished with status: completed" in result.output


def test_run_dry_run(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--dry-run should list pending tickets without executing."""
    monkeypatch.chdir(git_repo)
    tickets_dir = git_repo / ".cmcs" / "tickets"
    (tickets_dir / "TICKET-001.md").write_text(
        "---\ntitle: Test task\ndone: false\n---\nDo something\n", encoding="utf-8"
    )
    (tickets_dir / "TICKET-002.md").write_text(
        "---\ntitle: Done task\ndone: true\n---\nAlready done\n", encoding="utf-8"
    )

    runner = CliRunner()
    result = runner.invoke(app, ["run", str(git_repo), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Would process 1 ticket" in result.output
    assert "TICKET-001" in result.output
    assert "TICKET-002" not in result.output


def test_ticket_validate_ok(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ticket validate should pass for well-formed tickets."""
    monkeypatch.chdir(git_repo)
    tickets_dir = git_repo / ".cmcs" / "tickets"
    (tickets_dir / "TICKET-001.md").write_text(
        "---\ntitle: Good ticket\ndone: false\n---\nTask\n"
    )
    runner = CliRunner()
    result = runner.invoke(app, ["ticket", "validate", str(git_repo)])
    assert result.exit_code == 0
    assert "valid" in result.output.lower()


def test_ticket_validate_missing_title(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ticket validate should flag tickets without titles."""
    monkeypatch.chdir(git_repo)
    tickets_dir = git_repo / ".cmcs" / "tickets"
    (tickets_dir / "TICKET-001.md").write_text(
        "---\ndone: false\n---\nNo title\n"
    )
    runner = CliRunner()
    result = runner.invoke(app, ["ticket", "validate", str(git_repo)])
    assert result.exit_code == 1
    assert "missing title" in result.output


def test_clean_removes_old_logs(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """clean command should remove logs older than threshold."""
    monkeypatch.chdir(git_repo)
    log_dir = git_repo / ".cmcs" / "logs" / "1"
    log_dir.mkdir(parents=True)
    (log_dir / "test.stdout").write_text("old log", encoding="utf-8")

    old_time = time.time() - (60 * 86400)
    os.utime(log_dir, (old_time, old_time))

    runner = CliRunner()
    result = runner.invoke(app, ["clean", "--logs-days", "30"])
    assert result.exit_code == 0, result.output
    assert "Removed 1" in result.output
    assert not log_dir.exists()


def test_run_completes_with_no_tickets(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run command should complete cleanly when no tickets exist."""
    monkeypatch.chdir(git_repo)
    db.register_worktree(str(git_repo), "master")

    runner = CliRunner()
    result = runner.invoke(app, ["run", str(git_repo)])
    assert result.exit_code == 0, result.output
    assert "finished with status: completed" in result.output


def test_wait_exits_when_no_runs(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """wait command should exit with error when no runs exist."""
    monkeypatch.chdir(git_repo)

    runner = CliRunner()
    result = runner.invoke(app, ["wait", str(git_repo)])
    assert result.exit_code == 1, result.output
    assert "No runs" in result.output


def test_error_messages_include_guidance(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Error messages should suggest next steps."""
    monkeypatch.chdir(git_repo)

    runner = CliRunner()
    result = runner.invoke(app, ["wait", str(git_repo)])
    assert result.exit_code == 1, result.output
    assert "cmcs run" in result.output or "No runs" in result.output


def test_wait_exits_when_run_completed(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """wait command should return immediately for completed runs."""
    monkeypatch.chdir(git_repo)
    db.register_worktree(str(git_repo), "master")
    run_id = db.create_run(str(git_repo), worker_pid=1)
    db.finish_run(run_id, "completed")

    runner = CliRunner()
    result = runner.invoke(app, ["wait", str(git_repo)])
    assert result.exit_code == 0, result.output
    assert "completed" in result.output


def test_wait_timeout(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """wait --timeout should exit with code 2 after timeout."""
    from unittest.mock import patch

    monkeypatch.chdir(git_repo)
    db.register_worktree(str(git_repo), "master")
    db.create_run(str(git_repo), worker_pid=99999)

    runner = CliRunner()
    with patch("cmcs.cli.recover_orphans", return_value=[]):
        result = runner.invoke(app, ["wait", str(git_repo), "--timeout", "1"])

    assert result.exit_code == 2, result.output
    assert "Timed out" in result.output


def test_stop_exits_when_no_running(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stop command should exit with error when no running flows exist."""
    monkeypatch.chdir(git_repo)

    runner = CliRunner()
    result = runner.invoke(app, ["stop", str(git_repo)])
    assert result.exit_code == 1, result.output
    assert "No running flow" in result.output


def test_stop_marks_run_stopped(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stop command should mark the run as stopped."""
    from unittest.mock import patch

    monkeypatch.chdir(git_repo)
    db.register_worktree(str(git_repo), "master")
    run_id = db.create_run(str(git_repo), worker_pid=99999)

    runner = CliRunner()
    with patch("cmcs.cli.recover_orphans", return_value=[]):
        result = runner.invoke(app, ["stop", str(git_repo)])

    assert result.exit_code == 0, result.output
    assert "Stopped" in result.output
    run_record = db.get_run(run_id)
    assert run_record is not None
    assert run_record["status"] == "stopped"


def test_logs_no_runs(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """logs command should exit with error when no runs exist."""
    monkeypatch.chdir(git_repo)

    runner = CliRunner()
    result = runner.invoke(app, ["logs", str(git_repo)])
    assert result.exit_code == 1, result.output
    assert "No runs" in result.output


def test_logs_shows_content(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """logs command should display log file contents."""
    monkeypatch.chdir(git_repo)
    db.register_worktree(str(git_repo), "master")
    run_id = db.create_run(str(git_repo), worker_pid=1)
    db.finish_run(run_id, "completed")

    log_dir = git_repo / ".cmcs" / "logs" / str(run_id)
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "TICKET-001.stdout").write_text("test output here", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["logs", str(git_repo)])
    assert result.exit_code == 0, result.output
    assert "test output here" in result.output


def test_logs_lines_option(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--lines option should control how much of the log to show."""
    monkeypatch.chdir(git_repo)
    db.register_worktree(str(git_repo), "master")
    run_id = db.create_run(str(git_repo), worker_pid=1)
    db.finish_run(run_id, "completed")

    log_dir = git_repo / ".cmcs" / "logs" / str(run_id)
    log_dir.mkdir(parents=True)
    (log_dir / "TICKET-001.stdout").write_text("a" * 10000)

    runner = CliRunner()
    result = runner.invoke(app, ["logs", str(git_repo), "--lines", "100"])
    assert result.exit_code == 0
    assert len(result.output) < 500


def test_dashboard_starts_uvicorn(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """dashboard command should launch uvicorn with configured host and port."""
    from unittest.mock import patch

    monkeypatch.chdir(git_repo)

    runner = CliRunner()
    with patch("uvicorn.run") as mock_run:
        result = runner.invoke(app, ["dashboard"])

    assert result.exit_code == 0, result.output
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 4173


def test_logs_resolves_worktree_path(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """logs command should look in the worktree's .cmcs/logs/, not main repo."""
    monkeypatch.chdir(git_repo)

    from cmcs.db import Database

    db = Database(git_repo / ".cmcs" / "cmcs.db")
    db.initialize()

    # Simulate a worktree run: register a worktree and create a run.
    wt_path = git_repo / "worktrees" / "feature-a"
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


def test_logs_calls_recover_orphans(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The logs command should call recover_orphans before displaying."""
    monkeypatch.chdir(git_repo)

    from unittest.mock import patch
    from typer.testing import CliRunner
    from cmcs.cli import app

    runner = CliRunner()
    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0, init_result.output
    with patch("cmcs.cli.recover_orphans") as mock_recover:
        result = runner.invoke(app, ["logs", str(git_repo)])
    mock_recover.assert_called_once()
    assert result.exit_code in (0, 1)


def test_stop_verifies_termination(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stop command should verify the process died after SIGTERM."""
    from unittest.mock import call, patch

    from cmcs.db import Database

    monkeypatch.chdir(git_repo)

    db = Database(git_repo / ".cmcs" / "cmcs.db")
    db.initialize()
    db.register_worktree(str(git_repo), "master")
    run_id = db.create_run(str(git_repo), worker_pid=99999)
    db.close()

    runner = CliRunner()
    with patch("cmcs.cli.recover_orphans") as mock_recover:
        with patch("cmcs.cli.os.kill") as mock_kill:
            with patch("cmcs.cli.time.sleep") as mock_sleep:
                result = runner.invoke(app, ["stop", str(git_repo)])

    assert result.exit_code == 0, result.output
    assert "Stopped run" in result.output
    mock_recover.assert_called_once()
    assert mock_sleep.call_count == 10
    assert mock_kill.call_count == 12
    assert mock_kill.call_args_list[0] == call(99999, signal.SIGTERM)
    assert mock_kill.call_args_list[-1] == call(99999, signal.SIGKILL)
    for kill_call in mock_kill.call_args_list[1:11]:
        assert kill_call == call(99999, 0)

    db = Database(git_repo / ".cmcs" / "cmcs.db")
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


def test_status_active_filter(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--active flag should filter to running runs only."""
    runner = CliRunner()
    monkeypatch.chdir(git_repo)
    db.register_worktree(str(git_repo), "master")
    completed_run = db.create_run(str(git_repo), worker_pid=1)
    db.finish_run(completed_run, "completed")
    running_run = db.create_run(str(git_repo), worker_pid=os.getpid())

    result = runner.invoke(app, ["status", "--active"])

    assert result.exit_code == 0, result.output
    assert str(running_run) in result.output
    assert "completed" not in result.output
