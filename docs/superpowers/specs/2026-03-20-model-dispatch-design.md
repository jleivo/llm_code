# Model Dispatch Skill Design

## Problem

Claude Code's Agent tool only accepts `sonnet`, `opus`, and `haiku` as model values. There is no way to dispatch tasks to local/non-Anthropic models (e.g., qwen3-coder-next:128k via Ollama) from within a running session using the native subagent system.

However, pre-defined agent files in `~/.claude/agents/` with arbitrary `model:` values in frontmatter **do work** (verified). This skill leverages that capability.

## Overview

The `model-dispatch` skill enables dispatching tasks to any model from within a Claude Code session. It combines:

1. **Persistent model roster** — pre-defined agent files for frequently used local models
2. **Ad-hoc CLI dispatch** — `claude -p --model` via Bash for one-off tasks to any model
3. **Optional periodic monitoring** — CronCreate-based progress checks on running tasks

## Components

### 1. Persistent Model Roster

Agent files in `~/.claude/agents/` for core models. Each follows a standard template.

**Initial roster:**

| Short name       | Model ID                    | Agent file                          |
|------------------|-----------------------------|-------------------------------------|
| qwen3-coder     | qwen3-coder-next:128k      | ~/.claude/agents/qwen3-coder.md    |
| glm-flash       | glm-4.7-flash-64k:latest   | ~/.claude/agents/glm-flash.md      |
| qwen3-80b       | qwen3-next-80b:128k        | ~/.claude/agents/qwen3-80b.md      |
| nemotron-super   | nemotron-3-super:cloud      | ~/.claude/agents/nemotron-super.md |

**Agent file template:**

```yaml
---
name: <short-name>
description: General-purpose subagent running on <model-id>. Use when asked to dispatch work to <model-id> or <short-name>.
model: <full-model-id>
---

You are a subagent running on <model-id>. Complete the requested task thoroughly.
Report what you did and any issues encountered.
```

**Usage:** Once loaded (at session start), these are available via:
- Natural language: "use qwen3-coder to review this file"
- @-mention: `@agent-qwen3-coder review the auth module`
- Skill-mediated: "dispatch this task to qwen3-coder"

Roster models support full native subagent features: foreground/background execution, resume, UI indicators, context isolation.

### 2. Ad-hoc CLI Dispatch

For models not in the roster, dispatch via Bash:

```bash
claude -p "<task prompt>" --model <model-id> --output-format stream-json
```

**Execution model:**
- Runs via Bash tool with `run_in_background: true`
- Working directory is inherited (access to same codebase)
- Full tool access by default
- Output checked via `TaskOutput` (auto-notified on completion)

**Workflow:**
1. User requests dispatch to a model not in roster
2. Skill asks: add to roster (persistent) or one-off CLI dispatch?
3. If roster: creates agent file via `manage-roster.sh`, informs user to restart session
4. If one-off: constructs `claude -p` command, runs in background

### 3. Roster Management Script

`~/.claude/skills/model-dispatch/scripts/manage-roster.sh`

**Operations:**
- `add <short-name> <full-model-id>` — creates agent file from template in `~/.claude/agents/`
- `remove <short-name>` — deletes the agent file
- `list` — shows current roster (agent files with their model IDs)

**Template source:** `~/.claude/skills/model-dispatch/references/agent-template.md`

The script reads the template, substitutes `<short-name>` and `<full-model-id>`, and writes to `~/.claude/agents/<short-name>.md`.

### 4. Optional Periodic Monitoring

**Default behavior:** Completion notification only (built-in for both native subagents and Bash background tasks).

**Opt-in periodic monitoring:** When the user requests it (e.g., "dispatch this to qwen3 and check every 5 minutes"), the skill:

1. Dispatches the task (via Agent tool or Bash background)
2. Creates a CronCreate job at the requested interval
3. Each cron tick calls `TaskOutput` with `block: false` on the background task ID
4. Reports brief status: running / completed / failed
5. Auto-deletes the cron job via `CronDelete` once the task completes

**Trigger phrases:** "check every N minutes", "monitor progress", "keep me updated"

## Skill File Structure

```
~/.claude/skills/model-dispatch/
├── SKILL.md                           # Skill definition, trigger logic, dispatch flow
├── scripts/
│   └── manage-roster.sh              # Add/remove/list roster models
└── references/
    └── agent-template.md             # Template for agent .md files
```

## Skill Trigger

The skill triggers when:
- User asks to dispatch/delegate/run a task on a specific model
- User mentions a model name in context of task delegation
- User asks to add/remove models from the roster
- User invokes `/model-dispatch`

**Description (for triggering):** "Dispatch tasks to local or non-Anthropic models. Use when delegating work to specific models like qwen3, glm, nemotron, or any model not available through the native Agent tool model selector."

## Dispatch Decision Flow

```
User requests task on model X
    │
    ├── Is X in roster? (agent file exists in ~/.claude/agents/)
    │   ├── YES → Use Agent tool with subagent_type: <short-name>
    │   │         Run in background by default
    │   │         If periodic monitoring requested → CronCreate
    │   │
    │   └── NO → Ask: add to roster or one-off?
    │       ├── ADD TO ROSTER → Run manage-roster.sh add
    │       │                   Inform: restart session to use natively
    │       │                   Offer: one-off CLI dispatch now?
    │       │
    │       └── ONE-OFF → Run claude -p via Bash background
    │                     If periodic monitoring requested → CronCreate
    │
    └── Output returned via completion notification (default)
        or periodic CronCreate checks (if requested)
```

## Out of Scope

- **Model selection intelligence** — user picks the model, skill doesn't recommend
- **Output post-processing** — results returned as-is from the subagent/CLI
- **Task queuing or orchestration** — single task dispatch only (jules-executor handles multi-task)
- **Persistent task history** — no logging beyond the session
- **Model-specific tool restrictions** — all models get full toolset

## Dependencies

- Claude Code custom subagents feature (agent files in `~/.claude/agents/`)
- `claude` CLI available in PATH
- CronCreate/CronDelete tools (for optional periodic monitoring)
- Bash tool (for ad-hoc dispatch and roster management)
