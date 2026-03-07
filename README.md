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

## Adopting cmcs in Your Project

### 1. Install the Claude Code skill

```bash
# From your project root
claude skill add /path/to/cmcs/skill
```

This installs the **cmcs-driven-development** skill, which provides a structured two-stage review workflow (spec compliance + code quality) for Codex agent output.

### 2. Add the CLAUDE.md snippet

Copy the contents of [`CLAUDE-SNIPPET.md`](CLAUDE-SNIPPET.md) into your project's `CLAUDE.md`. This gives Claude the orchestrator role, dispatch decision tree, ticket format, and essential commands.

### 3. Reference the guides

For detailed workflow guidance, refer to:
- **[Orchestration Guide](docs/orchestration-guide.md)** — ticket writing, dispatch patterns, review checklist
- **[Large Implementation Preparation](docs/cmcs-large-implementation-preparation.md)** — for projects touching 10+ files or spanning multiple worktrees

## Documentation

- **[Architecture](docs/architecture.md)** — three-layer model, state management,
  parallelism, dashboard
- **[Orchestration Guide](docs/orchestration-guide.md)** — ticket writing,
  dispatch patterns, review checklist
- **[Large Implementation Preparation](docs/cmcs-large-implementation-preparation.md)** — research, design, phased execution, handover documents
- **[Configuration](docs/configuration.md)** — config file reference, defaults,
  ticket frontmatter fields
- **[Skill](skill/)** — Claude Code skill for structured two-stage review workflow

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
├── skill/
│   ├── SKILL.md
│   ├── ticket-template.md
│   ├── spec-reviewer-prompt.md
│   └── code-quality-reviewer-prompt.md
├── docs/
│   ├── architecture.md
│   ├── orchestration-guide.md
│   ├── cmcs-large-implementation-preparation.md
│   └── configuration.md
├── pyproject.toml
└── README.md
```
