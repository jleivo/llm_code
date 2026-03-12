---
name: jules-executor
description: Execute implementation plans by dispatching tasks to Jules (Google's AI agent).
  Use when user invokes /jules, has a plan file with tasks for Jules, or wants
  Jules-first development. Handles plan parsing, session creation, polling,
  question handling, and auto-merging PRs.
---

# Jules Executor

Dispatches tasks from a markdown implementation plan to Jules AI sessions, polls for progress, auto-merges completed PRs, and prints a live dashboard. Tasks marked `executor: claude` are handed off via `superpowers:subagent-driven-development`.

## Quick Start

All commands go through the `jules-run` wrapper which auto-creates a venv inside the skill on first use. No manual `pip install` or venv activation needed.

1. Verify auth: `<skill-path>/scripts/jules-run jules_cli.py auth`
2. Run the plan: `<skill-path>/scripts/jules-run run_plan.py <plan-file>`

Where `<skill-path>` is the directory containing this SKILL.md.

## Prerequisites

- Python 3 with `venv` module available on the system (deps are auto-installed)
- Vault access for Jules API key (`hosts/tuvmcpsrvp01/jules_api`) and GitHub token
- GitHub remote configured on the repo (`git remote -v` must show github.com)
- Plan file with `### Task N: Title` headers (see plan_parser.py for format)

## Running a Plan

### Interactive mode (stays running until all tasks complete)
```bash
<skill-path>/scripts/jules-run run_plan.py docs/plans/my-plan.md
```

### Poll-once mode (single cycle, for cron or /loop)
```bash
<skill-path>/scripts/jules-run run_plan.py docs/plans/my-plan.md \
  --poll-once --state-file /tmp/jules_state.json
```

## Monitoring with /loop

Use Claude Code's `/loop` to poll periodically:
```
/loop 60 <skill-path>/scripts/jules-run run_plan.py <plan-file> --poll-once --state-file /tmp/jules_state.json
```

## Handling Jules Questions

When Jules asks a question (session state `WAITING_FOR_USER_RESPONSE`):

- **Auto-answer** if the answer is in the plan body, AGENTS.md, or codebase context
- **Escalate to user** if it requires a judgment call, architectural decision, or credential

Use `jules_cli.py chat --session-id <id>` for interactive Q&A with a session.

## Claude Tasks

Tasks with `executor: claude` are not sent to Jules. Instead, dispatch them using `superpowers:subagent-driven-development` with the task body as the prompt.

## CLI Commands

```bash
<skill-path>/scripts/jules-run jules_cli.py create --prompt "Fix the bug"
<skill-path>/scripts/jules-run jules_cli.py status --session-id <id>
<skill-path>/scripts/jules-run jules_cli.py chat --session-id <id>
<skill-path>/scripts/jules-run jules_cli.py merge --session-id <id>
<skill-path>/scripts/jules-run jules_cli.py list [--state CODING]
```

## Red Flags

- Never auto-merge without COMPLETED state
- Never exceed `max_concurrent_sessions` from config
- Never skip logging failed tasks
- Always `pull --rebase` before launching tasks from a worktree

## Troubleshooting

See [references/troubleshooting.md](references/troubleshooting.md) for common issues.
