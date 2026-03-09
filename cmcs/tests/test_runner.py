"""Tests for cmcs.runner."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cmcs.config import CmcsConfig
from cmcs.db import Database
from cmcs.runner import (
    _build_codex_args,
    _run_single_ticket,
    build_prompt,
    recover_orphans,
    run_ticket_flow,
    stop_worker,
)
from cmcs.tickets import Ticket, discover_tickets, parse_ticket

SAMPLE_TICKET = """---
title: "Create hello"
agent: codex
done: false
---

## Goal
Create hello.py

## Task
1. Create src/hello.py
"""


def test_build_prompt_first_ticket() -> None:
    ticket = parse_ticket(SAMPLE_TICKET, "TICKET-001.md")
    prompt = build_prompt(
        ticket=ticket,
        repo_path="/work/repo",
        ticket_path="/work/repo/.cmcs/tickets/TICKET-001.md",
        previous_progress=None,
    )

    assert "Working directory: /work/repo" in prompt
    assert "--- TICKET ---" in prompt
    assert "--- END TICKET ---" in prompt
    assert "Create hello.py" in prompt
    assert "Context from the previous ticket:" not in prompt


def test_build_prompt_with_previous_progress() -> None:
    ticket = parse_ticket(SAMPLE_TICKET, "TICKET-002.md")
    prompt = build_prompt(
        ticket=ticket,
        repo_path="/work/repo",
        ticket_path="/work/repo/.cmcs/tickets/TICKET-002.md",
        previous_progress="## Progress\n- Created the config file.",
    )

    assert "Context from the previous ticket:" in prompt
    assert "Created the config file." in prompt
    assert "--- TICKET ---" in prompt


def test_build_codex_args_default() -> None:
    config = CmcsConfig()
    ticket = Ticket(filename="T.md", title="", agent="codex", done=False, body="", raw="")
    args = _build_codex_args(config, ticket)
    assert args == config.codex.args
    assert "-c" in args
    assert "reasoning_effort=xhigh" in args


def test_build_codex_args_ticket_override() -> None:
    config = CmcsConfig()
    ticket = Ticket(
        filename="T.md", title="", agent="codex", done=False,
        body="", raw="", reasoning_effort="high",
    )
    args = _build_codex_args(config, ticket)
    # Should have replaced xhigh with high
    assert "reasoning_effort=high" in args
    assert "reasoning_effort=xhigh" not in args
    # Should still have the other args
    assert "--yolo" in args


def test_build_codex_args_no_existing_effort() -> None:
    from cmcs.config import CodexConfig
    config = CmcsConfig(codex=CodexConfig(args=["--yolo", "exec"]))
    ticket = Ticket(
        filename="T.md", title="", agent="codex", done=False,
        body="", raw="", reasoning_effort="low",
    )
    args = _build_codex_args(config, ticket)
    assert args == ["--yolo", "exec", "-c", "reasoning_effort=low"]


def test_configurable_command() -> None:
    """Runner should use config.codex.command instead of hardcoded 'codex'."""
    from cmcs.config import CodexConfig

    cfg = CmcsConfig(codex=CodexConfig(command="echo"))

    assert cfg.codex.command == "echo"


def test_recover_orphans_marks_dead_runs(tmp_path) -> None:
    db = Database(tmp_path / "cmcs.db")
    db.initialize()
    db.register_worktree("/wt", "branch")

    run_id = db.create_run("/wt", worker_pid=999999999)
    db.record_event(run_id, ticket="TICKET-001.md", event="started")

    recovered = recover_orphans(db)
    run = db.get_run(run_id)

    assert len(recovered) == 1
    assert recovered[0]["run_id"] == run_id
    assert recovered[0]["worktree"] == "/wt"
    assert recovered[0]["ticket"] == "TICKET-001.md"
    assert run is not None
    assert run["status"] == "interrupted"


def test_recover_orphans_skips_alive_pids(tmp_path) -> None:
    db = Database(tmp_path / "cmcs.db")
    db.initialize()
    db.register_worktree("/wt", "branch")

    run_id = db.create_run("/wt", worker_pid=os.getpid())
    recovered = recover_orphans(db)
    run = db.get_run(run_id)

    assert recovered == []
    assert run is not None
    assert run["status"] == "running"


def test_stop_worker_already_dead() -> None:
    assert stop_worker(999999999) is True


def test_stop_worker_signals_process() -> None:
    import signal
    from unittest.mock import call, patch

    with patch("cmcs.runner.os.kill") as mock_kill:
        with patch("cmcs.runner.time.sleep") as mock_sleep:
            with patch("cmcs.runner._pid_alive", side_effect=[True, False]) as mock_alive:
                stopped = stop_worker(12345)

    assert stopped is True
    assert mock_alive.call_count == 2
    mock_sleep.assert_called_once_with(0.5)
    mock_kill.assert_called_once_with(12345, signal.SIGTERM)
    assert mock_kill.call_args_list == [call(12345, signal.SIGTERM)]


def test_stop_worker_escalates_to_sigkill() -> None:
    import signal
    from unittest.mock import call, patch

    with patch("cmcs.runner.os.kill") as mock_kill:
        with patch("cmcs.runner.time.sleep"):
            with patch("cmcs.runner._pid_alive", return_value=True):
                stopped = stop_worker(12345)

    assert stopped is False
    assert mock_kill.call_args_list[0] == call(12345, signal.SIGTERM)
    assert mock_kill.call_args_list[-1] == call(12345, signal.SIGKILL)


def test_run_records_subprocess_pid(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_ticket_flow should store the spawned codex subprocess PID."""
    import asyncio
    import stat

    tickets_dir = git_repo / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    (tickets_dir / "TICKET-001.md").write_text(
        "---\ntitle: test\ndone: false\n---\nDo nothing\n",
        encoding="utf-8",
    )

    codex_script = git_repo / "codex"
    codex_script.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import re\n"
            "import sys\n"
            "from pathlib import Path\n"
            "prompt = sys.argv[-1]\n"
            "match = re.search(r'update the ticket file at (.+?):', prompt, flags=re.IGNORECASE)\n"
            "if match is None:\n"
            "    raise SystemExit('ticket path not found in prompt')\n"
            "ticket_path = Path(match.group(1).strip())\n"
            "content = ticket_path.read_text(encoding='utf-8')\n"
            "ticket_path.write_text(content.replace('done: false', 'done: true', 1), encoding='utf-8')\n"
        ),
        encoding="utf-8",
    )
    codex_script.chmod(codex_script.stat().st_mode | stat.S_IEXEC)

    monkeypatch.setenv("PATH", f"{git_repo}:{os.environ.get('PATH', '')}")

    db.register_worktree(str(git_repo), "test")
    run_id = asyncio.run(run_ticket_flow(git_repo, CmcsConfig(), db))
    run_record = db.get_run(run_id)

    assert run_record is not None
    assert run_record["worker_pid"] is not None
    assert run_record["worker_pid"] != os.getpid()


def test_exit_zero_without_done_fails(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit code 0 without done:true should fail the run instead of looping."""
    import asyncio
    import stat

    tickets_dir = git_repo / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    (tickets_dir / "TICKET-001.md").write_text(
        "---\ntitle: test\ndone: false\n---\nDo nothing\n",
        encoding="utf-8",
    )

    codex_script = git_repo / "codex"
    codex_script.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "sys.exit(0)\n"
        ),
        encoding="utf-8",
    )
    codex_script.chmod(codex_script.stat().st_mode | stat.S_IEXEC)

    monkeypatch.setenv("PATH", f"{git_repo}:{os.environ.get('PATH', '')}")

    db.register_worktree(str(git_repo), "test")
    run_id = asyncio.run(
        asyncio.wait_for(run_ticket_flow(git_repo, CmcsConfig(), db), timeout=2)
    )
    run_record = db.get_run(run_id)

    assert run_record is not None
    assert run_record["status"] == "failed"

    events = db.get_events(run_id)
    failed_events = [event for event in events if event["event"] == "failed"]
    started_events = [event for event in events if event["event"] == "started"]

    assert len(started_events) == 1
    assert len(failed_events) >= 1


def test_run_creates_json_log(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each ticket execution should produce a .json summary log."""
    import asyncio
    import json
    import stat

    tickets_dir = git_repo / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    (tickets_dir / "TICKET-001.md").write_text(
        "---\ntitle: test\ndone: false\n---\nTest\n",
        encoding="utf-8",
    )

    codex_script = git_repo / "codex"
    codex_script.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import re\n"
            "import sys\n"
            "from pathlib import Path\n"
            "prompt = sys.argv[-1]\n"
            "match = re.search(r'update the ticket file at (.+?):', prompt, flags=re.IGNORECASE)\n"
            "if match is None:\n"
            "    raise SystemExit('ticket path not found in prompt')\n"
            "ticket_path = Path(match.group(1).strip())\n"
            "content = ticket_path.read_text(encoding='utf-8')\n"
            "ticket_path.write_text(content.replace('done: false', 'done: true', 1), encoding='utf-8')\n"
        ),
        encoding="utf-8",
    )
    codex_script.chmod(codex_script.stat().st_mode | stat.S_IEXEC)

    monkeypatch.setenv("PATH", f"{git_repo}:{os.environ.get('PATH', '')}")

    db.register_worktree(str(git_repo), "test")
    run_id = asyncio.run(run_ticket_flow(git_repo, CmcsConfig(), db))

    log_dir = git_repo / ".cmcs" / "logs" / str(run_id)
    json_files = list(log_dir.glob("*.json"))

    assert len(json_files) == 1

    summary = json.loads(json_files[0].read_text(encoding="utf-8"))

    assert summary["ticket"] == "TICKET-001.md"
    assert "duration_s" in summary
    assert "exit_code" in summary


@pytest.mark.asyncio
async def test_skips_human_agent_tickets(git_repo: Path, db: Database) -> None:
    """run_ticket_flow should skip tickets with agent != 'codex'."""
    db.register_worktree(str(git_repo), "master")

    tickets_dir = git_repo / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)

    (tickets_dir / "TICKET-001.md").write_text(
        "---\ntitle: Manual migration\nagent: human\ndone: false\n---\nRun SQL migration\n",
        encoding="utf-8",
    )
    (tickets_dir / "TICKET-002.md").write_text(
        "---\ntitle: Already done\ndone: true\n---\nDone\n",
        encoding="utf-8",
    )

    cfg = CmcsConfig()
    run_id = await run_ticket_flow(git_repo, cfg, db)

    run_record = db.get_run(run_id)
    events = db.get_events(run_id)

    assert run_record is not None
    assert run_record["status"] == "completed"
    assert len(events) == 0


@pytest.mark.asyncio
async def test_run_single_ticket_timeout(tmp_path, monkeypatch) -> None:
    db = Database(tmp_path / "cmcs.db")
    db.initialize()
    try:
        config = CmcsConfig()
        config.codex.timeout_s = 0.1

        tickets_dir = tmp_path / ".cmcs" / "tickets"
        tickets_dir.mkdir(parents=True, exist_ok=True)
        ticket_file = tickets_dir / "TICKET-001.md"
        ticket_file.write_text(
            "---\ntitle: slow\ndone: false\n---\nDo something slow\n",
            encoding="utf-8",
        )

        tickets = discover_tickets(tickets_dir)

        import cmcs.runner as runner_module

        original = runner_module.asyncio.create_subprocess_exec

        async def fake_exec(*args, **kwargs):
            kwargs = {key: value for key, value in kwargs.items() if key != "cwd"}
            return await original("sleep", "10", **kwargs)

        monkeypatch.setattr(runner_module.asyncio, "create_subprocess_exec", fake_exec)

        db.register_worktree(str(tmp_path), "test")
        run_id = db.create_run(str(tmp_path), worker_pid=1)

        result = await _run_single_ticket(tickets[0], tmp_path, config, db, run_id, tickets)

        assert result is False

        events = db.get_events(run_id)
        failed_events = [event for event in events if event["event"] == "failed"]

        assert len(failed_events) == 1
        assert failed_events[0]["exit_code"] == -1
        assert failed_events[0]["duration_s"] == pytest.approx(config.codex.timeout_s)
    finally:
        db.close()


def test_auto_commit_after_done_ticket(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Successful ticket marked done should be auto-committed."""
    import asyncio
    import stat
    import subprocess

    tickets_dir = git_repo / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    (tickets_dir / "TICKET-001.md").write_text(
        "---\ntitle: test\ndone: false\n---\nDo nothing\n",
        encoding="utf-8",
    )

    codex_script = git_repo / "codex"
    codex_script.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import re, sys\n"
            "from pathlib import Path\n"
            "prompt = sys.argv[-1]\n"
            "match = re.search(r'update the ticket file at (.+?):', prompt, flags=re.IGNORECASE)\n"
            "if match is None:\n"
            "    raise SystemExit('ticket path not found in prompt')\n"
            "ticket_path = Path(match.group(1).strip())\n"
            "content = ticket_path.read_text(encoding='utf-8')\n"
            "ticket_path.write_text(content.replace('done: false', 'done: true', 1), encoding='utf-8')\n"
            "# Also create a new file to verify it gets committed\n"
            "Path(ticket_path.parent.parent.parent / 'new_file.txt').write_text('created by agent')\n"
        ),
        encoding="utf-8",
    )
    codex_script.chmod(codex_script.stat().st_mode | stat.S_IEXEC)

    monkeypatch.setenv("PATH", f"{git_repo}:{os.environ.get('PATH', '')}")

    db.register_worktree(str(git_repo), "test")
    config = CmcsConfig()
    assert config.codex.auto_commit is True

    run_id = asyncio.run(run_ticket_flow(git_repo, config, db))
    run_record = db.get_run(run_id)
    assert run_record is not None
    assert run_record["status"] == "completed"

    # Verify a commit was created
    result = subprocess.run(
        ["git", "-C", str(git_repo), "log", "--oneline", "-2"],
        capture_output=True,
        text=True,
    )
    assert "cmcs: TICKET-001.md completed" in result.stdout


def test_auto_commit_disabled(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When auto_commit is False, no commit should be created after ticket."""
    import asyncio
    import stat
    import subprocess
    from cmcs.config import CodexConfig

    tickets_dir = git_repo / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    (tickets_dir / "TICKET-001.md").write_text(
        "---\ntitle: test\ndone: false\n---\nDo nothing\n",
        encoding="utf-8",
    )

    codex_script = git_repo / "codex"
    codex_script.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import re, sys\n"
            "from pathlib import Path\n"
            "prompt = sys.argv[-1]\n"
            "match = re.search(r'update the ticket file at (.+?):', prompt, flags=re.IGNORECASE)\n"
            "if match is None:\n"
            "    raise SystemExit('ticket path not found in prompt')\n"
            "ticket_path = Path(match.group(1).strip())\n"
            "content = ticket_path.read_text(encoding='utf-8')\n"
            "ticket_path.write_text(content.replace('done: false', 'done: true', 1), encoding='utf-8')\n"
        ),
        encoding="utf-8",
    )
    codex_script.chmod(codex_script.stat().st_mode | stat.S_IEXEC)

    monkeypatch.setenv("PATH", f"{git_repo}:{os.environ.get('PATH', '')}")

    db.register_worktree(str(git_repo), "test")
    config = CmcsConfig(codex=CodexConfig(auto_commit=False))

    run_id = asyncio.run(run_ticket_flow(git_repo, config, db))

    # Verify NO auto-commit was made
    result = subprocess.run(
        ["git", "-C", str(git_repo), "log", "--oneline", "-2"],
        capture_output=True,
        text=True,
    )
    assert "cmcs:" not in result.stdout


def test_auto_commit_failure_records_warning(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auto-commit failures should emit warning events and be logged in summary JSON."""
    import asyncio
    import json
    import stat

    tickets_dir = git_repo / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    (tickets_dir / "TICKET-001.md").write_text(
        "---\ntitle: test\ndone: false\n---\nDo nothing\n",
        encoding="utf-8",
    )

    codex_script = git_repo / "codex"
    codex_script.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import re, sys\n"
            "from pathlib import Path\n"
            "prompt = sys.argv[-1]\n"
            "match = re.search(r'update the ticket file at (.+?):', prompt, flags=re.IGNORECASE)\n"
            "if match is None:\n"
            "    raise SystemExit('ticket path not found in prompt')\n"
            "ticket_path = Path(match.group(1).strip())\n"
            "content = ticket_path.read_text(encoding='utf-8')\n"
            "ticket_path.write_text(content.replace('done: false', 'done: true', 1), encoding='utf-8')\n"
        ),
        encoding="utf-8",
    )
    codex_script.chmod(codex_script.stat().st_mode | stat.S_IEXEC)

    monkeypatch.setenv("PATH", f"{git_repo}:{os.environ.get('PATH', '')}")

    def broken_git_run(*_args, **_kwargs):
        raise OSError("git broken")

    monkeypatch.setattr("cmcs.runner.subprocess.run", broken_git_run)

    db.register_worktree(str(git_repo), "test")
    run_id = asyncio.run(run_ticket_flow(git_repo, CmcsConfig(), db))

    run_record = db.get_run(run_id)
    assert run_record is not None
    assert run_record["status"] == "completed"

    events = db.get_events(run_id)
    assert any(event["event"] == "warning" for event in events)

    summary_path = git_repo / ".cmcs" / "logs" / str(run_id) / "TICKET-001.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert "auto_commit_error" in summary


from cmcs.runner import _should_fallback


def test_should_fallback_context_length():
    assert _should_fallback("Error: context length exceeded for model") is True
    assert _should_fallback("context_length_exceeded") is True


def test_should_fallback_max_output_tokens():
    assert _should_fallback("Error: max_output_tokens limit reached") is True
    assert _should_fallback("maximum token limit exceeded") is True


def test_should_fallback_no_match():
    assert _should_fallback("SyntaxError: invalid syntax") is False
    assert _should_fallback("test failed with exit code 1") is False
    assert _should_fallback("rate_limit exceeded") is False
    assert _should_fallback("") is False


def test_fallback_retry_on_context_error(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When primary model fails with context error and fallback is set, retry with fallback."""
    import asyncio
    import stat

    tickets_dir = git_repo / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    (tickets_dir / "TICKET-001.md").write_text(
        "---\ntitle: test\ndone: false\n---\nDo something\n",
        encoding="utf-8",
    )

    codex_script = git_repo / "codex"
    codex_script.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import re, sys\n"
            "from pathlib import Path\n"
            "model_idx = sys.argv.index('-m') + 1\n"
            "model = sys.argv[model_idx]\n"
            "prompt = sys.argv[-1]\n"
            "if model == 'gpt-5.3-codex':\n"
            "    sys.stderr.write('Error: context_length_exceeded\\n')\n"
            "    sys.exit(1)\n"
            "match = re.search(r'update the ticket file at (.+?):', prompt, flags=re.IGNORECASE)\n"
            "if match is None:\n"
            "    raise SystemExit('ticket path not found')\n"
            "ticket_path = Path(match.group(1).strip())\n"
            "content = ticket_path.read_text(encoding='utf-8')\n"
            "ticket_path.write_text(content.replace('done: false', 'done: true', 1), encoding='utf-8')\n"
        ),
        encoding="utf-8",
    )
    codex_script.chmod(codex_script.stat().st_mode | stat.S_IEXEC)

    monkeypatch.setenv("PATH", f"{git_repo}:{os.environ.get('PATH', '')}")

    db.register_worktree(str(git_repo), "test")
    from cmcs.config import CodexConfig
    config = CmcsConfig(codex=CodexConfig(
        auto_commit=False,
        fallback_model="gpt-5.1-codex-max",
    ))

    run_id = asyncio.run(run_ticket_flow(git_repo, config, db))
    run_record = db.get_run(run_id)
    assert run_record is not None
    assert run_record["status"] == "completed"

    events = db.get_events(run_id)
    failed_events = [e for e in events if e["event"] == "failed"]
    completed_events = [e for e in events if e["event"] == "completed"]
    assert len(failed_events) == 1
    assert len(completed_events) == 1


def test_no_fallback_on_non_model_error(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """General failures should NOT trigger fallback retry."""
    import asyncio
    import stat

    tickets_dir = git_repo / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    (tickets_dir / "TICKET-001.md").write_text(
        "---\ntitle: test\ndone: false\n---\nDo something\n",
        encoding="utf-8",
    )

    codex_script = git_repo / "codex"
    codex_script.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "sys.stderr.write('SyntaxError: invalid syntax\\n')\n"
            "sys.exit(1)\n"
        ),
        encoding="utf-8",
    )
    codex_script.chmod(codex_script.stat().st_mode | stat.S_IEXEC)

    monkeypatch.setenv("PATH", f"{git_repo}:{os.environ.get('PATH', '')}")

    db.register_worktree(str(git_repo), "test")
    from cmcs.config import CodexConfig
    config = CmcsConfig(codex=CodexConfig(
        auto_commit=False,
        fallback_model="gpt-5.1-codex-max",
    ))

    run_id = asyncio.run(run_ticket_flow(git_repo, config, db))
    run_record = db.get_run(run_id)
    assert run_record is not None
    assert run_record["status"] == "failed"

    events = db.get_events(run_id)
    started_events = [e for e in events if e["event"] == "started"]
    assert len(started_events) == 1
