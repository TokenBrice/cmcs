"""cmcs CLI entrypoint."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import typer
import yaml

from cmcs.config import load_config
from cmcs.db import Database
from cmcs.runner import recover_orphans, run_ticket_flow
from cmcs.worktree import cleanup_worktree as _cleanup_worktree
from cmcs.worktree import create_worktree as _create_worktree
from cmcs.worktree import reconcile_worktrees as _reconcile_worktrees

app = typer.Typer(
    name="cmcs",
    help="Claude Master Codex Slave — orchestration CLI",
    no_args_is_help=True,
)
worktree_app = typer.Typer(help="Manage git worktrees.")
config_app = typer.Typer(help="Show effective configuration.")


def _repo_root() -> Path:
    """Resolve the main repo root, even when CWD is inside a git worktree."""
    cwd = Path.cwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if result.returncode == 0:
            git_common = Path(result.stdout.strip())
            if not git_common.is_absolute():
                git_common = (cwd / git_common).resolve()
            return git_common.parent
    except FileNotFoundError:
        pass
    return cwd


def _db() -> Database:
    return Database(_repo_root() / ".cmcs" / "cmcs.db")


def _ensure_initialized() -> None:
    cmcs_dir = _repo_root() / ".cmcs"
    if not cmcs_dir.exists():
        typer.echo("Error: not a cmcs project. Run 'cmcs init' first.", err=True)
        raise typer.Exit(code=1)


def _tail_text(path: Path, size: int = 4096) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        end = handle.tell()
        handle.seek(max(0, end - size), os.SEEK_SET)
        chunk = handle.read()
    return chunk.decode("utf-8", errors="replace")


app.add_typer(worktree_app, name="worktree")
app.add_typer(config_app, name="config")


@app.command()
def init() -> None:
    """Initialize .cmcs/ in the current repo."""
    root = _repo_root()
    cmcs_dir = root / ".cmcs"
    cmcs_dir.mkdir(parents=True, exist_ok=True)
    (cmcs_dir / "tickets").mkdir(parents=True, exist_ok=True)
    (cmcs_dir / "logs").mkdir(parents=True, exist_ok=True)

    db = Database(cmcs_dir / "cmcs.db")
    db.initialize()
    cfg = load_config(root)
    reconciled = _reconcile_worktrees(root, cfg, db)
    db.close()
    if reconciled:
        typer.echo(f"Re-registered {reconciled} orphaned worktree(s)")
    typer.echo(f"Initialized cmcs in {cmcs_dir}")


@config_app.command("show")
def config_show() -> None:
    """Print effective configuration."""
    _ensure_initialized()
    cfg = load_config(_repo_root())
    rendered = yaml.safe_dump(asdict(cfg), sort_keys=False)
    typer.echo(rendered.rstrip())


@worktree_app.command("create")
def worktree_create(branch: str) -> None:
    """Create a worktree and register it in the database."""
    _ensure_initialized()
    db = _db()
    db.initialize()
    cfg = load_config(_repo_root())
    try:
        wt_path = _create_worktree(_repo_root(), branch, cfg, db)
    finally:
        db.close()
    typer.echo(f"Created worktree: {wt_path}")


@worktree_app.command("list")
def worktree_list() -> None:
    """Show all registered worktrees with latest run status."""
    _ensure_initialized()
    db = _db()
    db.initialize()
    try:
        worktrees = db.list_worktrees()
        if not worktrees:
            typer.echo("No worktrees registered.")
            return

        typer.echo("BRANCH\tSTATUS\tLATEST\tPATH")
        for wt in worktrees:
            latest = db.get_latest_run(str(wt["path"]))
            latest_status = latest["status"] if latest else "no runs"
            typer.echo(f"{wt['branch']}\t{wt['status']}\t{latest_status}\t{wt['path']}")
    finally:
        db.close()


@worktree_app.command("cleanup")
def worktree_cleanup(branch: str) -> None:
    """Remove a worktree and archive it in the database."""
    _ensure_initialized()
    db = _db()
    db.initialize()
    try:
        _cleanup_worktree(_repo_root(), branch, db)
    finally:
        db.close()
    typer.echo(f"Cleaned up worktree for branch: {branch}")


@app.command()
def run(path: str = typer.Argument(".", help="Repo/worktree path")) -> None:
    """Process tickets in the target repo/worktree."""
    _ensure_initialized()
    repo_path = Path(path).resolve()
    root = _repo_root()
    db = _db()
    db.initialize()
    cfg = load_config(root)
    _reconcile_worktrees(root, cfg, db)
    existing = {wt["path"] for wt in db.list_worktrees()}
    if str(repo_path) not in existing:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=repo_path,
        )
        branch = result.stdout.strip() if result.returncode == 0 else repo_path.name
        db.register_worktree(str(repo_path), branch)
    try:
        run_id = asyncio.run(run_ticket_flow(repo_path, cfg, db))
        run_record = db.get_run(run_id)
    finally:
        db.close()

    status = run_record["status"] if run_record else "unknown"
    typer.echo(f"Run {run_id} finished with status: {status}")


@app.command()
def status(
    path: Optional[str] = typer.Argument(None, help="Optional worktree path filter"),
) -> None:
    """Show run status and ticket counts."""
    _ensure_initialized()
    db = _db()
    db.initialize()
    try:
        recover_orphans(db)
        if path is None:
            runs = db.all_runs()
        else:
            target = str(Path(path).resolve())
            runs = [run for run in db.all_runs() if str(run["worktree"]) == target]

        if not runs:
            typer.echo("No runs found.")
            return

        for run_row in runs:
            events = db.get_events(int(run_row["id"]))
            started = sum(1 for event in events if event["event"] == "started")
            completed = sum(1 for event in events if event["event"] == "completed")
            failed = sum(1 for event in events if event["event"] == "failed")
            typer.echo(
                f"Run {run_row['id']}: {run_row['status']} "
                f"(tickets started={started}, completed={completed}, failed={failed}) "
                f"worktree={run_row['worktree']}"
            )
    finally:
        db.close()


@app.command()
def wait(path: str = typer.Argument(..., help="Worktree path")) -> None:
    """Poll every second until the latest run is no longer running."""
    _ensure_initialized()
    target = str(Path(path).resolve())
    db = _db()
    db.initialize()
    try:
        while True:
            recover_orphans(db)
            run_row = db.get_latest_run(target)
            if run_row is None:
                typer.echo(f"No runs for {target}")
                raise typer.Exit(code=1)
            if run_row["status"] != "running":
                typer.echo(f"Run {run_row['id']} is {run_row['status']}")
                return
            time.sleep(1)
    finally:
        db.close()


@app.command()
def stop(path: str = typer.Argument(..., help="Worktree path")) -> None:
    """Terminate the latest running run for a worktree and mark it stopped."""
    _ensure_initialized()
    target = str(Path(path).resolve())
    db = _db()
    db.initialize()
    try:
        running = [
            run_row
            for run_row in db.get_running_runs()
            if str(run_row["worktree"]) == target
        ]
        if not running:
            typer.echo("No running flow for this path.")
            raise typer.Exit(code=1)

        run_row = sorted(running, key=lambda row: int(row["id"]))[-1]
        pid = run_row.get("worker_pid")
        if isinstance(pid, int) and pid > 0:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except PermissionError:
                typer.echo(f"Unable to signal pid {pid}; marking run stopped anyway.", err=True)

        db.finish_run(int(run_row["id"]), "stopped")
        typer.echo(f"Stopped run {run_row['id']}")
    finally:
        db.close()


@app.command()
def logs(path: str = typer.Argument(..., help="Worktree path")) -> None:
    """Show the last 4KB of each log file for the latest run."""
    _ensure_initialized()
    target = str(Path(path).resolve())
    db = _db()
    db.initialize()
    try:
        run_row = db.get_latest_run(target)
    finally:
        db.close()

    if run_row is None:
        typer.echo("No runs for this path.")
        raise typer.Exit(code=1)

    log_dir = Path(run_row["worktree"]) / ".cmcs" / "logs" / str(run_row["id"])
    if not log_dir.exists():
        typer.echo("No log artifacts found.")
        raise typer.Exit(code=1)

    log_files = sorted(path for path in log_dir.iterdir() if path.is_file())
    if not log_files:
        typer.echo("No log artifacts found.")
        raise typer.Exit(code=1)

    for log_file in log_files:
        typer.echo(f"=== {log_file.name} ===")
        content = _tail_text(log_file)
        typer.echo(content.rstrip() or "(empty)")


@app.command()
def dashboard() -> None:
    """Run the web dashboard."""
    _ensure_initialized()
    cfg = load_config(_repo_root())

    from cmcs.dashboard.app import create_app
    import uvicorn

    web_app = create_app(_repo_root())
    uvicorn.run(web_app, host="127.0.0.1", port=cfg.dashboard.port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
