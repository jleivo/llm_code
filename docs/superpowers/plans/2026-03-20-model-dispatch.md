# Model Dispatch Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code skill that enables dispatching tasks to local/non-Anthropic models via persistent agent files and CLI fallback.

**Architecture:** Persistent agent files in `~/.claude/agents/` provide native subagent integration for roster models. A bash script manages the roster (add/remove/list). The SKILL.md contains the dispatch decision logic and monitoring instructions. Ad-hoc models use `claude -p --model` via Bash background.

**Tech Stack:** Bash (roster script), Markdown (skill definition, agent templates), Claude Code subagent system

**Spec:** `docs/superpowers/specs/2026-03-20-model-dispatch-design.md`

---

## Convention Note

Skill source files live in `~/.agents/skills/` (the canonical location for all custom skills). They are symlinked into `~/.claude/skills/` for Claude Code discovery. This matches the pattern used by existing skills (jules-executor, skill-creator, etc.). Skill files are NOT tracked in the git repo — only test files are committed.

## File Structure

```
~/.agents/skills/model-dispatch/
├── SKILL.md                          # Skill definition with dispatch logic
├── scripts/
│   └── manage-roster.sh             # Roster management (add/remove/list)
└── references/
    └── agent-template.md            # Template for agent .md files

~/.claude/agents/
├── qwen3-coder.md                   # Agent: qwen3-coder-next:128k
├── glm-flash.md                     # Agent: glm-4.7-flash-64k:latest
├── qwen3-80b.md                     # Agent: qwen3-next-80b:128k
└── nemotron-super.md                # Agent: nemotron-3-super:cloud

tests/model-dispatch/
└── test_manage_roster.bats          # Tests for manage-roster.sh
```

---

### Task 1: Create the agent template

**Files:**
- Create: `~/.agents/skills/model-dispatch/references/agent-template.md`

- [ ] **Step 1: Create skill directory structure**

```bash
mkdir -p ~/.agents/skills/model-dispatch/scripts
mkdir -p ~/.agents/skills/model-dispatch/references
```

- [ ] **Step 2: Write the agent template file**

Create `~/.agents/skills/model-dispatch/references/agent-template.md`:

```markdown
---
name: {{SHORT_NAME}}
description: General-purpose subagent running on {{MODEL_ID}}. Use when asked to dispatch work to {{MODEL_ID}} or {{SHORT_NAME}}.
model: {{MODEL_ID}}
---

You are a subagent running on {{MODEL_ID}}. Complete the requested task thoroughly.
Report what you did and any issues encountered.
```

Uses `{{PLACEHOLDER}}` syntax for clear substitution boundaries.

- [ ] **Step 3: Verify**

Template file lives outside the git repo (`~/.agents/skills/`). No git commit needed. Verify file exists:

```bash
cat ~/.agents/skills/model-dispatch/references/agent-template.md
```

---

### Task 2: Create the roster management script

**Files:**
- Create: `~/.agents/skills/model-dispatch/scripts/manage-roster.sh`

- [ ] **Step 1: Write the test file**

Create `tests/model-dispatch/test_manage_roster.bats`:

```bash
#!/usr/bin/env bats

setup() {
    export TEST_AGENTS_DIR="$(mktemp -d)"
    export AGENTS_DIR="$TEST_AGENTS_DIR"
    export SCRIPT="$HOME/.agents/skills/model-dispatch/scripts/manage-roster.sh"
}

teardown() {
    rm -rf "$TEST_AGENTS_DIR"
}

@test "list shows empty roster" {
    run bash "$SCRIPT" list
    [ "$status" -eq 0 ]
    [[ "$output" == *"No models"* ]] || [[ "$output" == *"empty"* ]]
}

@test "add creates agent file" {
    run bash "$SCRIPT" add test-model "test-model-id:latest"
    [ "$status" -eq 0 ]
    [ -f "$TEST_AGENTS_DIR/test-model.md" ]
}

@test "add substitutes short name in agent file" {
    bash "$SCRIPT" add test-model "test-model-id:latest"
    run grep "name: test-model" "$TEST_AGENTS_DIR/test-model.md"
    [ "$status" -eq 0 ]
}

@test "add substitutes model id in agent file" {
    bash "$SCRIPT" add test-model "test-model-id:latest"
    run grep "model: test-model-id:latest" "$TEST_AGENTS_DIR/test-model.md"
    [ "$status" -eq 0 ]
}

@test "add overwrites existing entry" {
    bash "$SCRIPT" add test-model "old-model:v1"
    bash "$SCRIPT" add test-model "new-model:v2"
    run grep "model: new-model:v2" "$TEST_AGENTS_DIR/test-model.md"
    [ "$status" -eq 0 ]
}

@test "add rejects invalid short name with uppercase" {
    run bash "$SCRIPT" add "BadName" "model:latest"
    [ "$status" -ne 0 ]
    [[ "$output" == *"must match"* ]] || [[ "$output" == *"invalid"* ]]
}

@test "add rejects invalid short name with spaces" {
    run bash "$SCRIPT" add "bad name" "model:latest"
    [ "$status" -ne 0 ]
}

@test "add rejects empty model id" {
    run bash "$SCRIPT" add "good-name" ""
    [ "$status" -ne 0 ]
}

@test "add rejects missing arguments" {
    run bash "$SCRIPT" add
    [ "$status" -ne 0 ]
}

@test "remove deletes agent file" {
    bash "$SCRIPT" add test-model "test-model-id:latest"
    run bash "$SCRIPT" remove test-model
    [ "$status" -eq 0 ]
    [ ! -f "$TEST_AGENTS_DIR/test-model.md" ]
}

@test "remove nonexistent model fails" {
    run bash "$SCRIPT" remove nonexistent
    [ "$status" -ne 0 ]
}

@test "list shows added models" {
    bash "$SCRIPT" add alpha "alpha-model:v1"
    bash "$SCRIPT" add beta "beta-model:v2"
    run bash "$SCRIPT" list
    [ "$status" -eq 0 ]
    [[ "$output" == *"alpha"* ]]
    [[ "$output" == *"beta"* ]]
}

@test "unknown command fails" {
    run bash "$SCRIPT" unknown
    [ "$status" -ne 0 ]
}

@test "no arguments shows usage" {
    run bash "$SCRIPT"
    [ "$status" -ne 0 ]
    [[ "$output" == *"Usage"* ]]
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/git/llm_code && bats tests/model-dispatch/test_manage_roster.bats
```

Expected: FAIL (script doesn't exist yet)

- [ ] **Step 3: Write manage-roster.sh**

Create `~/.agents/skills/model-dispatch/scripts/manage-roster.sh`:

```bash
#!/usr/bin/env bash
# 0.1.0
set -euo pipefail

AGENTS_DIR="${AGENTS_DIR:-$HOME/.claude/agents}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$SCRIPT_DIR/../references/agent-template.md"

usage() {
    echo "Usage: $(basename "$0") <command> [args]"
    echo ""
    echo "Commands:"
    echo "  add <short-name> <model-id>   Add or update a model in the roster"
    echo "  remove <short-name>           Remove a model from the roster"
    echo "  list                          List all models in the roster"
    exit 1
}

validate_short_name() {
    local name="$1"
    if [[ ! "$name" =~ ^[a-z0-9-]+$ ]]; then
        echo "Error: short-name must match [a-z0-9-]+ (got: '$name')" >&2
        exit 1
    fi
}

cmd_add() {
    if [[ $# -lt 2 ]]; then
        echo "Error: add requires <short-name> <model-id>" >&2
        exit 1
    fi
    local short_name="$1"
    local model_id="$2"

    validate_short_name "$short_name"

    if [[ -z "$model_id" ]]; then
        echo "Error: model-id must not be empty" >&2
        exit 1
    fi

    if [[ ! -f "$TEMPLATE" ]]; then
        echo "Error: template not found at $TEMPLATE" >&2
        exit 1
    fi

    mkdir -p "$AGENTS_DIR"

    sed -e "s|{{SHORT_NAME}}|${short_name}|g" \
        -e "s|{{MODEL_ID}}|${model_id}|g" \
        "$TEMPLATE" > "$AGENTS_DIR/${short_name}.md"

    echo "Added $short_name ($model_id) to roster"
}

cmd_remove() {
    if [[ $# -lt 1 ]]; then
        echo "Error: remove requires <short-name>" >&2
        exit 1
    fi
    local short_name="$1"
    local agent_file="$AGENTS_DIR/${short_name}.md"

    if [[ ! -f "$agent_file" ]]; then
        echo "Error: no agent file found for '$short_name'" >&2
        exit 1
    fi

    rm "$agent_file"
    echo "Removed $short_name from roster"
}

cmd_list() {
    if [[ ! -d "$AGENTS_DIR" ]] || ! compgen -G "$AGENTS_DIR/*.md" > /dev/null 2>&1; then
        echo "No models in roster"
        return 0
    fi

    printf "%-20s %s\n" "SHORT NAME" "MODEL ID"
    printf "%-20s %s\n" "----------" "--------"
    for file in "$AGENTS_DIR"/*.md; do
        local name
        name="$(basename "$file" .md)"
        local model
        model="$(grep '^model:' "$file" | head -1 | sed 's/^model: *//')"
        printf "%-20s %s\n" "$name" "$model"
    done
}

if [[ $# -lt 1 ]]; then
    usage
fi

case "$1" in
    add)    shift; cmd_add "$@" ;;
    remove) shift; cmd_remove "$@" ;;
    list)   cmd_list ;;
    *)      echo "Error: unknown command '$1'" >&2; usage ;;
esac
```

- [ ] **Step 4: Make script executable**

```bash
chmod +x ~/.agents/skills/model-dispatch/scripts/manage-roster.sh
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd ~/git/llm_code && bats tests/model-dispatch/test_manage_roster.bats
```

Expected: All 14 tests PASS

- [ ] **Step 6: Run shellcheck**

```bash
shellcheck ~/.agents/skills/model-dispatch/scripts/manage-roster.sh
```

Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add tests/model-dispatch/test_manage_roster.bats
git commit -m "Feat: Add roster management script with tests

Bash script to add/remove/list model agent files in ~/.claude/agents/.
Validates input, uses template substitution, idempotent add."
```

Note: `manage-roster.sh` lives outside the git repo (in `~/.agents/skills/`), so only the test file is committed. The script itself is tracked by the skill directory.

---

### Task 3: Create the initial roster agent files

**Files:**
- Create: `~/.claude/agents/qwen3-coder.md`
- Create: `~/.claude/agents/glm-flash.md`
- Create: `~/.claude/agents/qwen3-80b.md`
- Create: `~/.claude/agents/nemotron-super.md`

- [ ] **Step 1: Generate all four agent files using the script**

```bash
SCRIPT=~/.agents/skills/model-dispatch/scripts/manage-roster.sh
bash "$SCRIPT" add qwen3-coder "qwen3-coder-next:128k"
bash "$SCRIPT" add glm-flash "glm-4.7-flash-64k:latest"
bash "$SCRIPT" add qwen3-80b "qwen3-next-80b:128k"
bash "$SCRIPT" add nemotron-super "nemotron-3-super:cloud"
```

- [ ] **Step 2: Verify all files were created correctly**

```bash
bash "$SCRIPT" list
```

Expected output:
```
SHORT NAME           MODEL ID
----------           --------
glm-flash            glm-4.7-flash-64k:latest
nemotron-super       nemotron-3-super:cloud
qwen3-80b            qwen3-next-80b:128k
qwen3-coder          qwen3-coder-next:128k
```

- [ ] **Step 3: Verify one agent file has correct content**

```bash
cat ~/.claude/agents/qwen3-coder.md
```

Expected: frontmatter with `name: qwen3-coder`, `model: qwen3-coder-next:128k`, and the system prompt.

No commit needed — agent files live outside the repo.

---

### Task 4: Write the SKILL.md

**Files:**
- Create: `~/.agents/skills/model-dispatch/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

Create `~/.agents/skills/model-dispatch/SKILL.md`:

```markdown
---
name: model-dispatch
description: Dispatch tasks to local or non-Anthropic models. Use when delegating
  work to specific models like qwen3, glm, nemotron, or any model not available
  through the native Agent tool model selector. Also use when user asks to add/remove
  models from the roster, or invokes /model-dispatch.
---

# Model Dispatch

Dispatch tasks to local and non-Anthropic models from within a Claude Code session.

## How It Works

Two dispatch paths depending on whether the model is in the roster:

### Roster Models (native subagent)

Models with agent files in `~/.claude/agents/` work as native subagents. Use the Agent tool with `subagent_type` set to the agent's short name.

**Check roster:** Run `~/.agents/skills/model-dispatch/scripts/manage-roster.sh list`

**Dispatch:** Use the Agent tool:
- Set `subagent_type` to the short name (e.g., `qwen3-coder`)
- Set `run_in_background: true` (default)
- Write a clear, complete task prompt

### Ad-hoc Models (CLI dispatch)

For models not in the roster, dispatch via Bash:

```bash
claude -p "<task prompt>" --model <model-id> --output-format text
```

Run with `run_in_background: true`. The task ID returned by Bash is used to check output later via `TaskOutput`.

**Before dispatching ad-hoc**, ask the user:
1. **Add to roster + dispatch now**: Run `manage-roster.sh add` then do CLI dispatch. Model available natively after session restart.
2. **One-off only**: Just do the CLI dispatch.

## Roster Management

Script: `~/.agents/skills/model-dispatch/scripts/manage-roster.sh`

```bash
# Add or update a model
~/.agents/skills/model-dispatch/scripts/manage-roster.sh add <short-name> <model-id>

# Remove a model
~/.agents/skills/model-dispatch/scripts/manage-roster.sh remove <short-name>

# List current roster
~/.agents/skills/model-dispatch/scripts/manage-roster.sh list
```

Short names must be lowercase alphanumeric with hyphens only (`[a-z0-9-]+`).

## Optional Periodic Monitoring

**Default:** Completion notification (built-in — you are notified when the background task finishes).

**Opt-in periodic checks:** When the user says something like "check every 5 minutes" or "monitor progress":

1. After dispatching, note the background task ID
2. Use `CronCreate` with the user's requested interval
3. Set the cron prompt to: "Check on background task <task_id> using TaskOutput with block: false. Report status (running/completed/failed). If completed or failed, delete this cron job using CronDelete with id <cron_id>."
4. Avoid minute 0 and 30 for the cron schedule

## Error Handling

- **Model unavailable**: Report the error output. Suggest checking `ollama list` or server status.
- **CLI dispatch timeout**: Report timeout. Suggest increasing timeout or simplifying the task.
- **Roster script failure**: Report the error message from the script.

## Dispatch Decision Flow

```
User requests task on model X
    │
    ├─ Is X in roster? (run manage-roster.sh list)
    │   ├─ YES → Agent tool with subagent_type: <short-name>
    │   │        Background by default
    │   │        If monitoring requested → CronCreate
    │   │
    │   └─ NO → Ask: add to roster or one-off?
    │       ├─ ADD → manage-roster.sh add, then CLI dispatch now
    │       └─ ONE-OFF → CLI dispatch via Bash background
    │
    └─ Completion notification (default) or periodic CronCreate checks
```

- [ ] **Step 2: Verify skill is well-formed**

```bash
head -10 ~/.agents/skills/model-dispatch/SKILL.md
```

Verify frontmatter has `name` and `description` fields.

- [ ] **Step 3: Commit**

The SKILL.md lives outside the repo (`~/.agents/skills/`). No git commit needed.

---

### Task 5: Symlink the skill and verify end-to-end

**Files:**
- Create: symlink `~/.claude/skills/model-dispatch` → `~/.agents/skills/model-dispatch`

- [ ] **Step 1: Create symlink**

```bash
ln -sf ~/.agents/skills/model-dispatch ~/.claude/skills/model-dispatch
```

- [ ] **Step 2: Verify skill directory structure**

```bash
find ~/.agents/skills/model-dispatch -type f | sort
```

Expected:
```
~/.agents/skills/model-dispatch/SKILL.md
~/.agents/skills/model-dispatch/references/agent-template.md
~/.agents/skills/model-dispatch/scripts/manage-roster.sh
```

- [ ] **Step 3: Verify agent files exist**

```bash
ls ~/.claude/agents/*.md
```

Expected: 4 files (qwen3-coder.md, glm-flash.md, qwen3-80b.md, nemotron-super.md)

- [ ] **Step 4: Verify roster list works**

```bash
~/.agents/skills/model-dispatch/scripts/manage-roster.sh list
```

Expected: All 4 models listed with correct IDs.

- [ ] **Step 5: Manual smoke test**

Restart Claude Code session. Verify:
1. `/agents` or `claude agents` shows the 4 new agents
2. Try: "Use qwen3-coder to list files in the current directory"
3. Confirm the subagent runs on the qwen3 model

- [ ] **Step 6: Verify all files in place**

```bash
# Skill files
find ~/.agents/skills/model-dispatch -type f | sort

# Agent files
ls ~/.claude/agents/*.md

# Symlink
ls -la ~/.claude/skills/model-dispatch
```

All test files should already be committed from Task 2. Verify with `git status`.
