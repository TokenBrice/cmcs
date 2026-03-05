"""FastAPI dashboard application for cmcs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from cmcs.db import Database


def _open_db(db_path: Path) -> Database:
    db = Database(db_path)
    db.initialize()
    return db


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

    app = FastAPI(title="cmcs dashboard")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/worktrees")
    def worktrees() -> list[dict[str, Any]]:
        db = _open_db(db_path)
        try:
            return db.list_worktrees()
        finally:
            db.close()

    @app.get("/api/runs")
    def runs() -> list[dict[str, Any]]:
        db = _open_db(db_path)
        try:
            enriched: list[dict[str, Any]] = []
            for run in db.all_runs():
                events = db.get_events(int(run["id"]))
                tickets_done, tickets_total = _ticket_counts(events)
                row = dict(run)
                row["tickets_done"] = tickets_done
                row["tickets_total"] = tickets_total
                enriched.append(row)
            return enriched
        finally:
            db.close()

    @app.get("/api/runs/{run_id}/events")
    def run_events(run_id: int) -> list[dict[str, Any]]:
        db = _open_db(db_path)
        try:
            return db.get_events(run_id)
        finally:
            db.close()

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(content=template_html)

    return app
