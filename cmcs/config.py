"""Config loading for cmcs with defaults and YAML overrides."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CodexConfig:
    model: str = "gpt-5.3-codex"
    args: list[str] = field(
        default_factory=lambda: [
            "--yolo", "exec",
            "--sandbox", "danger-full-access",
            "-c", "reasoning_effort=xhigh",
        ]
    )


@dataclass
class WorktreeConfig:
    root: str = "worktrees"
    start_point: str = "master"


@dataclass
class DashboardConfig:
    port: int = 4173


@dataclass
class TicketDirConfig:
    dir: str = ".cmcs/tickets"


@dataclass
class CmcsConfig:
    codex: CodexConfig = field(default_factory=CodexConfig)
    worktrees: WorktreeConfig = field(default_factory=WorktreeConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    tickets: TicketDirConfig = field(default_factory=TicketDirConfig)


DEFAULTS = CmcsConfig()


def _merge(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override values into defaults."""
    merged = dict(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(repo_root: Path) -> CmcsConfig:
    """Load config from .cmcs/config.yml and merge with defaults."""
    config_path = repo_root / ".cmcs" / "config.yml"

    overrides: dict[str, Any]
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        overrides = loaded if isinstance(loaded, dict) else {}
    else:
        overrides = {}

    merged = _merge(asdict(DEFAULTS), overrides)
    return CmcsConfig(
        codex=CodexConfig(**merged.get("codex", {})),
        worktrees=WorktreeConfig(**merged.get("worktrees", {})),
        dashboard=DashboardConfig(**merged.get("dashboard", {})),
        tickets=TicketDirConfig(**merged.get("tickets", {})),
    )
