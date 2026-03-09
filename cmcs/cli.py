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
ticket_app = typer.Typer(help="Ticket management.")


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
        start = max(0, end - size)
        handle.seek(start, os.SEEK_SET)
        chunk = handle.read()

    i = 0
    while i < len(chunk) and i < 4 and (chunk[i] & 0xC0) == 0x80:
        i += 1
    return chunk[i:].decode("utf-8", errors="replace")


_STATUS_COLORS = {
    "running": typer.colors.GREEN,
    "completed": typer.colors.WHITE,
    "failed": typer.colors.RED,
    "interrupted": typer.colors.YELLOW,
    "stopped": typer.colors.YELLOW,
}


def _colored_status(status: str) -> str:
    color = _STATUS_COLORS.get(status, typer.colors.WHITE)
    return typer.style(status, fg=color)


app.add_typer(worktree_app, name="worktree")
app.add_typer(config_app, name="config")
app.add_typer(ticket_app, name="ticket")


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


@app.command()
def clean(
    logs_older_than: int = typer.Option(
        30, "--logs-days", help="Delete logs older than N days"
    ),
    purge_archived: bool = typer.Option(
        False, "--purge-archived", help="Remove archived worktree records from DB"
    ),
) -> None:
    """Clean up old logs and archived data."""
    _ensure_initialized()
    root = _repo_root()
    removed_logs = 0

    logs_dir = root / ".cmcs" / "logs"
    if logs_dir.exists():
        import shutil

        cutoff = time.time() - (logs_older_than * 86400)
        for log_dir in logs_dir.iterdir():
            if log_dir.is_dir() and log_dir.stat().st_mtime < cutoff:
                shutil.rmtree(log_dir)
                removed_logs += 1

    typer.echo(
        f"Removed {removed_logs} old log director{'y' if removed_logs == 1 else 'ies'}."
    )

    if purge_archived:
        db = _db()
        db.initialize()
        try:
            archived = [
                worktree for worktree in db.list_worktrees() if worktree["status"] == "archived"
            ]
            # Keep run/event rows for history; only remove archived worktree entries.
            count = len(archived)
            for worktree in archived:
                db._conn.execute(
                    "DELETE FROM worktrees WHERE path = ? AND status = 'archived'",
                    (worktree["path"],),
                )
            db._conn.commit()
            typer.echo(f"Purged {count} archived worktree record(s) from database.")
        finally:
            db.close()


@config_app.command("show")
def config_show() -> None:
    """Print effective configuration."""
    _ensure_initialized()
    cfg = load_config(_repo_root())
    rendered = yaml.safe_dump(asdict(cfg), sort_keys=False)
    typer.echo(rendered.rstrip())


@ticket_app.command("validate")
def ticket_validate(
    path: str = typer.Argument(".", help="Repo/worktree path"),
) -> None:
    """Validate ticket format and report issues."""
    _ensure_initialized()
    repo_path = Path(path).resolve()
    cfg = load_config(_repo_root())
    tickets_dir = repo_path / cfg.tickets.dir

    from cmcs.tickets import discover_tickets
    import warnings

    errors = 0
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        tickets = discover_tickets(tickets_dir)

    if not tickets:
        typer.echo("No tickets found.")
        return

    for ticket in tickets:
        issues = []
        if not ticket.title:
            issues.append("missing title")
        if ticket.model and not ticket.model.strip():
            issues.append("empty model string")

        if issues:
            errors += 1
            typer.echo(f"  {ticket.filename}: {', '.join(issues)}", err=True)
        else:
            typer.echo(f"  {ticket.filename}: OK")

    for warning_message in caught:
        typer.echo(f"  WARNING: {warning_message.message}", err=True)
        errors += 1

    if errors:
        typer.echo(f"\n{errors} issue(s) found.", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"\nAll {len(tickets)} ticket(s) valid.")


@app.command()
def version() -> None:
    """Print the cmcs version."""
    from importlib.metadata import version as pkg_version

    typer.echo(f"cmcs {pkg_version('cmcs')}")


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
        recover_orphans(db)
        worktrees = db.list_worktrees()
        if not worktrees:
            typer.echo("No worktrees registered.")
            return

        typer.echo(f"{'BRANCH':<25} {'STATUS':<10} {'LATEST':<12} PATH")
        for wt in worktrees:
            latest = db.get_latest_run(str(wt["path"]))
            latest_status = latest["status"] if latest else "no runs"
            colored_latest = _colored_status(latest_status) if latest else latest_status
            typer.echo(f"{wt['branch']:<25} {wt['status']:<10} {colored_latest:<12} {wt['path']}")
    finally:
        db.close()


@worktree_app.command("cleanup")
def worktree_cleanup(
    branch: str,
    force: bool = typer.Option(False, "--force", help="Force-delete even if branch has unmerged changes"),
) -> None:
    """Remove a worktree and archive it in the database."""
    _ensure_initialized()
    db = _db()
    db.initialize()
    try:
        _cleanup_worktree(_repo_root(), branch, db, force=force)
    finally:
        db.close()
    typer.echo(f"Cleaned up worktree for branch: {branch}")


@app.command()
def run(
    path: str = typer.Argument(".", help="Repo/worktree path"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show tickets that would be processed without running them",
    ),
) -> None:
    """Process tickets in the target repo/worktree."""
    _ensure_initialized()
    repo_path = Path(path).resolve()
    root = _repo_root()
    cfg = load_config(root)

    if dry_run:
        from cmcs.tickets import discover_tickets

        tickets_dir = repo_path / cfg.tickets.dir
        tickets = discover_tickets(tickets_dir)
        undone = [ticket for ticket in tickets if not ticket.done]
        if not undone:
            typer.echo("No pending tickets to process.")
        else:
            typer.echo(f"Would process {len(undone)} ticket(s):")
            for ticket in undone:
                model = ticket.model or cfg.codex.model
                typer.echo(f"  {ticket.filename}: {ticket.title} (model={model})")
        return

    db = _db()
    db.initialize()
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
    active: bool = typer.Option(False, "--active", help="Show only running runs"),
    latest: bool = typer.Option(
        False, "--latest", help="Show only the latest run per worktree"
    ),
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

        if active:
            runs = [run for run in runs if run["status"] == "running"]
        if latest:
            # Keep only the latest run per worktree.
            seen = {}
            for run in reversed(runs):
                worktree = str(run["worktree"])
                if worktree not in seen:
                    seen[worktree] = run
            runs = list(seen.values())

        if not runs:
            typer.echo("No runs found.")
            return

        typer.echo(f"{'ID':<6} {'STATUS':<12} {'STARTED':>10} {'DONE':>5} {'FAIL':>5} WORKTREE")
        for run_row in runs:
            events = db.get_events(int(run_row["id"]))
            started = sum(1 for event in events if event["event"] == "started")
            completed = sum(1 for event in events if event["event"] == "completed")
            failed = sum(1 for event in events if event["event"] == "failed")
            status_str = _colored_status(run_row["status"])
            worktree_name = Path(run_row["worktree"]).name
            typer.echo(
                f"{run_row['id']:<6} {status_str:<12} {started:>10} {completed:>5} {failed:>5} {worktree_name}"
            )
    finally:
        db.close()


@app.command()
def wait(
    path: str = typer.Argument(..., help="Worktree path"),
    timeout: Optional[int] = typer.Option(
        None, "--timeout", "-t", help="Max seconds to wait"
    ),
) -> None:
    """Poll every second until the latest run is no longer running."""
    _ensure_initialized()
    target = str(Path(path).resolve())
    db = _db()
    db.initialize()
    start_time = time.monotonic()
    try:
        while True:
            if timeout is not None and (time.monotonic() - start_time) > timeout:
                typer.echo(
                    f"Timed out after {timeout}s waiting for run to complete.", err=True
                )
                raise typer.Exit(code=2)
            recover_orphans(db)
            run_row = db.get_latest_run(target)
            if run_row is None:
                typer.echo(
                    f"No runs for {target}. Use 'cmcs run {path}' to start a run.",
                    err=True,
                )
                raise typer.Exit(code=1)
            if run_row["status"] != "running":
                typer.echo(f"Run {run_row['id']} is {_colored_status(run_row['status'])}")
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
        recover_orphans(db)
        running = [
            run_row
            for run_row in db.get_running_runs()
            if str(run_row["worktree"]) == target
        ]
        if not running:
            typer.echo(
                "No running flow for this path. Use 'cmcs status' to check run states.",
                err=True,
            )
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
            else:
                # Wait briefly for graceful shutdown before escalating.
                for _ in range(10):
                    time.sleep(0.5)
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        break
                    except PermissionError:
                        break
                else:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass

        db.finish_run(int(run_row["id"]), "stopped")
        typer.echo(f"Stopped run {run_row['id']}: {_colored_status('stopped')}")
    finally:
        db.close()


@app.command()
def logs(
    path: str = typer.Argument(..., help="Worktree path"),
    lines: int = typer.Option(
        4096, "--lines", "-n", help="Bytes to tail from each log file"
    ),
    follow: bool = typer.Option(
        False, "--follow", "-f", help="Follow log output (poll every 2s)"
    ),
) -> None:
    """Show log file output for the latest run."""
    _ensure_initialized()
    target = str(Path(path).resolve())
    db = _db()
    db.initialize()
    try:
        recover_orphans(db)
        run_row = db.get_latest_run(target)
    finally:
        db.close()

    if run_row is None:
        typer.echo(
            "No runs for this path. Use 'cmcs run <path>' to start a run.",
            err=True,
        )
        raise typer.Exit(code=1)

    log_dir = Path(run_row["worktree"]) / ".cmcs" / "logs" / str(run_row["id"])
    if not log_dir.exists():
        typer.echo(
            f"No log artifacts found at {log_dir}. The run may not have produced output.",
            err=True,
        )
        raise typer.Exit(code=1)

    log_files = sorted(path for path in log_dir.iterdir() if path.is_file())
    if not log_files:
        typer.echo(
            f"No log artifacts found at {log_dir}. The run may not have produced output.",
            err=True,
        )
        raise typer.Exit(code=1)

    for log_file in log_files:
        typer.echo(f"=== {log_file.name} ===")
        content = _tail_text(log_file, size=lines)
        typer.echo(content.rstrip() or "(empty)")

    if follow:
        last_sizes = {lf: lf.stat().st_size for lf in log_files}
        while True:
            time.sleep(2)
            for log_file in log_files:
                current_size = log_file.stat().st_size if log_file.exists() else 0
                prev_size = last_sizes.get(log_file, 0)
                if current_size > prev_size:
                    with log_file.open("rb") as f:
                        f.seek(prev_size)
                        new_data = f.read()
                    typer.echo(new_data.decode("utf-8", errors="replace"), nl=False)
                    last_sizes[log_file] = current_size


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
