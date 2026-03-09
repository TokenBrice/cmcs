"""End-to-end integration test for ticket flow using a fake codex binary."""

from __future__ import annotations

import os
import stat
import textwrap
from pathlib import Path

import pytest

from cmcs.config import CmcsConfig, load_config
from cmcs.db import Database
from cmcs.runner import run_ticket_flow


def _write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def e2e_repo(git_repo: Path, db: Database) -> dict[str, Path]:
    repo = git_repo
    cmcs_dir = repo / ".cmcs"
    (cmcs_dir / "tickets").mkdir(parents=True, exist_ok=True)
    (cmcs_dir / "logs").mkdir(parents=True, exist_ok=True)
    db.register_worktree(str(repo), "master")

    ticket_path = cmcs_dir / "tickets" / "TICKET-001.md"
    ticket_path.write_text(
        textwrap.dedent(
            """\
            ---
            title: "Create hello"
            agent: "codex"
            done: false
            ---

            ## Goal
            Make a hello file.

            ## Task
            1. Create src/hello.py
            """
        ),
        encoding="utf-8",
    )

    fake_codex = repo / "fake_codex.py"
    _write_executable(
        fake_codex,
        """\
        #!/usr/bin/env python3
        import re
        import sys
        from pathlib import Path

        prompt = sys.argv[-1]
        match = re.search(r"update the ticket file at (.+?):", prompt, flags=re.IGNORECASE)
        if match is None:
            raise SystemExit("ticket path not found in prompt")

        ticket_path = Path(match.group(1).strip())
        content = ticket_path.read_text(encoding="utf-8")
        content = content.replace("done: false", "done: true", 1)
        if "## Progress" not in content:
            content += "\\n\\n## Progress\\n- Completed by fake codex.\\n"
        ticket_path.write_text(content, encoding="utf-8")

        repo_root = ticket_path.parents[2]
        src_dir = repo_root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "hello.py").write_text("print('Hello, world!')\\n", encoding="utf-8")

        print("fake codex done")
        """,
    )

    codex_link = repo / "codex"
    if codex_link.exists() or codex_link.is_symlink():
        codex_link.unlink()
    codex_link.symlink_to(fake_codex)

    (cmcs_dir / "config.yml").write_text(
        textwrap.dedent(
            """\
            codex:
              model: mock
              args: []
            """
        ),
        encoding="utf-8",
    )

    return {
        "repo": repo,
        "ticket": ticket_path,
        "codex_dir": repo,
    }


@pytest.mark.asyncio
async def test_full_ticket_flow(
    e2e_repo: dict[str, Path], db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = e2e_repo["repo"]
    monkeypatch.setenv("PATH", f"{e2e_repo['codex_dir']}:{os.environ.get('PATH', '')}")

    config = load_config(repo)
    run_id = await run_ticket_flow(repo, config, db)

    run = db.get_run(run_id)
    events = db.get_events(run_id)

    assert run is not None
    assert run["status"] == "completed"

    assert len(events) == 2
    assert events[0]["event"] == "started"
    assert events[1]["event"] == "completed"

    ticket_content = e2e_repo["ticket"].read_text(encoding="utf-8")
    assert "done: true" in ticket_content

    assert (repo / ".cmcs" / "logs" / str(run_id) / "TICKET-001.stdout").exists()

    hello_path = repo / "src" / "hello.py"
    assert hello_path.exists()
    assert "Hello, world!" in hello_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_multi_ticket_sequential(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multiple undone tickets should be processed in filename order."""
    db.register_worktree(str(git_repo), "master")

    tickets_dir = git_repo / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)

    fake_codex = git_repo / "fake-codex"
    _write_executable(fake_codex, "#!/bin/sh\nexit 0\n")

    for i in range(1, 4):
        (tickets_dir / f"TICKET-00{i}.md").write_text(
            f"---\ntitle: Task {i}\ndone: false\n---\nDo task {i}\n",
            encoding="utf-8",
        )

    import cmcs.runner as runner_module

    original_exec = runner_module.asyncio.create_subprocess_exec
    call_order: list[str] = []

    async def fake_exec(*args, **kwargs):
        ticket_file = sorted(tickets_dir.glob("TICKET-*.md"), key=lambda path: path.name)[len(call_order)]
        call_order.append(ticket_file.name)
        content = ticket_file.read_text(encoding="utf-8")
        ticket_file.write_text(
            content.replace("done: false", "done: true", 1),
            encoding="utf-8",
        )
        return await original_exec(str(fake_codex), **kwargs)

    monkeypatch.setattr(runner_module.asyncio, "create_subprocess_exec", fake_exec)

    run_id = await run_ticket_flow(git_repo, CmcsConfig(), db)
    run_record = db.get_run(run_id)
    events = db.get_events(run_id)

    started_events = [event for event in events if event["event"] == "started"]

    assert call_order == ["TICKET-001.md", "TICKET-002.md", "TICKET-003.md"]
    assert run_record is not None
    assert run_record["status"] == "completed"
    assert [event["ticket"] for event in started_events] == call_order
    assert len(started_events) == 3


@pytest.mark.asyncio
async def test_ticket_failure_stops_run(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing ticket should stop the run with failed status."""
    db.register_worktree(str(git_repo), "master")

    tickets_dir = git_repo / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    (tickets_dir / "TICKET-001.md").write_text(
        "---\ntitle: Will fail\ndone: false\n---\nThis will fail\n",
        encoding="utf-8",
    )

    fake_codex = git_repo / "fake-codex-fail"
    _write_executable(fake_codex, "#!/bin/sh\nexit 1\n")

    import cmcs.runner as runner_module

    original_exec = runner_module.asyncio.create_subprocess_exec

    async def fake_exec(*args, **kwargs):
        return await original_exec(str(fake_codex), **kwargs)

    monkeypatch.setattr(runner_module.asyncio, "create_subprocess_exec", fake_exec)

    run_id = await run_ticket_flow(git_repo, CmcsConfig(), db)
    run_record = db.get_run(run_id)
    events = db.get_events(run_id)

    failed_events = [event for event in events if event["event"] == "failed"]

    assert run_record is not None
    assert run_record["status"] == "failed"
    assert len(failed_events) == 1


@pytest.mark.asyncio
async def test_skips_done_tickets(
    git_repo: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tickets with done: true should be skipped."""
    db.register_worktree(str(git_repo), "master")

    tickets_dir = git_repo / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    (tickets_dir / "TICKET-001.md").write_text(
        "---\ntitle: Already done\ndone: true\n---\nDone\n",
        encoding="utf-8",
    )
    (tickets_dir / "TICKET-002.md").write_text(
        "---\ntitle: Also done\ndone: true\n---\nDone\n",
        encoding="utf-8",
    )

    fake_codex = git_repo / "fake-codex"
    _write_executable(fake_codex, "#!/bin/sh\nexit 0\n")

    import cmcs.runner as runner_module

    original_exec = runner_module.asyncio.create_subprocess_exec
    call_count = 0

    async def fake_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return await original_exec(str(fake_codex), **kwargs)

    monkeypatch.setattr(runner_module.asyncio, "create_subprocess_exec", fake_exec)

    run_id = await run_ticket_flow(git_repo, CmcsConfig(), db)
    run_record = db.get_run(run_id)
    events = db.get_events(run_id)

    assert call_count == 0
    assert run_record is not None
    assert run_record["status"] == "completed"
    assert events == []


@pytest.mark.asyncio
async def test_human_agent_ticket_skipped(git_repo: Path, db: Database) -> None:
    """Integration test: human agent tickets are skipped."""
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

    run_id = await run_ticket_flow(git_repo, CmcsConfig(), db)
    run_record = db.get_run(run_id)
    events = db.get_events(run_id)

    assert run_record is not None
    assert run_record["status"] == "completed"
    assert events == []
