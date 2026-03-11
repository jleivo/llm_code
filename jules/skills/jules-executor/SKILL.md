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

1. Install dependencies: `pip install -r <skill-path>/scripts/requirements.txt`
2. Verify auth: `python3 <skill-path>/scripts/jules_cli.py auth`
3. Run the plan: `python3 <skill-path>/scripts/run_plan.py <plan-file>`

Where `<skill-path>` is the directory containing this SKILL.md.

## Prerequisites

- Python deps installed in active venv: `hvac`, `requests`
- Vault access for Jules API key (`hosts/tuvmcpsrvp01/jules_api`) and GitHub token
- GitHub remote configured on the repo (`git remote -v` must show github.com)
- Plan file with `### Task N: Title` headers (see plan_parser.py for format)

## Running a Plan

### Interactive mode (stays running until all tasks complete)
```bash
python3 <skill-path>/scripts/run_plan.py docs/plans/my-plan.md
```

### Poll-once mode (single cycle, for cron or /loop)
```bash
python3 <skill-path>/scripts/run_plan.py docs/plans/my-plan.md \
  --poll-once --state-file /tmp/jules_state.json
```

### Configuration override
```bash
python3 <skill-path>/scripts/run_plan.py docs/plans/my-plan.md \
  --config <skill-path>/scripts/jules_config.ini
```

## Monitoring with /loop

Use Claude Code's `/loop` to poll periodically:
```
/loop 60 python3 <skill-path>/scripts/run_plan.py <plan-file> --poll-once --state-file /tmp/jules_state.json
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
python3 <skill-path>/scripts/jules_cli.py create --prompt "Fix the bug"
python3 <skill-path>/scripts/jules_cli.py status --session-id <id>
python3 <skill-path>/scripts/jules_cli.py chat --session-id <id>
python3 <skill-path>/scripts/jules_cli.py merge --session-id <id>
python3 <skill-path>/scripts/jules_cli.py list [--state CODING]
```

## Red Flags

- Never auto-merge without COMPLETED state
- Never exceed `max_concurrent_sessions` from config
- Never skip logging failed tasks
- Always `pull --rebase` before launching tasks from a worktree

## Troubleshooting

See [references/troubleshooting.md](references/troubleshooting.md) for common issues.
