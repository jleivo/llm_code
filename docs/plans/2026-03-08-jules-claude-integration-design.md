# Jules + Claude Code Integration Design

**Date:** 2026-03-08
**Status:** Approved

## Overview

Integrate Jules (Google's AI coding agent) as the default executor for development tasks orchestrated by Claude Code. Claude plans and divides work into tasks, Jules executes them autonomously, and Claude monitors progress via a live dashboard. The user can override individual tasks to run via Claude subagents instead.

## Architecture

```
User <-> Claude Code (planning, monitoring, question triage)
              |
              ├── /jules skill (orchestration)
              │     ├── Parse plan file
              │     ├── Launch Jules sessions (via jules.py library)
              │     ├── Monitor dashboard loop
              │     ├── Auto-answer Jules questions
              │     └── Auto-merge completed PRs
              │
              └── jules/jules.py (library)
                    ├── JulesSession class
                    ├── Auto-detect repo from git remote
                    └── API communication
```

## Plan File Format

Tasks in plan files (`docs/plans/YYYY-MM-DD-*.md`) gain `executor` and `depends` fields:

```markdown
### Task 1: Add user authentication
- executor: jules
- depends: none
- Description: Implement JWT-based auth...

### Task 2: Update config schema
- executor: claude
- depends: [1]
- Description: Add new auth fields to config...
```

- `executor: jules` is the default — can be omitted
- `executor: claude` overrides to run via Claude subagents
- `depends: none` marks a task as independent (can run in parallel)
- `depends: [1, 3]` sets explicit dependencies
- Tasks are sequential by default (task N depends on task N-1)

## Jules Library Refactor

Refactor `jules/jules_cli.py` into library + CLI wrapper:

### Library (`jules/jules.py`)

- `JulesSession` class encapsulating session lifecycle
- Auto-detect repo from `git remote -v` (parse GitHub owner/repo, construct Jules source identifier format `sources/github-{owner}-{repo}`)
- Configurable branch (default: current branch from `git rev-parse`)
- Methods: `create()`, `status()`, `send_message()`, `get_activities()`, `get_pr_url()`
- Raise exceptions instead of `sys.exit()` — callers handle errors
- API key lookup unchanged (file-based, vault-ready in future)

### CLI Wrapper (`jules/jules_cli.py`)

- Thin wrapper calling the library
- Same commands as today: `create`, `chat`, `status`, `merge`
- Handles user-facing output and `sys.exit()`

## `/jules` Skill

A Claude Code skill that orchestrates Jules-based development.

### Activation

- Invoked with `/jules <plan-file-path>`
- Can also be triggered by `subagent-driven-development` skill when it detects `executor: jules` tasks

### Workflow

1. Parse the plan file, extract tasks with their executors and dependencies
2. For each `jules` task: construct a prompt from task description + context (AGENTS.md, repo structure, branch)
3. Launch Jules sessions respecting concurrency limit
4. For `claude` tasks: hand off to existing subagent dispatch
5. Enter monitoring loop

### Task Prompt Construction

Each Jules session receives:
- The task description from the plan
- Relevant coding standards from AGENTS.md
- The branch to work on
- `requirePlanApproval=False`, `automationMode=AUTO_CREATE_PR`

## Dashboard & Monitoring Loop

### Dashboard Table

Reprinted on each update cycle:

```
┌──────┬──────────────────────────┬────────────┬─────────────┬───────────┐
│ Task │ Description              │ Executor   │ Status      │ PR        │
├──────┼──────────────────────────┼────────────┼─────────────┼───────────┤
│ 1    │ Add user authentication  │ jules      │ CODING      │ —         │
│ 2    │ Update config schema     │ claude     │ completed   │ —         │
│ 3    │ Add API endpoints        │ jules      │ COMPLETED   │ #42 ✓    │
│ 4    │ Write integration tests  │ jules      │ QUEUED      │ —         │
└──────┴──────────────────────────┴────────────┴─────────────┴───────────┘
Active: 2/3 slots | Queued: 1 | Completed: 1 | Failed: 0
```

### Loop Behavior

- Poll interval: 30 seconds
- On each cycle: poll all active Jules sessions, update and print the table
- When a slot frees up: dequeue the next waiting task and launch it
- Loop exits when all tasks are completed or failed

### User Interaction During Monitoring

- User can type commands: `answer <task#> <response>`, `pause`, `cancel <task#>`, `show details <task#>`
- Ctrl+C exits the loop gracefully, leaving Jules sessions running

## Two-Tier Question Handling

When Jules sends an `agentMessaged` activity with a question:

### Tier 1: Claude Auto-Answer

Claude reads the question in context of the plan file, AGENTS.md, and the codebase. If the answer is clearly derivable, Claude answers directly:

```
  ↳ Jules asked: "Should I use pytest or unittest?"
  ↳ Claude answered: "Use pytest, per AGENTS.md"
```

**Auto-answer when:** Answer exists in AGENTS.md, plan file, codebase conventions, or is a straightforward technical choice.

### Tier 2: Escalate to User

If Claude can't confidently answer, it escalates:

```
│ 1    │ Add user authentication  │ jules      │ NEEDS INPUT │ —         │
⚠ Task 1 — Claude couldn't determine the answer:
  Jules: "Should we support OAuth2 or just username/password?"
  Reply with: answer 1 <your response>
```

**Escalate when:** Product/design decision, multiple equally valid approaches, or question is outside task scope.

## Auto-Merge & Completion

### On Session COMPLETED

1. Fetch PR URL from session outputs
2. Auto-merge via GitHub API
3. Pull changes into local repo (`git pull`) so subsequent tasks see merged code
4. Update dashboard — mark task as `MERGED` with PR number

### Failure Handling

- Merge failure (conflict, API error): mark as `MERGE FAILED`, escalate to user
- Jules session failure: mark as `FAILED`, print reason, free the slot
- Failed tasks don't block other tasks unless explicit dependency exists

### Session End

- When all tasks finish: print final summary (succeeded, failed, PRs merged)
- Claude exits monitoring loop and returns to normal interactive mode

## Configuration

### File: `jules/jules_config.ini`

```ini
[jules]
max_concurrent_sessions = 3
poll_interval_seconds = 30
default_executor = jules
auto_merge = true
```

### API Keys (unchanged)

- `jules_api_key.txt` in repo root (gitignored)
- `github_token.txt` or `GITHUB_TOKEN` env var

## File Layout

```
jules/
├── jules.py              # Library (refactored from jules_cli.py)
├── jules_cli.py          # Thin CLI wrapper (refactored)
├── jules_config.ini      # Configuration
├── test_jules.py         # Library tests
├── test_jules_cli.py     # CLI wrapper tests (updated)
└── README_JULES_CLI.md   # Updated docs
```

Plus a skill file registered with superpowers for `/jules` activation.
