"""FastAPI dashboard application for cmcs."""

from __future__ import annotations

import os
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from cmcs.db import Database
from cmcs.runner import recover_orphans


def _ticket_counts(events: list[dict[str, Any]]) -> tuple[int, int]:
    tickets_total = {str(event["ticket"]) for event in events}
    tickets_done = {
        str(event["ticket"])
        for event in events
        if str(event.get("event", "")) == "completed"
    }
    return len(tickets_done), len(tickets_total)


def create_app(repo_root: Path) -> FastAPI:
    """Create the dashboard FastAPI app bound to a repo's cmcs database."""
    db_path = Path(repo_root) / ".cmcs" / "cmcs.db"
    template_path = Path(__file__).parent / "templates" / "index.html"
    template_html = template_path.read_text(encoding="utf-8")

    db: Database | None = None

    def _database() -> Database:
        nonlocal db
        if db is None:
            db = Database(db_path)
            db.initialize()
        return db

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal db
        _database()
        try:
            yield
        finally:
            if db is not None:
                db.close()
                db = None

    app = FastAPI(title="cmcs dashboard", lifespan=lifespan)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/worktrees")
    async def worktrees() -> list[dict[str, Any]]:
        return _database().list_worktrees()

    @app.get("/api/runs")
    async def runs(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        dashboard_db = _database()
        recover_orphans(dashboard_db)
        all_runs = dashboard_db.all_runs()
        paginated = all_runs[offset : offset + limit]
        enriched: list[dict[str, Any]] = []
        for run in paginated:
            events = dashboard_db.get_events(int(run["id"]))
            tickets_done, tickets_total = _ticket_counts(events)
            row = dict(run)
            row["events"] = events
            row["tickets_done"] = tickets_done
            row["tickets_total"] = tickets_total
            enriched.append(row)
        return enriched

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: int) -> list[dict[str, Any]]:
        dashboard_db = _database()
        run = dashboard_db.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return dashboard_db.get_events(run_id)

    @app.post("/api/runs/{run_id}/stop")
    async def stop_run(run_id: int) -> dict[str, str | int]:
        dashboard_db = _database()
        run = dashboard_db.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        if run["status"] != "running":
            raise HTTPException(status_code=400, detail=f"Run {run_id} is not running")

        pid = run.get("worker_pid")
        if isinstance(pid, int) and pid > 0:
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass

        dashboard_db.finish_run(run_id, "stopped")
        return {"status": "stopped", "run_id": run_id}

    @app.get("/api/runs/{run_id}/logs")
    async def run_logs(run_id: int) -> list[dict[str, str]]:
        dashboard_db = _database()
        run = dashboard_db.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        log_dir = Path(run["worktree"]) / ".cmcs" / "logs" / str(run_id)
        if not log_dir.exists():
            return []

        logs: list[dict[str, str]] = []
        for log_file in sorted(log_dir.iterdir()):
            if log_file.is_file() and log_file.suffix in (".stdout", ".stderr"):
                content = log_file.read_text(encoding="utf-8", errors="replace")[-4096:]
                logs.append({"name": log_file.name, "content": content})
        return logs

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(content=template_html)

    return app
