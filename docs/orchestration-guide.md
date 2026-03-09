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
model: "gpt-5.4"         # optional per-ticket override
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
model: "gpt-5.3-codex-spark"
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
7. **Self-contained smoke tests.** Any smoke test commands in tickets or execution handovers must include required auth tokens or use public endpoints. Don't assume the reviewer has env vars set.

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

**File ownership:** When two parallel worktrees might create or modify the same file, explicitly assign ownership to one worktree. The other must import from the owned file or be sequenced after it. Document expected merge conflicts in the plan. Common culprits: shared types files, constants, documentation.

**Step 2: Write tickets in each worktree queue**
```bash
worktrees/feature-a/.cmcs/tickets/TICKET-001.md
worktrees/feature-b/.cmcs/tickets/TICKET-001.md
```

**Step 3: Launch runs**

Launch all parallel runs in a single shell call with `&` backgrounding. Claude Code throttles concurrent Bash tool calls (~2 at a time), so separate tool calls cause ~2 min staggered starts.

```bash
# All agents launch simultaneously
cmcs run worktrees/feature-a 2>&1 &
cmcs run worktrees/feature-b 2>&1 &
wait
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

Two-stage review before accepting any Codex output. Each stage catches different classes of issues.

**Stage 1 — Spec review:**
1. Does the output match the ticket contract? Missing fields, wrong signatures, unmet acceptance criteria.
2. Run acceptance criteria commands independently.

**Stage 2 — Quality review:**
1. Read every file Codex created or modified.
2. Check for:
   - Correct file locations
   - Clean code (no dead code, no unnecessary complexity)
   - Security issues (no hardcoded secrets, no command injection)
   - Import correctness (proper module paths, no broken imports)
   - Test quality (tests assert meaningful behavior)
   - SQL/data patterns (N+1 queries, INSERT OR REPLACE vs ON CONFLICT, timestamp semantics)

**Then:**
- **If issues found:** update the ticket with clearer instructions and re-run.
- **If clean:** commit the work and proceed.

## Post-Merge Checklist

After merging each phase:

1. Install dependencies if the package manifest changed (e.g. `npm install`, `pip install -e .`)
2. Run full build / type-check
3. Run tests
4. Check for duplicate exports/constants from parallel worktree merges
5. Delete the worktree only after confirming all commits are reachable on the target branch

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

## Post-Execution Retrospective

After completing a cmcs execution (all phases merged), record what worked and what didn't. This prevents repeating the same mistakes across projects.

```markdown
# Retrospective: <project> (<date>)

## Stats
- Tickets: N total, M first-pass success, K needed rework
- Models: codex for X tickets, spark for Y tickets

## What worked
- [e.g., "spark handled all rename tickets perfectly"]
- [e.g., "parallel worktrees for frontend/worker saved 30 min"]

## What didn't
- [e.g., "TICKET-003 needed 3 rework cycles — too vague on edge cases"]
- [e.g., "spark couldn't handle cross-file type propagation — should have used codex"]

## Lessons for next time
- [e.g., "always include before/after snippets for type signature changes"]
- [e.g., "split tickets touching >5 files — Codex quality degrades past that"]
```

**When to write:** After merging the final phase, before cleaning up worktrees. The context is freshest right after execution.
