# Orchestration Guide

## The Autonomous Loop

```
User request
    │
    ▼
Decompose into tasks
    │
    ├── Independent tasks? ──► Parallel dispatch (worktrees)
    │                              │
    └── Dependent tasks? ────► Sequential dispatch (ticket queue)
                                   │
                                   ▼
                          Write tickets ──► cmcs run
                                                │
                                                ▼
                                    Monitor until complete
                                                │
                                                ▼
                                    Review each output
                                         │
                              ┌──────────┴──────────┐
                              ▼                      ▼
                         Accept                  Reject
                              │                      │
                         Commit work            Rewrite ticket
                              │                      │
                              ▼                      ▼
                    Next tasks or done        Re-dispatch to Codex
```

## Writing Tickets

Tickets live in `.cmcs/tickets/` and are processed in filename order (`TICKET-001.md`, `TICKET-002.md`, ...).

Every ticket follows this structure:

```markdown
---
title: "Short imperative description"
agent: "codex"
model: "gpt-5.3-codex"   # optional per-ticket override
done: false
---

## Goal
One sentence: what this achieves and why it matters.

## Task
Numbered steps. Be specific about:
- File paths to create or modify
- Function signatures and return types
- Exact behavior expected

## Acceptance Criteria
Concrete, runnable checks:
- `python3 some_script.py` produces X
- `python3 -m pytest tests/test_foo.py` passes
- `command` exits 0 with expected output
```

### Full Ticket Example

Here's a complete ticket showing all fields and sections in use:

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

### Ticket Writing Principles

1. **One concern per ticket.** A ticket should produce a reviewable unit of work.
2. **Specify file paths.** Codex performs better with explicit file targets.
3. **Include function signatures.** Type hints and return types reduce ambiguity.
4. **Runnable acceptance criteria.** Every ticket should include at least one objective verification command.
5. **No implicit dependencies.** Keep dependent tasks sequential or explicitly reference required prior files.
6. **Use `model:` only when needed.** Omit it to inherit default `codex.model` from config.

## Sequential Dispatch

Use when tasks depend on each other.

```
.cmcs/tickets/
├── TICKET-001.md   ← "Create data model"
├── TICKET-002.md   ← "Add API endpoints using data model"
└── TICKET-003.md   ← "Add tests for API endpoints"
```

**Commands (from repo root):**
```bash
# Initialize once per repo
cmcs init

# Run the local ticket queue (.cmcs/tickets)
cmcs run .

# Optional monitoring commands (useful from a second terminal)
cmcs status .
cmcs logs .
cmcs stop .
```

Notes:
- `cmcs run` is the execution command for ticket processing.
- `cmcs stop <path>` is for interrupting an active run.

## Parallel Dispatch

Use when tasks are independent.

**Step 1: Create worktrees**
```bash
cmcs worktree create feature-a
cmcs worktree create feature-b
```

By default, worktrees are created under `worktrees/<branch>/`.

**Step 2: Write tickets in each worktree queue**
```bash
worktrees/feature-a/.cmcs/tickets/TICKET-001.md
worktrees/feature-b/.cmcs/tickets/TICKET-001.md
```

**Step 3: Launch runs (typically in separate terminals or background jobs)**
```bash
cmcs run worktrees/feature-a
cmcs run worktrees/feature-b
```

**Step 4: Monitor completion**
```bash
cmcs status
cmcs wait worktrees/feature-a
cmcs wait worktrees/feature-b
```

**Step 5: Review logs, then merge**
```bash
cmcs logs worktrees/feature-a
cmcs logs worktrees/feature-b
```

After review, merge the worktree branches back to `master`.

## Dashboard Monitoring

For visual status across runs, start the local dashboard:

```bash
cmcs dashboard
```

Default URL is `http://127.0.0.1:4173` unless overridden in `.cmcs/config.yml`.

## Review Checklist

After every Codex ticket completion, before accepting:

1. **Read every file** Codex created or modified.
2. **Run acceptance criteria** commands independently.
3. **Check for:**
   - Correct file locations
   - Clean code (no dead code, no unnecessary complexity)
   - Security issues (no hardcoded secrets, no command injection)
   - Import correctness (proper module paths, no broken imports)
   - Test quality (tests assert meaningful behavior)
4. **If issues found:** update the ticket with clearer instructions and re-run.
5. **If clean:** commit the work and proceed.

## Hybrid Pattern

For complex projects, combine both approaches:

```
worktree-a (sequential):          worktree-b (sequential):
  TICKET-001: data model            TICKET-001: config parser
  TICKET-002: data validation        TICKET-002: config tests
  TICKET-003: data tests

Both worktrees run in parallel, each processing its own
sequential ticket chain.
```

## Codex Behavior Notes

Observed behavior in the cmcs workflow:

- Codex sets `done: true` in frontmatter to mark completion.
- Codex appends a `## Progress` section to summarize changes.
- Per-ticket stdout/stderr artifacts are written under `.cmcs/logs/<run-id>/`.
- `cmcs status` summarizes run state without requiring run IDs.
- `cmcs wait <path>` removes the need for manual `sleep` polling loops.
