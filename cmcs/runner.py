"""Codex subprocess runner with prompt protocol, logs, and orphan recovery."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from cmcs.config import CmcsConfig
from cmcs.db import Database
from cmcs.tickets import Ticket, discover_tickets, get_previous_progress


def build_prompt(
    ticket: Ticket,
    repo_path: str,
    ticket_path: str,
    previous_progress: Optional[str],
) -> str:
    """Construct the worker prompt for a ticket run."""
    lines = [
        "You are a Codex worker agent in the cmcs workflow.",
        f"Working directory: {repo_path}",
        "You MUST edit files to complete the task below.",
        f"When done, update the ticket file at {ticket_path}:",
        "  - Set `done: true` in the YAML frontmatter",
        "  - Append a `## Progress` section describing what you did",
        "",
    ]

    if previous_progress:
        lines.append("Context from the previous ticket:")
        lines.append(previous_progress)
        lines.append("")

    lines.append("--- TICKET ---")
    lines.append(ticket.raw)
    lines.append("--- END TICKET ---")
    return "\n".join(lines)


def _pid_alive(pid: Optional[int]) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _find_in_progress_ticket(events: list[dict[str, Any]]) -> str:
    started_order: list[str] = []
    finished: set[str] = set()

    for event in events:
        event_name = event.get("event")
        ticket = str(event.get("ticket", "unknown"))
        if event_name == "started":
            started_order.append(ticket)
        elif event_name in {"completed", "failed"}:
            finished.add(ticket)

    for ticket in reversed(started_order):
        if ticket not in finished:
            return ticket

    return "unknown"


def recover_orphans(db: Database) -> List[Dict[str, Any]]:
    """Mark dead running runs as interrupted and return recovery details."""
    recovered: List[Dict[str, Any]] = []
    for run in db.get_running_runs():
        if _pid_alive(run.get("worker_pid")):
            continue

        db.finish_run(int(run["id"]), "interrupted")
        in_progress = _find_in_progress_ticket(db.get_events(int(run["id"])))
        recovered.append(
            {
                "run_id": int(run["id"]),
                "worktree": str(run["worktree"]),
                "ticket": in_progress,
            }
        )
    return recovered


def _build_codex_args(config: CmcsConfig, ticket: Ticket) -> list[str]:
    """Build codex CLI args, applying per-ticket reasoning_effort override."""
    args = list(config.codex.args)
    if ticket.reasoning_effort:
        filtered: list[str] = []
        skip_next = False
        for i, arg in enumerate(args):
            if skip_next:
                skip_next = False
                continue
            if arg == "-c" and i + 1 < len(args) and args[i + 1].startswith("reasoning_effort="):
                skip_next = True
                continue
            filtered.append(arg)
        args = filtered + ["-c", f"reasoning_effort={ticket.reasoning_effort}"]
    return args


async def _run_single_ticket(
    ticket: Ticket,
    repo_path: Path,
    config: CmcsConfig,
    db: Database,
    run_id: int,
    tickets: list[Ticket],
) -> bool:
    """Execute one ticket by spawning a codex subprocess."""
    ticket_path = repo_path / config.tickets.dir / ticket.filename
    previous_progress = get_previous_progress(tickets, ticket.filename)
    prompt = build_prompt(ticket, str(repo_path), str(ticket_path), previous_progress)

    model = ticket.model or config.codex.model
    db.record_event(run_id, ticket.filename, "started", model=model)

    args = _build_codex_args(config, ticket)

    log_dir = repo_path / ".cmcs" / "logs" / str(run_id)
    log_dir.mkdir(parents=True, exist_ok=True)

    ticket_stem = Path(ticket.filename).stem
    stdout_path = log_dir / f"{ticket_stem}.stdout"
    stderr_path = log_dir / f"{ticket_stem}.stderr"

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    started = time.monotonic()
    exit_code = -1
    duration = config.codex.timeout_s
    with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
        process = await asyncio.create_subprocess_exec(
            config.codex.command,
            *args,
            "-m",
            model,
            prompt,
            cwd=repo_path,
            stdout=stdout_file,
            stderr=stderr_file,
        )
        db.update_worker_pid(run_id, process.pid)
        try:
            exit_code = await asyncio.wait_for(
                process.wait(), timeout=config.codex.timeout_s
            )
            duration = time.monotonic() - started
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
    summary = {
        "ticket": ticket.filename,
        "model": model,
        "exit_code": exit_code,
        "duration_s": round(duration, 2),
        "started_at": started_at,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    summary_path = log_dir / f"{ticket_stem}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    db.record_event(
        run_id,
        ticket.filename,
        "completed" if exit_code == 0 else "failed",
        model=model,
        exit_code=exit_code,
        duration_s=duration,
    )
    return exit_code == 0


async def run_ticket_flow(repo_path: Path, config: CmcsConfig, db: Database) -> int:
    """Run tickets in order until all are done or a ticket run fails."""
    repo_path = Path(repo_path)

    recovered = recover_orphans(db)
    for recovery in recovered:
        print(
            f"Recovered orphaned run {recovery['run_id']} "
            f"in {recovery['worktree']} (ticket: {recovery['ticket']})"
        )

    run_id = db.create_run(str(repo_path), worker_pid=os.getpid())
    tickets_dir = repo_path / config.tickets.dir

    while True:
        tickets = discover_tickets(tickets_dir)
        next_ticket = next((ticket for ticket in tickets if not ticket.done), None)
        if next_ticket is None:
            db.finish_run(run_id, "completed")
            return run_id

        success = await _run_single_ticket(next_ticket, repo_path, config, db, run_id, tickets)
        if not success:
            db.finish_run(run_id, "failed")
            return run_id
