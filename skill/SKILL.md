---
name: cmcs-driven-development
description: Use when executing implementation plans via cmcs/Codex agents with structured review checkpoints
---

# cmcs-Driven Development

Execute plan by writing cmcs tickets for Codex agents, with two-stage Claude review after each: spec compliance review first, then code quality review.

**Core principle:** Codex implements via tickets + Claude reviews (spec then quality) = high quality, orchestrator never implements

## When to Use

```dot
digraph when_to_use {
    "Have implementation plan?" [shape=diamond];
    "Using cmcs/Codex?" [shape=diamond];
    "cmcs-driven-development" [shape=box];
    "subagent-driven-development" [shape=box];
    "Write plan first (superpowers:writing-plans)" [shape=box];

    "Have implementation plan?" -> "Using cmcs/Codex?" [label="yes"];
    "Have implementation plan?" -> "Write plan first (superpowers:writing-plans)" [label="no"];
    "Using cmcs/Codex?" -> "cmcs-driven-development" [label="yes"];
    "Using cmcs/Codex?" -> "subagent-driven-development" [label="no - use Claude subagents"];
}
```

**vs. Subagent-Driven Development:**
- Codex agents implement (not Claude subagents)
- Tickets must be fully self-contained (Codex can't ask questions)
- Async execution via `cmcs run` + `cmcs wait`
- Model selection matters (gpt-5.3-codex vs spark)
- Claude subagents still handle review (spec + quality)

**For large projects (10+ files, multi-phase):** Read the [large implementation preparation guide](../docs/cmcs-large-implementation-preparation.md) first — it covers research, design docs, phased execution, and handover documents.

## The Process

```dot
digraph process {
    rankdir=TB;

    subgraph cluster_per_task {
        label="Per Task";
        "Write ticket (./ticket-template.md)" [shape=box];
        "cmcs run + cmcs wait" [shape=box];
        "cmcs succeeded?" [shape=diamond];
        "Read cmcs logs, diagnose failure" [shape=box];
        "Fix ticket and re-run" [shape=box];
        "Run acceptance criteria yourself" [shape=box];
        "Dispatch spec reviewer subagent (./spec-reviewer-prompt.md)" [shape=box];
        "Spec reviewer confirms code matches spec?" [shape=diamond];
        "Write fix ticket and re-run cmcs" [shape=box];
        "Dispatch code quality reviewer subagent (./code-quality-reviewer-prompt.md)" [shape=box];
        "Code quality reviewer approves?" [shape=diamond];
        "Write quality-fix ticket and re-run cmcs" [shape=box];
        "Mark task complete in TodoWrite" [shape=box];
    }

    "Read plan, extract all tasks with full text, note context, create TodoWrite" [shape=box];
    "Create worktree: cmcs worktree create branch-name" [shape=box];
    "More tasks remain?" [shape=diamond];
    "Dispatch final code reviewer subagent for entire implementation" [shape=box];
    "Merge worktree to main" [shape=box];

    "Read plan, extract all tasks with full text, note context, create TodoWrite" -> "Create worktree: cmcs worktree create branch-name";
    "Create worktree: cmcs worktree create branch-name" -> "Write ticket (./ticket-template.md)";
    "Write ticket (./ticket-template.md)" -> "cmcs run + cmcs wait";
    "cmcs run + cmcs wait" -> "cmcs succeeded?";
    "cmcs succeeded?" -> "Run acceptance criteria yourself" [label="yes"];
    "cmcs succeeded?" -> "Read cmcs logs, diagnose failure" [label="no"];
    "Read cmcs logs, diagnose failure" -> "Fix ticket and re-run" ;
    "Fix ticket and re-run" -> "cmcs run + cmcs wait";
    "Run acceptance criteria yourself" -> "Dispatch spec reviewer subagent (./spec-reviewer-prompt.md)";
    "Dispatch spec reviewer subagent (./spec-reviewer-prompt.md)" -> "Spec reviewer confirms code matches spec?";
    "Spec reviewer confirms code matches spec?" -> "Write fix ticket and re-run cmcs" [label="no"];
    "Write fix ticket and re-run cmcs" -> "cmcs run + cmcs wait" [label="re-run"];
    "Spec reviewer confirms code matches spec?" -> "Dispatch code quality reviewer subagent (./code-quality-reviewer-prompt.md)" [label="yes"];
    "Dispatch code quality reviewer subagent (./code-quality-reviewer-prompt.md)" -> "Code quality reviewer approves?";
    "Code quality reviewer approves?" -> "Write quality-fix ticket and re-run cmcs" [label="no"];
    "Write quality-fix ticket and re-run cmcs" -> "cmcs run + cmcs wait" [label="re-run"];
    "Code quality reviewer approves?" -> "Mark task complete in TodoWrite" [label="yes"];
    "Mark task complete in TodoWrite" -> "More tasks remain?";
    "More tasks remain?" -> "Write ticket (./ticket-template.md)" [label="yes"];
    "More tasks remain?" -> "Dispatch final code reviewer subagent for entire implementation" [label="no"];
    "Dispatch final code reviewer subagent for entire implementation" -> "Merge worktree to main";
}
```

## Ticket Writing

See `./ticket-template.md` for the full template.

**Critical:** Tickets must be completely self-contained. Codex agents cannot ask questions, read the plan file, or access files outside their worktree. Everything they need must be in the ticket itself.

**Model selection:**

| Model | Use When |
|-------|----------|
| `gpt-5.3-codex` | Complex multi-file refactors, architectural changes, new test suites |
| `gpt-5.3-codex-spark` | Repetitive pattern application, medium complexity, well-defined changes |
| `gpt-5.3-codex-spark` | Mechanical/rote changes, string replacements, config fixes |

When unsure, use `gpt-5.3-codex` — over-provisioning wastes tokens but under-provisioning produces bad output.

## Prompt Templates

- `./ticket-template.md` - Write cmcs tickets for Codex agents
- `./spec-reviewer-prompt.md` - Dispatch spec compliance reviewer (Claude subagent)
- `./code-quality-reviewer-prompt.md` - Dispatch code quality reviewer (Claude subagent)

## Worktree Strategy

```
Dependent tasks?   -> Same worktree, sequential tickets (TICKET-001, 002, ...)
Independent tasks? -> Separate worktrees, parallel cmcs runs
Single task?       -> Single worktree, single ticket
```

**Parallel worktrees** within a task group must touch non-overlapping files.

**Parallel dispatch:** Always launch parallel `cmcs run` commands in a single Bash call with `&` backgrounding. Claude Code throttles concurrent Bash tool calls (~2 at a time), so separate tool calls cause ~2 min staggered starts.

```bash
# All agents launch simultaneously
cmcs run worktrees/branch-a 2>&1 &
cmcs run worktrees/branch-b 2>&1 &
cmcs run worktrees/branch-c 2>&1 &
wait
```

## Example Workflow

```
You: I'm using cmcs-Driven Development to execute this plan.

[Read plan file once]
[Extract all 5 tasks with full text and context]
[Create TodoWrite with all tasks]
[Create worktree: cmcs worktree create feat/new-feature]

Task 1: Add data model

[Write TICKET-001.md with full task text, context, acceptance criteria]
[Copy ticket to worktree: cp to worktrees/feat/new-feature/.cmcs/tickets/]
[cmcs run worktrees/feat/new-feature]
[cmcs wait worktrees/feat/new-feature]

cmcs: Completed (1/1 tickets passed)

[Run acceptance criteria: build + test — all pass]

[Dispatch spec compliance reviewer (Claude subagent)]
Spec reviewer: APPROVED — all requirements met, nothing extra

[Get git SHAs, dispatch code quality reviewer (Claude subagent)]
Code reviewer: Strengths: Good. Issues: None. Approved.

[Mark Task 1 complete]

Task 2: Refactor API handler

[Write TICKET-002.md with full context]
[Copy to worktree, cmcs run, cmcs wait]

cmcs: Completed (1/1 tickets passed)

[Run acceptance criteria — all pass]

[Dispatch spec compliance reviewer]
Spec reviewer: ISSUES:
  - Missing: Fallback error handler (spec requirement)
  - Extra: Added logging middleware (not requested)

[Write TICKET-002-fix.md: "Add error fallback, remove logging middleware"]
[cmcs run, cmcs wait]

[Dispatch spec reviewer again]
Spec reviewer: APPROVED

[Dispatch code quality reviewer]
Code reviewer: Strengths: Solid. Issues (Important): Magic timeout value

[Write TICKET-002-quality.md: "Extract TIMEOUT constant"]
[cmcs run, cmcs wait]

[Dispatch code quality reviewer again]
Code reviewer: APPROVED

[Mark Task 2 complete]

...

[After all tasks]
[Dispatch final code reviewer for entire worktree diff]
Final reviewer: All requirements met, ready to merge

[Merge worktree to main]
Done!
```

## Advantages

**vs. Subagent-Driven Development:**
- Codex handles heavy implementation (cost-efficient)
- Tickets create audit trail of exactly what was requested
- Model selection optimizes cost/quality per task
- Parallel worktrees for independent tasks (true parallelism)

**vs. Raw cmcs (no structured review):**
- Two-stage review catches spec drift and quality issues
- Review loops ensure fixes actually work
- Spec compliance prevents over/under-building by Codex
- Code quality ensures maintainable output

**Quality gates:**
- Acceptance criteria run by orchestrator (not trusted from Codex)
- Spec compliance review by Claude subagent (independent verification)
- Code quality review by Claude subagent (catches what Codex misses)
- Review loops ensure fixes are verified
- Final review catches cross-task integration issues

## Red Flags

**Never:**
- Implement code directly as orchestrator (all work goes through Codex tickets)
- Use Claude subagents for implementation (cmcs rule)
- Auto-merge Codex output without review
- Skip reviews (spec compliance OR code quality)
- Proceed with unfixed issues
- Trust Codex's self-reported success (run acceptance criteria yourself)
- Write tickets that say "update all files that use X" (list every file explicitly)
- Let Codex access files outside its worktree (copy artifacts in)
- Skip the re-review after a fix ticket
- **Start code quality review before spec compliance is APPROVED** (wrong order)
- Move to next task while either review has open issues
- Run `sudo` in any context

**If cmcs run fails:**
1. Read logs: `cmcs logs <path>`
2. Diagnose: ticket too vague? wrong model? codebase issue?
3. Fix the ticket (more context, clearer steps, correct paths)
4. Re-run — don't try to fix the code manually

**If reviewer finds issues:**
1. Write a targeted fix ticket describing exactly what to change
2. Run cmcs again in the same worktree
3. Reviewer reviews again
4. Repeat until approved

**Trivial fixes only:** If a review issue is a one-line change (rename a constant, fix a typo), the orchestrator MAY fix it directly rather than writing a ticket. Use judgment — if there's any complexity, write a ticket.

## Integration

**Required process docs:**
- **[Orchestration Guide](../docs/orchestration-guide.md)** — dispatch patterns, ticket writing, review checklist
- **[Large Implementation Preparation](../docs/cmcs-large-implementation-preparation.md)** — for large projects (10+ files)

**Required workflow skills:**
- **superpowers:writing-plans** — Creates the plan this skill executes
- **superpowers:requesting-code-review** — Code review template for reviewer subagents
- **superpowers:verification-before-completion** — Verify before claiming done

**Review subagents use:**
- **superpowers:requesting-code-review** — Code quality review template

**Alternative workflow:**
- **superpowers:subagent-driven-development** — Use Claude subagents instead of Codex for implementation
