# Ticket Template for cmcs-Driven Development

Use this template when writing cmcs tickets for Codex agents.

**Critical:** Tickets must be completely self-contained. Codex agents cannot:
- Ask clarifying questions
- Read the plan file or design docs
- Access files outside their worktree
- Infer intent from context

Everything the agent needs must be **in the ticket itself**.

## Template

```markdown
---
title: "Short imperative description"
agent: "codex"
model: "gpt-5.4"                  # see model guide below
reasoning_effort: "high"          # low, medium, high, xhigh (default: xhigh)
done: false
---

## Goal

One sentence describing the concrete outcome.

## Context

[WHY this change is needed. What system/feature it's part of. How it fits with
other changes. Include any architectural context the agent needs.]

## Task

1. **`path/to/file.ext`** (line ~N, `FunctionOrBlock`):
   - Exact description of the change
   - Before/after code snippets when the change is non-obvious:
     ```
     // Before
     const old = doThing();
     // After
     const new = doOtherThing();
     ```

2. **`path/to/other-file.ext`** (line ~M):
   - ...

## Acceptance Criteria

- `<your-build-command>` exits 0
- `<your-test-command>` exits 0
- `grep -c 'expectedPattern' path/to/file.ext` returns N
- [Specific behavioral checks relevant to this ticket]
```

## Validation

After writing tickets, validate them before dispatching:

```bash
cmcs ticket validate <worktree-path>
```

This checks for:
- Missing or empty `title` fields
- Empty `model` strings
- Spark model assigned to tickets referencing 8+ files (likely to hit output-token limits)
- Malformed YAML frontmatter

## Model & Reasoning Effort Guide

See the [Model Selection Guide](../docs/model-selection.md) for model catalog, selection heuristics, reasoning effort levels, and known failure modes.

## Ticket Writing Principles

1. **Exact file paths and line numbers.** Codex works from the worktree root — it needs precise locations.
2. **Code snippets for non-obvious changes.** Show the before/after pattern, not just "update the function."
3. **Acceptance criteria are runnable commands.** `grep`, `wc -l`, build commands — things that return pass/fail.
4. **Always include build + test** in acceptance criteria, even for small tickets.
5. **Reference data artifacts inline.** If a ticket needs a mapping table, tell Codex exactly where to find it — and make sure the file is copied into the worktree.
6. **One logical change per ticket.** If a ticket does two independent things, split it. Codex performs best on narrowly focused tasks.
7. **List every file explicitly.** Never say "update all files that use X" — enumerate them with paths and line numbers.
8. **Validate before dispatching.** Run `cmcs ticket validate` after writing tickets to catch formatting issues and model/scope mismatches early.

## Fix Tickets

When a reviewer finds issues, write a targeted fix ticket:

```markdown
---
title: "Fix: [what needs fixing]"
agent: "codex"
model: "gpt-5.3-codex-spark"
reasoning_effort: "medium"
done: false
---

## Goal

Fix [specific issue] identified during review.

## Context

The previous ticket (TICKET-NNN) implemented [feature]. Review found:
- [Issue 1: file:line — what's wrong and what it should be]
- [Issue 2: ...]

## Task

1. **`path/to/file.ext`** (line ~N):
   - [Exact fix]

## Acceptance Criteria

- `<your-build-command>` exits 0
- `<your-test-command>` exits 0
- [Specific check that the fix is correct]
- [Specific check that the original issue is gone]
```

Fix tickets should use lighter models/effort since the problem is already well-defined.

## Human Tickets

Use `agent: "human"` for manual steps that cmcs should skip but that belong in the ticket sequence for documentation:

```markdown
---
title: "Run database migration"
agent: "human"
done: false
---

## Runbook

1. Connect to production database
2. Run `ALTER TABLE ...`
3. Verify with `SELECT COUNT(*) FROM ...`
4. Set `done: true` when complete
```

cmcs skips any ticket where `agent` is not `"codex"`. These `human` tickets serve as documented checkpoints in a sequential ticket chain.

## Sequential Ticket Context

When running sequential tickets in a worktree (TICKET-001, TICKET-002, ...), cmcs automatically passes the `## Progress` section from the previous completed ticket to the next agent. This means:

- The next agent knows what the previous agent did
- You don't need to repeat context that was already established
- Carry forward the prior ticket's `## Progress` details instead of restating completed work
- Design your sequential tickets to build on each other, knowing the agent will receive prior progress
- The first ticket in a sequence gets no prior context — make it fully self-contained
