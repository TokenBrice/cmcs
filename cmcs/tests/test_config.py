from pathlib import Path
import tempfile

from cmcs.config import load_config


def test_defaults_when_no_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = load_config(Path(tmpdir))

        assert cfg.codex.model == "gpt-5.3-codex"
        assert cfg.codex.timeout_s == 1800
        assert cfg.codex.args == ["--yolo", "exec", "--sandbox", "danger-full-access", "-c", "reasoning_effort=xhigh"]
        assert cfg.worktrees.root == "worktrees"
        assert cfg.worktrees.start_point == "master"
        assert cfg.dashboard.port == 4173
        assert cfg.tickets.dir == ".cmcs/tickets"


def test_partial_override():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        config_file = root / ".cmcs" / "config.yml"
        config_file.parent.mkdir(parents=True)
        config_file.write_text("codex:\n  model: gpt-5.1-codex-mini\n", encoding="utf-8")

        cfg = load_config(root)

        assert cfg.codex.model == "gpt-5.1-codex-mini"
        assert cfg.codex.timeout_s == 1800
        assert cfg.codex.args == ["--yolo", "exec", "--sandbox", "danger-full-access", "-c", "reasoning_effort=xhigh"]
        assert cfg.worktrees.root == "worktrees"
        assert cfg.worktrees.start_point == "master"
        assert cfg.dashboard.port == 4173
        assert cfg.tickets.dir == ".cmcs/tickets"


def test_full_override():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        config_file = root / ".cmcs" / "config.yml"
        config_file.parent.mkdir(parents=True)
        config_file.write_text(
            "codex:\n"
            "  model: gpt-5.2-codex\n"
            "  timeout_s: 120\n"
            "  args: ['--yolo', 'exec']\n"
            "worktrees:\n"
            "  root: wt\n"
            "  start_point: main\n"
            "dashboard:\n"
            "  port: 8080\n"
            "tickets:\n"
            "  dir: tickets\n",
            encoding="utf-8",
        )

        cfg = load_config(root)

        assert cfg.codex.model == "gpt-5.2-codex"
        assert cfg.codex.timeout_s == 120
        assert cfg.codex.args == ["--yolo", "exec"]
        assert cfg.worktrees.root == "wt"
        assert cfg.worktrees.start_point == "main"
        assert cfg.dashboard.port == 8080
        assert cfg.tickets.dir == "tickets"
