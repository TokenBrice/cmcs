# Configuration

## Config File

Config file path: `.cmcs/config.yml`

Missing keys fall back to defaults, and nested sections are merged recursively.

## Full Config Example

```yaml
codex:
  model: gpt-5.3-codex
  auto_commit: true
  fallback_model: gpt-5.1-codex-max
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

## Default Values

| Key | Default |
|---|---|
| `codex.model` | `gpt-5.3-codex` |
| `codex.args` | `["--yolo", "exec", "--sandbox", "danger-full-access", "-c", "reasoning_effort=xhigh"]` |
| `codex.timeout_s` | `1800` |
| `codex.auto_commit` | `true` |
| `codex.fallback_model` | `null` (disabled) |
| `worktrees.root` | `worktrees` |
| `worktrees.start_point` | `master` |
| `dashboard.port` | `4173` |
| `tickets.dir` | `.cmcs/tickets` |

## Minimal Config Example

```yaml
codex:
  model: gpt-5.3-codex
```

## Ticket Frontmatter Fields

| Field | Required | Type | Meaning |
|---|---|---|---|
| `title` | optional (recommended) | string | Short ticket summary. |
| `agent` | no | string | Worker name. Defaults to `"codex"` when omitted. |
| `model` | no | string | Per-ticket model override (takes precedence over config default). |
| `reasoning_effort` | no | string | Per-ticket reasoning effort (`low`, `medium`, `high`, `xhigh`). Passed through to `codex` as a `reasoning_effort` command arg without validation. |
| `done` | optional | bool | Completion flag. Parser defaults to `false`; flow picks first ticket where `done != true`. |

## Resolution Order

**Model:** ticket `model:` field, then `codex.model` in config.

**Reasoning effort:** ticket `reasoning_effort:` field, then `codex.args` in config (default: `xhigh`).

## Model Selection

See the [Model Selection Guide](model-selection.md) for model catalog, selection heuristics, and reasoning effort levels.
