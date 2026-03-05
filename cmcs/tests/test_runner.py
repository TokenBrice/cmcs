"""Tests for cmcs.runner."""

from __future__ import annotations

import os

from cmcs.config import CmcsConfig
from cmcs.db import Database
from cmcs.runner import _build_codex_args, build_prompt, recover_orphans
from cmcs.tickets import Ticket, parse_ticket

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
