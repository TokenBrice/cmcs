# cmcs

> Orchestration CLI for the Claude-Master / Codex-Slave workflow.

cmcs is a lightweight broker between Claude (the orchestrator) and Codex (the worker).
Claude decomposes tasks and reviews output. cmcs dispatches tickets as Codex subprocesses
and tracks state. Codex executes. ~2,000 LOC, 12 commands, direct subprocess invocation.

## Three-Layer Model

```text
┌─────────────────────────────────────────────┐
│          Claude (Opus) — Orchestrator      │
│  Plans, decomposes, writes tickets, reviews │
└──────────────────┬──────────────────────────┘
                   │ writes tickets / reads results
┌──────────────────▼──────────────────────────┐
│               cmcs — Broker                 │
│  Runs Codex subprocesses, tracks run state  │
└──────────────────┬──────────────────────────┘
                   │ dispatches work / collects output
┌──────────────────▼──────────────────────────┐
│           Codex CLI — Worker Agent(s)       │
│  Executes tickets on the filesystem          │
└─────────────────────────────────────────────┘
```

## Install

From the repository root:

```bash
pip install -e ".[dev]"
```

Requires Python 3.12+.

## Quick Start

```bash
cmcs init
# write .cmcs/tickets/TICKET-001.md (see example below)
cmcs run .
cmcs status
cmcs dashboard
```

### Minimal ticket

```markdown
---
title: "Add README section"
agent: "codex"
done: false
---

## Goal
Document project setup.

## Task
1. Update README.md with setup steps.

## Acceptance Criteria
- README includes setup steps
```

For ticket writing guidelines and advanced patterns, see the
[Orchestration Guide](docs/orchestration-guide.md).

## Commands

| Command | Description |
|---------|-------------|
| `cmcs --help` | Show top-level help and command groups |
| `cmcs init` | Initialize `.cmcs/` (db, tickets, logs) in current repo |
| `cmcs config show` | Print effective config |
| `cmcs worktree create <branch>` | Create git worktree and register in DB |
| `cmcs worktree list` | Show registered worktrees and latest run status |
| `cmcs worktree cleanup <branch>` | Remove worktree, delete branch, archive in DB |
| `cmcs run [path]` | Process tickets for repo/worktree (default: `.`) |
| `cmcs status [path]` | Show run status and ticket counts |
| `cmcs wait <path>` | Block until latest run completes |
| `cmcs stop <path>` | Stop latest running worker for path |
| `cmcs logs <path>` | Print tail of log files for latest run |
| `cmcs dashboard` | Start web dashboard |

## Documentation

- **[Architecture](docs/architecture.md)** — three-layer model, state management,
  parallelism, dashboard
- **[Orchestration Guide](docs/orchestration-guide.md)** — ticket writing,
  dispatch patterns, review checklist
- **[Configuration](docs/configuration.md)** — config file reference, defaults,
  ticket frontmatter fields

## Project Layout

```text
.
├── .cmcs/
│   ├── cmcs.db
│   ├── tickets/
│   │   └── TICKET-001.md
│   └── logs/
│       └── <run-id>/
├── cmcs/
│   ├── cli.py
│   ├── config.py
│   ├── db.py
│   ├── runner.py
│   ├── tickets.py
│   ├── worktree.py
│   ├── dashboard/
│   │   ├── app.py
│   │   └── templates/
│   └── tests/
├── docs/
│   ├── architecture.md
│   ├── orchestration-guide.md
│   └── configuration.md
├── pyproject.toml
└── README.md
```
