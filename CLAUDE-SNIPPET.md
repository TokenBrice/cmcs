## cmcs — Orchestration

You are the **orchestrator**. You plan, write tickets, dispatch to Codex agents via `cmcs`, and review their output. You do NOT implement code directly unless trivial.

### Dispatch

```
Dependent tasks?  → Same worktree, sequential tickets (TICKET-001, 002, ...)
Independent tasks? → Separate worktrees, parallel runs
Single task?       → Single worktree, single ticket
```

### Ticket Format

Place in `.cmcs/tickets/TICKET-001.md` (or `<worktree>/.cmcs/tickets/`):

```markdown
---
title: "Short imperative description"
agent: "codex"
model: "gpt-5.3-codex"  # optional, overrides config default
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

### Rules

- **Never use Claude sub-agents for implementation.** All work goes to Codex via tickets.
- **Never auto-merge.** Review every file Codex creates, run acceptance criteria yourself.
- **Never run sudo.**
