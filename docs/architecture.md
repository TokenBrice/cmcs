# Architecture

## Three-Layer Model

```
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

### Claude (Orchestrator)

- Decomposes user requests into discrete, testable tasks
- Writes ticket files with structured Goal / Task / Acceptance Criteria
- Decides between sequential and parallel dispatch
- Reviews every piece of Codex output before accepting
- Merges approved work back to the main branch
- Operates asynchronously through ticket artifacts and run status

### cmcs (Broker)

- Purpose-built orchestration layer for Claude-Master/Codex-Slave
- Directly spawns `codex` subprocesses (no app-server or JSON-RPC chain)
- Reads ticket metadata (including optional per-ticket `model` override)
- Tracks runtime state in SQLite at `.cmcs/cmcs.db`
- Stores per-ticket stdout/stderr artifacts under `.cmcs/logs/<run-id>/`
- Provides CLI and dashboard observability for runs, events, and outcomes

### Codex (Worker)

- Codex CLI process invoked by `cmcs` with configured args/model
- Reads a single active ticket prompt, edits files, and updates the ticket
- Sets `done: true` in ticket frontmatter when finished
- Appends a `## Progress` section describing changes made
- One running Codex worker per `cmcs run` process

## State Model

State is intentionally split so humans and automation each have a clean source of truth.

- **Ticket state (human-readable):** markdown files in `.cmcs/tickets/`
- **Runtime state (machine-managed):** SQLite database `.cmcs/cmcs.db`
- **Execution artifacts:** per-ticket logs in `.cmcs/logs/<run-id>/`
- **Code state:** repository files tracked with git

```
repo (master)
├── .cmcs/
│   ├── tickets/
│   │   ├── TICKET-001.md
│   │   └── TICKET-002.md
│   ├── cmcs.db
│   └── logs/
│       └── <run-id>/
│           ├── TICKET-001.stdout
│           └── TICKET-001.stderr
├── worktrees/
│   ├── feature-a/
│   │   └── .cmcs/tickets/
│   └── feature-b/
│       └── .cmcs/tickets/
└── src/...
```

## Parallelism Model

`cmcs` processes tickets sequentially per run, so parallelism is achieved at the worktree level.

| Dimension | Sequential | Parallel |
|-----------|-----------|----------|
| Scope | One repo/worktree, ordered tickets | Multiple worktrees, each with own ticket queue |
| Startup | `cmcs run <path>` | `cmcs worktree create <branch>` + multiple `cmcs run <path>` |
| Agents | 1 Codex worker process | N Codex worker processes (one per active run) |
| Use case | Dependent tasks (A then B) | Independent tasks (A and B share no mutable state) |
| Integration | Same branch workflow | Merge worktree branches back to master |

### When to use which

- **Sequential:** tasks that build on prior outputs.
- **Parallel:** independent features/files that can be reviewed separately.
- **Hybrid:** multiple worktrees in parallel, each with a sequential ticket chain.

## Observability

- `cmcs status [<path>]` shows run status and ticket event counts
- `cmcs logs <path>` shows recent per-ticket stdout/stderr output
- `cmcs wait <path>` blocks until the latest run is no longer running
- `cmcs dashboard` serves a local web UI for visual run monitoring

## Constraints

- Claude reviews every work unit before merge; no auto-merge
- Codex is expected to edit files directly to satisfy ticket requirements
- Ticket completion contract remains explicit: `done: true` + `## Progress`
- No hidden broker state: ticket files and SQLite records are inspectable
