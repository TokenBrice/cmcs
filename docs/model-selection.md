# Model Selection Guide

## Model Catalog

| Model | Strengths | Limits | Cost |
|---|---|---|---|
| `gpt-5.4` | Strong reasoning + coding, best for ambiguous/architectural work | Slower, higher cost | $$$$ |
| `gpt-5.3-codex` | Well-scoped coding with clear specs; default for standard tickets | Context window cannot hold very large codebases (>50K LOC) | $$ |
| `gpt-5.3-codex-spark` | Fast mechanical work: renames, string replacements, config, boilerplate | Hits max_output_tokens on 10+ files or ~500 LOC of changes | $ |
| `gpt-5.1-codex-max` | Marathon tickets: 10+ files, huge refactors, full-codebase research | Slower, highest cost | $$$$$ |

## Selection Heuristics

1. **Default:** `gpt-5.3-codex` -- use for any standard, well-scoped ticket.
2. **When unsure:** `gpt-5.4` -- if the task is ambiguous or requires architectural judgment.
3. **Mechanical work (<10 files):** `gpt-5.3-codex-spark` -- renames, config edits, boilerplate generation.
4. **10+ files or full-codebase scope:** `gpt-5.1-codex-max` -- never use spark for large-scope work.
5. **Research tickets scanning entire src/:** `gpt-5.1-codex-max` -- needs the extended context and output capacity.

## Reasoning Effort

| Level | Use When |
|---|---|
| `low` | Trivial edits: typo fixes, single-line config changes |
| `medium` | Straightforward implementation with clear specs and examples |
| `high` | Multi-step tasks requiring careful logic, test writing, moderate refactors |
| `xhigh` | Complex architectural decisions, subtle bug investigation, large refactors |

## Resolution Order

Model and reasoning effort settings are resolved in the following order (highest priority first):

1. **Ticket frontmatter** -- the `model` field in a ticket's YAML header overrides everything.
2. **Config file** -- the `codex.model` value in `.cmcs/config.yml`.
3. **Built-in default** -- `gpt-5.3-codex` if nothing else is specified.

## Known Failure Modes

| Symptom | Cause | Fix |
|---|---|---|
| Context length exceeded / truncated input | Codebase too large for the model's context window | Use `gpt-5.1-codex-max` or set `fallback_model` in config |
| Output cut off mid-file / incomplete changes | Hitting max_output_tokens limit | Use `gpt-5.3-codex` instead of spark; reduce ticket scope |
| Partial changes across files / some files untouched | Ticket scope too broad for the model's output capacity | Split into smaller tickets or upgrade to `gpt-5.1-codex-max` |
