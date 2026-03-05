"""End-to-end integration test for ticket flow using a fake codex binary."""

from __future__ import annotations

import os
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

from cmcs.config import load_config
from cmcs.db import Database
from cmcs.runner import run_ticket_flow


@pytest.fixture
def e2e_repo(tmp_path: Path) -> dict[str, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "checkout", "-B", "master"], cwd=repo, capture_output=True, check=True)

    (repo / "README.md").write_text("integration repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, capture_output=True, check=True)

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, env=env, capture_output=True, check=True)

    cmcs_dir = repo / ".cmcs"
    (cmcs_dir / "tickets").mkdir(parents=True, exist_ok=True)
    (cmcs_dir / "logs").mkdir(parents=True, exist_ok=True)

    db = Database(cmcs_dir / "cmcs.db")
    db.initialize()
    db.register_worktree(str(repo), "master")
    db.close()

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
    fake_codex.write_text(
        textwrap.dedent(
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
            """
        ),
        encoding="utf-8",
    )
    fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IEXEC)

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
async def test_full_ticket_flow(e2e_repo: dict[str, Path], monkeypatch) -> None:
    repo = e2e_repo["repo"]
    monkeypatch.setenv("PATH", f"{e2e_repo['codex_dir']}:{os.environ.get('PATH', '')}")

    db = Database(repo / ".cmcs" / "cmcs.db")
    db.initialize()
    try:
        config = load_config(repo)
        run_id = await run_ticket_flow(repo, config, db)

        run = db.get_run(run_id)
        events = db.get_events(run_id)
    finally:
        db.close()

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
