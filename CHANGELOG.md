# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-03-09

Systematic self-improvement: 46 tickets across 9 phases, executed via cmcs itself. Test count 46 → 106.

### Added

- `cmcs version` command
- `cmcs status --active` and `--latest` filters
- `cmcs wait --timeout` option for time-bounded polling
- `cmcs logs --lines` and `--follow` options for flexible log tailing
- `cmcs run --dry-run` flag to preview pending tickets
- `cmcs ticket validate` subcommand for checking ticket YAML
- `cmcs clean` command to remove old logs and archived worktrees
- Agent field filtering: non-codex tickets are skipped during runs
- Configurable worker command via `codex.command` config
- JSON structured logging per ticket (timing, exit code, log paths)
- Dashboard: stop action and log viewing modal
- Dashboard: inline events in runs API (eliminates N+1 fetch)
- Dashboard: pagination for `/api/runs` endpoint
- Dashboard: orphan recovery and 404 handling
- Colored status output in CLI (run status, worktree list)
- Aligned fixed-width columns in `status` and `worktree list`
- PEP 561 `py.typed` marker and mypy configuration
- `from __future__ import annotations` across all source files
- 60 new tests (46 → 106)

### Fixed

- Auto-register worktree path before creating run (crash fix)
- Log path resolution for worktree runs
- YAML parsing crash on malformed frontmatter
- `done` field coercion for unknown string values
- XSS vulnerability: replaced all `innerHTML` with safe DOM APIs
- Database double-finish guard (prevents status corruption)
- SQLite busy timeout for concurrent access
- `_tail_text` UTF-8 boundary handling
- Stop command: verify process termination with SIGKILL escalation
- Orphan run recovery called consistently across all commands
- Safe branch delete in worktree cleanup (prevents unmerged data loss)
- Subprocess PID recording for reliable process management
- Dashboard database lifecycle (proper open/close)
- Configurable subprocess timeout (was hardcoded)

### Changed

- Config validation: reject invalid types, warn on unknown keys
- Ticket frontmatter: handle malformed YAML gracefully with warnings
- Error messages include actionable guidance (e.g., "Run 'cmcs run' to start")
- Documentation accuracy: command count, config defaults, isolation claims
- `Optional[X]` → `X | None` type annotations throughout
- `_repo_root()` cached per process for performance
- Removed trivial `list_worktrees` wrapper from `worktree.py`
- Deduplicated test fixtures via shared conftest

## [0.1.0] - 2026-03-06

Initial release of cmcs — Claude Master Codex Slave orchestration CLI.

### Added

- 11 CLI commands via Typer: `init`, `config show`, `worktree create/list/cleanup`, `run`, `status`, `wait`, `stop`, `logs`, `dashboard`
- Git worktree management for parallel agent workspaces
- Codex subprocess orchestration (`runner.py`)
- Ticket parsing and discovery with YAML frontmatter support
- Per-ticket `reasoning_effort` override and default `xhigh` setting
- SQLite state tracking for runs, events, and worktrees
- Web dashboard (FastAPI + self-contained HTML)
- Configuration loading with sensible defaults
- CLAUDE.md orchestrator instructions for Claude Code integration
- Claude Code skill for structured two-stage review workflow
- 35 tests at release, now 95 (unit + integration)
- Documentation: architecture guide, orchestration playbook, configuration reference, full ticket example
- Project logo (SVG and PNG)

[0.2.0]: https://github.com/TokenBrice/cmcs/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/TokenBrice/cmcs/releases/tag/v0.1.0
