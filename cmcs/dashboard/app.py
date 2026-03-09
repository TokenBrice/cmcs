"""FastAPI dashboard application for cmcs."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from cmcs.db import Database


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
    async def runs() -> list[dict[str, Any]]:
        dashboard_db = _database()
        enriched: list[dict[str, Any]] = []
        for run in dashboard_db.all_runs():
            events = dashboard_db.get_events(int(run["id"]))
            tickets_done, tickets_total = _ticket_counts(events)
            row = dict(run)
            row["tickets_done"] = tickets_done
            row["tickets_total"] = tickets_total
            enriched.append(row)
        return enriched

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: int) -> list[dict[str, Any]]:
        return _database().get_events(run_id)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(content=template_html)

    return app
