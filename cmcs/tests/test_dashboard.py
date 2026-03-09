"""Tests for cmcs.dashboard.app."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from cmcs.dashboard.app import create_app
from cmcs.db import Database


def _seed_dashboard_db(tmp_path: Path) -> None:
    cmcs_dir = tmp_path / ".cmcs"
    cmcs_dir.mkdir()

    db = Database(cmcs_dir / "cmcs.db")
    db.initialize()
    db.register_worktree("/tmp/worktrees/feature-a", "feature-a")

    run_id = db.create_run("/tmp/worktrees/feature-a", worker_pid=12345)
    db.record_event(run_id, "TICKET-001.md", "started", model="gpt-5.3-codex")
    db.record_event(
        run_id,
        "TICKET-001.md",
        "completed",
        model="gpt-5.3-codex",
        exit_code=0,
        duration_s=45.2,
    )
    db.finish_run(run_id, "completed")
    db.close()


def test_health(tmp_path: Path) -> None:
    _seed_dashboard_db(tmp_path)
    with TestClient(create_app(tmp_path)) as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_worktrees(tmp_path: Path) -> None:
    _seed_dashboard_db(tmp_path)
    with TestClient(create_app(tmp_path)) as test_client:
        response = test_client.get("/api/worktrees")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["branch"] == "feature-a"


def test_runs(tmp_path: Path) -> None:
    _seed_dashboard_db(tmp_path)
    with TestClient(create_app(tmp_path)) as test_client:
        response = test_client.get("/api/runs")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["status"] == "completed"
    assert payload[0]["tickets_done"] == 1
    assert payload[0]["tickets_total"] == 1


def test_run_events(tmp_path: Path) -> None:
    _seed_dashboard_db(tmp_path)
    with TestClient(create_app(tmp_path)) as test_client:
        response = test_client.get("/api/runs/1/events")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["event"] == "started"
    assert payload[1]["event"] == "completed"
    assert payload[1]["duration_s"] == 45.2


def test_index_page(tmp_path: Path) -> None:
    _seed_dashboard_db(tmp_path)
    with TestClient(create_app(tmp_path)) as test_client:
        response = test_client.get("/")
    assert response.status_code == 200
    assert "cmcs" in response.text.lower()
