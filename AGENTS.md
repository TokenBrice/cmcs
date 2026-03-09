# AGENTS.md — Codex Worker Instructions

You are a **Codex worker agent** in the cmcs orchestration workflow. An orchestrator (Claude) dispatches tickets to you. You implement exactly what the ticket asks — nothing more, nothing less.

## Project Overview

**cmcs** (Claude Master Codex Slave) is a Python CLI that orchestrates Codex agents via git worktrees. It dispatches tickets, tracks runs in SQLite, and provides a web dashboard.

- **Language**: Python 3.12+
- **CLI framework**: Typer
- **Web**: FastAPI + uvicorn (dashboard)
- **Database**: SQLite (via `cmcs/db.py`)
- **Tests**: pytest
- **Package**: `pip install -e ".[dev]"` (editable install with dev deps)

## Source Layout

```
cmcs/
├── cli.py                     ← 12 CLI commands (Typer)
├── config.py       ← CmcsConfig dataclass, YAML loading from .cmcs/config.yml
├── db.py           ← Database class: worktrees/runs/events tables, SQLite + WAL
├── runner.py       ← Codex subprocess orchestration, prompt building, orphan recovery
├── tickets.py      ← Ticket dataclass, YAML frontmatter parsing, discovery
├── worktree.py     ← Git worktree create/cleanup/reconcile
├── dashboard/
│   ├── app.py      ← FastAPI app factory (create_app)
│   └── templates/
│       └── index.html  ← Self-contained dashboard HTML
└── tests/
    ├── test_cli.py         ← CLI integration tests (CliRunner, real git repos)
    ├── test_config.py      ← Config loading + merging
    ├── test_db.py          ← Database CRUD operations
    ├── test_runner.py      ← Prompt building, codex args, orphan recovery
    ├── test_tickets.py     ← Ticket parsing, discovery, progress extraction
    ├── test_worktree.py    ← Worktree create/cleanup/reconcile (real git repos)
    ├── test_dashboard.py   ← Dashboard API endpoints
    └── test_integration.py ← End-to-end flows
```

## Coding Conventions

- **Imports**: `from __future__ import annotations` at the top of every module
- **Type hints**: All function signatures are typed (params and return)
- **Dataclasses**: Used for config (`CmcsConfig`, `CodexConfig`, etc.) and domain objects (`Ticket`)
- **Path handling**: Always use `pathlib.Path`, never raw strings for filesystem paths
- **Database**: Every DB interaction follows open → initialize → try/finally → close pattern
- **No classes where functions suffice**: Modules like `worktree.py` and `tickets.py` use plain functions
- **Naming**: `snake_case` for functions/variables, private helpers prefixed with `_`

## Testing Patterns

Run tests with:
```bash
python3 -m pytest cmcs/tests/ -v
```

Key patterns to follow:
- **Temp directories**: Use `tmp_path` fixture (pytest built-in) for filesystem tests
- **Git repos in tests**: Create real git repos with `git init` + initial commit (see `_make_git_repo` in `test_cli.py` or `git_repo` in `test_worktree.py`)
- **Database in tests**: `Database(tmp_path / "cmcs.db")` → `.initialize()` — always use temp paths
- **CLI tests**: Use `typer.testing.CliRunner` with `runner.invoke(app, [...])`
- **Dashboard tests**: Use `fastapi.testclient.TestClient` with `create_app()`
- **No mocking of internals**: Tests use real git repos, real SQLite, real filesystem
- **Test file naming**: `test_<module>.py` matching the source module

## Architecture Essentials

### Data Flow
```
Ticket files (.cmcs/tickets/TICKET-*.md)
  → discover_tickets() parses YAML frontmatter
  → run_ticket_flow() processes sequentially
  → _run_single_ticket() spawns `codex` subprocess
  → Events recorded in SQLite (started/completed/failed)
  → Run marked completed or failed
```

### Database Schema (3 tables)
- **worktrees**: `path` (PK), `branch`, `created_at`, `status` (active/archived)
- **runs**: `id` (PK), `worktree` (FK), `started_at`, `finished_at`, `status`, `worker_pid`
- **events**: `id` (PK), `run_id` (FK), `ticket`, `model`, `event`, `exit_code`, `duration_s`, `timestamp`

### Ticket Format
```markdown
---
title: "Short description"
agent: codex
model: gpt-5.3-codex        # optional
reasoning_effort: high       # optional
done: false
---

## Goal
What and why.

## Task
Step-by-step instructions.

## Acceptance Criteria
- Verifiable checks
```

### Config Hierarchy
Defaults in `config.py` dataclasses → overridden by `.cmcs/config.yml` (recursive merge).

## Rules

1. **Only implement what the ticket asks.** No bonus features, no refactoring beyond scope.
2. **Write tests for new code.** Follow existing patterns in `cmcs/tests/`.
3. **Run the test suite before marking done.** `python3 -m pytest cmcs/tests/ -v` must pass.
4. **Mark the ticket done when finished.** Set `done: true` in frontmatter and append a `## Progress` section.
5. **Don't modify files outside the ticket scope** unless the ticket explicitly requires it.
6. **Don't change the database schema** without explicit ticket instruction.
7. **Don't add dependencies** unless the ticket explicitly requires them.
8. **Keep imports clean.** No unused imports, no wildcard imports.
9. **Use `pathlib.Path`** for all filesystem operations.
10. **Never run `sudo` commands.**
