"""Config loading for cmcs with defaults and YAML overrides."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CodexConfig:
    model: str = "gpt-5.3-codex"
    command: str = "codex"
    timeout_s: int = 1800
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
        try:
            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            overrides = {}
        else:
            overrides = loaded if isinstance(loaded, dict) else {}
    else:
        overrides = {}

    merged = _merge(asdict(DEFAULTS), overrides)

    def _safe_construct(cls: type[Any], data: Any) -> Any:
        """Construct a dataclass, ignoring unknown keys and handling None."""
        if not isinstance(data, dict):
            return cls()
        known_fields = set(cls.__dataclass_fields__)
        filtered = {key: value for key, value in data.items() if key in known_fields and value is not None}
        return cls(**filtered)

    return CmcsConfig(
        codex=_safe_construct(CodexConfig, merged.get("codex")),
        worktrees=_safe_construct(WorktreeConfig, merged.get("worktrees")),
        dashboard=_safe_construct(DashboardConfig, merged.get("dashboard")),
        tickets=_safe_construct(TicketDirConfig, merged.get("tickets")),
    )
