# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[0.1.0]: https://github.com/TokenBrice/cmcs/releases/tag/v0.1.0
