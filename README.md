# cmcs

Purpose-built orchestration CLI for the Claude-Master / Codex-Slave workflow.

`cmcs` replaces CAR (`codex-autorunner`) for this repo's day-to-day flow:
- smaller surface area (focused command set instead of a platform-sized CLI)
- direct Codex subprocess execution (no deep JSON-RPC/app-server chain)
- minimal config with only the fields this workflow actually uses

## Install

From the repository root:

```bash
pip install -e ".[dev]"
```

## Quick Start

This walkthrough is the shortest practical path from zero to a running ticket flow.

### 1) Initialize cmcs metadata

Run in repo root:

```bash
cmcs init
```

Creates `.cmcs/cmcs.db`, `.cmcs/tickets/`, and `.cmcs/logs/`.

### 2) Write a ticket file

Create `.cmcs/tickets/TICKET-001.md`:

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

### 3) Run the flow

```bash
cmcs run .
```

`cmcs` will:
1. scan `TICKET-*.md` in order
2. take the first ticket where `done != true`
3. spawn `codex` for that ticket
4. continue until all tickets are done or one ticket fails

### 4) Check status

```bash
cmcs status
```

### 5) Open the dashboard

Run from repo root:

```bash
cmcs dashboard
```

Then open `http://127.0.0.1:4173`.

If you run per-branch worktrees, create and run them with:

```bash
cmcs worktree create feature/readme
cmcs run worktrees/feature/readme
```

## Commands

### Setup

| Command | Syntax | Description |
|---|---|---|
| `cmcs --help` | `cmcs --help` | Show top-level help and command groups. |
| `init` | `cmcs init` | Initialize `.cmcs/` (db, tickets, logs) in current repo. |
| `config show` | `cmcs config show` | Print effective config after merging defaults + `.cmcs/config.yml`. |

### Worktree Management

| Command | Syntax | Description |
|---|---|---|
| `worktree create` | `cmcs worktree create <branch>` | Create git worktree at `<worktrees.root>/<branch>` and register it in DB. |
| `worktree list` | `cmcs worktree list` | Show registered worktrees and their latest run status. |
| `worktree cleanup` | `cmcs worktree cleanup <branch>` | Remove worktree, delete branch, mark worktree as archived in DB. |

### Flow Control

| Command | Syntax | Description |
|---|---|---|
| `run` | `cmcs run [path]` | Process tickets for a repo/worktree path (`.` by default). |
| `status` | `cmcs status [path]` | Show run status and per-run ticket counts (all paths if omitted). |
| `wait` | `cmcs wait <path>` | Block until the latest run for `<path>` is no longer `running`. |
| `stop` | `cmcs stop <path>` | Send SIGTERM to latest running worker for `<path>`, then mark run `stopped`. |
| `logs` | `cmcs logs <path>` | Print tail (last 4KB) of each log file for latest run on `<path>`. |

### Observability

| Command | Syntax | Description |
|---|---|---|
| `dashboard` | `cmcs dashboard` | Start FastAPI dashboard on `127.0.0.1:<dashboard.port>`. |

## Ticket Format

Tickets live in `.cmcs/tickets/` and are discovered with pattern `TICKET-*.md` (sorted alphabetically).

### Frontmatter fields

| Field | Required | Type | Meaning |
|---|---|---|---|
| `title` | yes (recommended) | string | Short ticket summary. |
| `agent` | no | string | Worker name. Defaults to `"codex"` when omitted. |
| `model` | no | string | Per-ticket model override (takes precedence over config default). |
| `done` | yes | bool | Completion flag. Flow picks first ticket where `done != true`. |

### Full ticket example

```markdown
---
title: "Implement dashboard filters"
agent: "codex"
model: "gpt-5.1-codex-mini"
done: false
---

## Goal
Add simple run-status filters to the dashboard.

## Task
1. Add status filter controls in dashboard UI.
2. Filter runs client-side by selected statuses.
3. Update tests for filter behavior.

## Acceptance Criteria
- Running/completed/failed filters work
- Existing dashboard tests pass

## Notes
- Keep UI dependency-free (vanilla JS only)
```

### Model resolution order

1. `model` field in ticket frontmatter (if present)
2. `codex.model` in `.cmcs/config.yml`

## Config

Config file path: `.cmcs/config.yml`

Missing keys fall back to defaults, and nested sections are merged recursively.

### Full config example

```yaml
codex:
  model: gpt-5.3-codex
  args:
    - --yolo
    - exec
    - --sandbox
    - danger-full-access
    - -c
    - reasoning_effort=xhigh

worktrees:
  root: worktrees
  start_point: master

dashboard:
  port: 4173

tickets:
  dir: .cmcs/tickets
```

### Default values

| Key | Default |
|---|---|
| `codex.model` | `gpt-5.3-codex` |
| `codex.args` | `["--yolo", "exec", "--sandbox", "danger-full-access", "-c", "reasoning_effort=xhigh"]` |
| `worktrees.root` | `worktrees` |
| `worktrees.start_point` | `master` |
| `dashboard.port` | `4173` |
| `tickets.dir` | `.cmcs/tickets` |

### Minimal config example

```yaml
codex:
  model: gpt-5.3-codex
```

## Architecture

### Three-layer model

```text
Claude (orchestrator)
    |
    v
cmcs (coordination layer)
    |
    v
Codex (worker subprocesses)
```

### State split

- tickets: markdown files in `.cmcs/tickets/`
- runtime: SQLite database in `.cmcs/cmcs.db` (`worktrees`, `runs`, `events`)
- config: `.cmcs/config.yml`
- logs: `.cmcs/logs/<run-id>/TICKET-xxx.stdout|stderr`

### Direct subprocess invocation

`cmcs` launches Codex directly from `runner.py`:

```python
process = await asyncio.create_subprocess_exec(
    "codex", *config.codex.args, "-m", model, prompt, cwd=repo_path
)
```

## Dashboard

### Access

```bash
cmcs dashboard
```

Open: `http://127.0.0.1:4173` (or your configured `dashboard.port`).

### What it shows

- active and historical runs by worktree
- run status (`running`, `completed`, `failed`, `interrupted`, `stopped`)
- current ticket/model/pid/elapsed time per run
- recent event stream (ticket events, timestamps, duration)

### ASCII mockup

```text
+----------------------------------------------------------------------------------+
| cmcs dashboard                                               updated 23:41:12    |
+----------------------------------------------------------------------------------+
| ACTIVE AGENTS: worktree | status | branch | ticket | model | pid | elapsed      |
| feature/readme          | running | feature/readme | TICKET-002 | gpt-5.3 | 48291 |
| feature/tests           | completed | feature/tests | TICKET-004 | gpt-5.1 | 48104 |
|                                                                                  |
| RECENT EVENTS: timestamp | worktree | ticket | event | model | duration          |
| 3/05 23:41:11 | readme | TICKET-002 | started | gpt-5.3 | n/a                    |
| 3/05 23:40:35 | tests  | TICKET-004 | completed | gpt-5.1 | 45.2s                |
+----------------------------------------------------------------------------------+
```

## Comparison With CAR

`cmcs` is intentionally narrower in scope for this workflow.

| Metric | CAR | cmcs target |
|---|---:|---:|
| LOC | ~127,000 | ~2,000-2,500 |
| CLI commands | 131 | 12 |
| Config lines | 426 | ~10 |
| Codex invocation depth | 8 layers | 1 layer (direct subprocess) |
