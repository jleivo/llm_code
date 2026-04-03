---
name: jules-executor
description: Execute implementation plans by dispatching tasks to Jules (Google's AI agent).
  Use when user invokes /jules, has a plan file with tasks for Jules, or wants
  Jules-first development. Handles plan parsing, session creation, polling,
  question handling, and auto-merging PRs.
---

# Jules Executor

Dispatches tasks from a markdown implementation plan to Jules AI sessions. Tasks marked `executor: claude` are handed off via `superpowers:subagent-driven-development`.

## Steps

Follow these steps when the user invokes `/jules <plan-file>`:

1. **Verify prerequisites**
   - Confirm `<plan-file>` argument was provided. If not, ask the user for the plan file path.
   - Run `<skill-path>/scripts/jules-run jules_cli.py auth` to verify Vault and API access.

2. **Launch the plan**
   - Run `<skill-path>/scripts/jules-run run_plan.py <plan-file>` in interactive mode.
   - This parses the plan, creates Jules sessions respecting `depends:` ordering and concurrency limits, polls for progress, and auto-merges completed PRs.
   - Present the dashboard output to the user after each poll cycle.

3. **Handle `executor: claude` tasks**
   - Tasks marked `executor: claude` are not sent to Jules.
   - When their dependencies are met, dispatch them using `superpowers:subagent-driven-development` with the task body as the prompt.

4. **Handle Jules questions**
   - When a task shows `NEEDS_INPUT`, Jules has asked a question.
   - If the answer is in the plan body, AGENTS.md, or codebase context, use `<skill-path>/scripts/jules-run jules_cli.py chat --session-id <id>` to answer it.
   - If it requires a judgment call or credentials, escalate to the user.

5. **Report results**
   - When all tasks reach a terminal state, present the final summary to the user.
   - Flag any failed tasks with their error messages.

## Troubleshooting

See [README.md](README.md) for CLI usage and [references/troubleshooting.md](references/troubleshooting.md) for common issues.
