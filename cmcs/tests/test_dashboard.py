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


def test_runs_include_events(tmp_path: Path) -> None:
    """API /api/runs should include events in each run."""
    cmcs_dir = tmp_path / ".cmcs"
    cmcs_dir.mkdir()

    db = Database(cmcs_dir / "cmcs.db")
    db.initialize()
    db.register_worktree("/tmp/wt", "main")
    run_id = db.create_run("/tmp/wt", worker_pid=1)
    db.record_event(run_id, "TICKET-001", "started", model="test")
    db.close()

    with TestClient(create_app(tmp_path)) as test_client:
        response = test_client.get("/api/runs")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "events" in data[0]
    assert len(data[0]["events"]) == 1


def test_runs_pagination(tmp_path: Path) -> None:
    """API /api/runs should support limit and offset."""
    cmcs_dir = tmp_path / ".cmcs"
    cmcs_dir.mkdir()

    db = Database(cmcs_dir / "cmcs.db")
    db.initialize()
    db.register_worktree("/tmp/wt", "main")
    for i in range(5):
        run_id = db.create_run("/tmp/wt", worker_pid=i)
        db.finish_run(run_id, "completed")
    db.close()

    with TestClient(create_app(tmp_path)) as test_client:
        response = test_client.get("/api/runs?limit=2&offset=0")
        assert response.status_code == 200
        assert len(response.json()) == 2

        response = test_client.get("/api/runs?limit=2&offset=3")
        assert response.status_code == 200
        assert len(response.json()) == 2


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


def test_run_events_404_for_nonexistent(tmp_path: Path) -> None:
    """Events endpoint should return 404 for non-existent run."""
    _seed_dashboard_db(tmp_path)
    with TestClient(create_app(tmp_path)) as test_client:
        response = test_client.get("/api/runs/999/events")
    assert response.status_code == 404


def test_index_page(tmp_path: Path) -> None:
    _seed_dashboard_db(tmp_path)
    with TestClient(create_app(tmp_path)) as test_client:
        response = test_client.get("/")
    assert response.status_code == 200
    assert "cmcs" in response.text.lower()


def test_xss_safe_worktree_name(tmp_path: Path) -> None:
    """Worktree names with HTML should not be rendered as HTML."""
    cmcs_dir = tmp_path / ".cmcs"
    cmcs_dir.mkdir()

    db = Database(cmcs_dir / "cmcs.db")
    db.initialize()
    db.register_worktree("/tmp/<script>alert(1)</script>", "xss-branch")
    db.close()

    app = create_app(tmp_path)
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "innerHTML" not in response.text

    worktrees = TestClient(app).get("/api/worktrees")
    assert worktrees.status_code == 200
    data = worktrees.json()
    assert any("<script>" in str(wt.get("path", "")) for wt in data)
