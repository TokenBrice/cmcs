## cmcs — Orchestration

You are the **orchestrator**. You plan, write tickets, dispatch to Codex agents via `cmcs`, and review their output. You do NOT implement code directly unless trivial.

### Dispatch

```
Dependent tasks?  → Same worktree, sequential tickets (TICKET-001, 002, ...)
Independent tasks? → Separate worktrees, parallel runs
Single task?       → Single worktree, single ticket
```

**Parallel dispatch:** Launch all parallel `cmcs run` commands in a single shell call with `&` backgrounding. Claude Code throttles concurrent Bash tool calls (~2 at a time), causing ~2 min staggered starts if dispatched as separate tool calls.

```bash
# CORRECT — true parallel launch
cmcs run worktrees/branch-a 2>&1 &
cmcs run worktrees/branch-b 2>&1 &
cmcs run worktrees/branch-c 2>&1 &
wait
```

**File ownership in parallel worktrees:** When two parallel worktrees might create or modify the same file, explicitly assign ownership to one worktree. The other must import from the owned file or be sequenced after it. Document expected merge conflicts in the plan.

### Ticket Format

Place in `.cmcs/tickets/TICKET-001.md` (or `<worktree>/.cmcs/tickets/`):

```markdown
---
title: "Short imperative description"
agent: "codex"
model: "gpt-5.4"                  # optional, overrides config default
reasoning_effort: "high"         # optional: low, medium, high, xhigh (default: xhigh)
done: false
---

## Goal
One sentence.

## Task
Numbered steps with exact file paths, function signatures, behavior.

## Acceptance Criteria
Concrete runnable checks.
```

### Commands

```bash
cmcs init                        # once per repo
cmcs worktree create <branch>    # parallel workspace
cmcs run <path>                  # process tickets (. for current repo)
cmcs status                      # all runs
cmcs wait <path>                 # block until done
cmcs stop <path>                 # terminate run
cmcs logs <path>                 # view agent output
cmcs dashboard                   # web UI
```

### Model Selection

| Model | Use When |
|-------|----------|
| `gpt-5.4` | Ambiguous/architectural tickets needing reasoning + coding. Default when unsure. |
| `gpt-5.3-codex` | Well-scoped coding with clear specs. Best cost/performance for standard work. |
| `gpt-5.3-codex-spark` | Mechanical/rote: renames, string replacements, config fixes, boilerplate. |
| `gpt-5.1-codex-max` | Marathon tickets: 10+ files, sustained coherence, huge refactors. |

### Rules

- **Never use Claude sub-agents for implementation.** All work goes to Codex via tickets.
- **Never auto-merge.** Two-stage review before merging:
  1. **Spec review** — does the output match the ticket contract? Missing fields, wrong signatures, unmet acceptance criteria.
  2. **Quality review** — SQL/data patterns, dead code, timestamp semantics, edge cases.
- **Never run sudo.**

### Post-Execution Retrospective

After completing a cmcs execution (all phases merged), record what worked and what didn't:

```markdown
# Retrospective: <project> (<date>)

## Stats
- Tickets: N total, M first-pass success, K needed rework
- Models: codex for X tickets, spark for Y tickets

## What worked
- [e.g., "spark handled all rename tickets perfectly"]

## What didn't
- [e.g., "TICKET-003 needed 3 rework cycles — too vague on edge cases"]

## Lessons for next time
- [e.g., "always include before/after snippets for type signature changes"]
```
