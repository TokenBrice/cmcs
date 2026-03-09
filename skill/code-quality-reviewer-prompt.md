# Code Quality Reviewer Prompt Template

Use this template when dispatching a Claude subagent to review Codex agent output for code quality.

**Purpose:** Verify implementation is well-built (clean, tested, maintainable)

**Only dispatch after spec compliance review passes.**

```
Agent tool (superpowers:code-reviewer):
  Use template at requesting-code-review/code-reviewer.md

  WHAT_WAS_IMPLEMENTED: [summary of what Codex built — from ticket + code inspection]
  PLAN_OR_REQUIREMENTS: Task N from [plan-file]
  BASE_SHA: [commit before cmcs run]
  HEAD_SHA: [current commit after cmcs run]
  DESCRIPTION: [task summary]
```

**Note on auto-commit:** Since cmcs v0.3.0, worktree changes are auto-committed after successful tickets (when `codex.auto_commit` is enabled, which is the default). The `HEAD_SHA` will be the auto-commit SHA. Use `git diff BASE_SHA..HEAD_SHA` to see exactly what changed. If auto-commit is disabled, review uncommitted changes directly.

**Code reviewer returns:** Strengths, Issues (Critical/Important/Minor), Assessment

**Additional context for reviewer:** Note that the implementation was done by a Codex agent via cmcs ticket. Common Codex patterns to watch for:
- Overly verbose or boilerplate-heavy code
- Missing edge cases that weren't explicitly in the ticket
- Inconsistency with existing codebase patterns/conventions
- Hardcoded values that should be constants
- Test quality (testing behavior vs testing implementation details)
- Check `cmcs logs <worktree-path>` for agent stdout/stderr — may reveal runtime warnings or failed attempts
