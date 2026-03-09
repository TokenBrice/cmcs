from __future__ import annotations

from pathlib import Path
import tempfile

from cmcs.config import CmcsConfig, CodexConfig, load_config


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


def test_load_config_null_section(tmp_path: Path):
    """Config with null section values should not crash."""
    cmcs_dir = tmp_path / ".cmcs"
    cmcs_dir.mkdir()
    (cmcs_dir / "config.yml").write_text("codex: null\ndashboard: null\n", encoding="utf-8")

    cfg = load_config(tmp_path)

    assert cfg.codex.model == "gpt-5.3-codex"
    assert cfg.dashboard.port == 4173


def test_load_config_unknown_nested_keys(tmp_path: Path):
    """Config with unknown nested keys should not crash."""
    cmcs_dir = tmp_path / ".cmcs"
    cmcs_dir.mkdir()
    (cmcs_dir / "config.yml").write_text(
        "codex:\n  model: custom-model\n  unknown_key: value\n",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)

    assert cfg.codex.model == "custom-model"


def test_load_config_malformed_yaml(tmp_path: Path):
    """Malformed YAML should fall back to defaults."""
    cmcs_dir = tmp_path / ".cmcs"
    cmcs_dir.mkdir()
    (cmcs_dir / "config.yml").write_text("codex:\n  model: 'unclosed\n", encoding="utf-8")

    cfg = load_config(tmp_path)

    assert cfg.codex.model == "gpt-5.3-codex"


def test_load_config_invalid_port_type(tmp_path: Path) -> None:
    """Non-integer port should not crash config loading."""
    cmcs_dir = tmp_path / ".cmcs"
    cmcs_dir.mkdir()
    (cmcs_dir / "config.yml").write_text("dashboard:\n  port: not-a-number\n", encoding="utf-8")

    cfg = load_config(tmp_path)

    if isinstance(cfg.dashboard.port, int):
        assert cfg.dashboard.port == 4173
    else:
        assert cfg.dashboard.port == "not-a-number"


def test_load_config_empty_model(tmp_path: Path) -> None:
    """Empty model string should be handled without crashing."""
    cmcs_dir = tmp_path / ".cmcs"
    cmcs_dir.mkdir()
    (cmcs_dir / "config.yml").write_text("codex:\n  model: ''\n", encoding="utf-8")

    cfg = load_config(tmp_path)

    assert cfg.codex.model in {"", "gpt-5.3-codex"}


def test_load_config_non_mapping_top_level(tmp_path: Path) -> None:
    """Top-level non-mapping YAML should fall back to defaults."""
    cmcs_dir = tmp_path / ".cmcs"
    cmcs_dir.mkdir()
    (cmcs_dir / "config.yml").write_text("- just\n- a\n- list\n", encoding="utf-8")

    cfg = load_config(tmp_path)

    assert cfg.codex.model == "gpt-5.3-codex"
    assert cfg.dashboard.port == 4173


def test_codex_config_defaults():
    """New fields should have correct defaults."""
    cfg = CodexConfig()
    assert cfg.auto_commit is True
    assert cfg.fallback_model is None


def test_codex_config_custom_values():
    """New fields should accept custom values."""
    cfg = CodexConfig(auto_commit=False, fallback_model="gpt-5.1-codex-max")
    assert cfg.auto_commit is False
    assert cfg.fallback_model == "gpt-5.1-codex-max"


def test_load_config_with_new_fields(tmp_path: Path):
    """Config YAML with new fields should parse correctly."""
    cmcs_dir = tmp_path / ".cmcs"
    cmcs_dir.mkdir()
    (cmcs_dir / "config.yml").write_text(
        "codex:\n"
        "  auto_commit: false\n"
        "  fallback_model: gpt-5.1-codex-max\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert cfg.codex.auto_commit is False
    assert cfg.codex.fallback_model == "gpt-5.1-codex-max"


def test_load_config_defaults_new_fields(tmp_path: Path):
    """Config YAML without new fields should use defaults."""
    cmcs_dir = tmp_path / ".cmcs"
    cmcs_dir.mkdir()
    (cmcs_dir / "config.yml").write_text(
        "codex:\n  model: gpt-5.4\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert cfg.codex.auto_commit is True
    assert cfg.codex.fallback_model is None
