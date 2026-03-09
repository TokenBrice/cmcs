"""Tests for cmcs.runner."""

from __future__ import annotations

import os

import pytest

from cmcs.config import CmcsConfig
from cmcs.db import Database
from cmcs.runner import (
    _build_codex_args,
    _run_single_ticket,
    build_prompt,
    recover_orphans,
    run_ticket_flow,
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


def test_run_records_subprocess_pid(tmp_path, monkeypatch) -> None:
    """run_ticket_flow should store the spawned codex subprocess PID."""
    import asyncio
    import stat

    tickets_dir = tmp_path / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    (tickets_dir / "TICKET-001.md").write_text(
        "---\ntitle: test\ndone: false\n---\nDo nothing\n",
        encoding="utf-8",
    )

    codex_script = tmp_path / "codex"
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

    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ.get('PATH', '')}")

    db = Database(tmp_path / ".cmcs" / "cmcs.db")
    db.initialize()
    try:
        db.register_worktree(str(tmp_path), "test")
        run_id = asyncio.run(run_ticket_flow(tmp_path, CmcsConfig(), db))
        run_record = db.get_run(run_id)
    finally:
        db.close()

    assert run_record is not None
    assert run_record["worker_pid"] is not None
    assert run_record["worker_pid"] != os.getpid()


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
