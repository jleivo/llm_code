---
name: jules-executor
description: Use when executing implementation plans where tasks should be dispatched to Jules AI agent instead of Claude subagents, or when user invokes /jules
---

# Jules Executor

Execute implementation plans by dispatching tasks to Jules (Google's AI coding agent). Jules is the default executor — tasks go to Jules unless explicitly marked `executor: claude`.

**Announce at start:** "I'm using the Jules executor to dispatch tasks to Jules."

## When to Use

- User invokes `/jules <plan-file-path>`
- An implementation plan has tasks with `executor: jules`
- User wants Jules-first development mode

## Prerequisites

- `jules_api_key.txt` in repo root (or `JULES_API_KEY_FILE` env var)
- `github_token.txt` or `GITHUB_TOKEN` env var (for auto-merge)
- The repo must have a GitHub remote

## The Process

1. **Parse the plan file** using `jules.parse_plan(content)`:
   - Read the plan file
   - Parse it to extract tasks with executor, depends, and body
   - Display the task list to the user

2. **Initialize orchestrator** using `jules.JulesOrchestrator(tasks, config)`:
   - Load config from `jules/jules_config.ini`
   - Create orchestrator with parsed tasks

3. **Launch initial tasks:**
   - Get launchable tasks (ready + within concurrency limit)
   - For each Jules task: construct prompt with task body + AGENTS.md context
   - Create JulesSession via the library
   - Mark task as ACTIVE in orchestrator
   - For Claude tasks that are ready: dispatch via subagent-driven-development pattern

4. **Enter monitoring loop** (poll every `poll_interval_seconds`):

   On each cycle:
   a. Poll all ACTIVE Jules sessions for status
   b. Check for questions from Jules (agentMessaged activities)
   c. If question found:
      - Read the question
      - Attempt to answer from context (plan file, AGENTS.md, codebase)
      - If confident: send answer via session.send_message(), log it
      - If not confident: mark task as NEEDS_INPUT, print question for user
   d. If session COMPLETED: get PR URL, auto-merge, git pull, mark MERGED
   e. If session FAILED: mark FAILED with error reason
   f. Launch any newly ready tasks (dependencies resolved + slots available)
   g. Print dashboard table
   h. If all tasks done: exit loop, print summary

5. **Handle user commands during loop:**
   - `answer <task#> <response>` — send response to Jules session
   - `cancel <task#>` — mark task as FAILED
   - `show <task#>` — show full session activities
   - `pause` — stop launching new tasks (existing continue)
   - `resume` — resume launching tasks

## Dashboard Format

```
Task   Description                    Executor   Status         PR
------------------------------------------------------------------------
1      Add authentication             jules      CODING         -
2      Update config schema           claude     completed      -
3      Add API endpoints              jules      MERGED         #42
4      Write integration tests        jules      QUEUED         -

Active: 1/3 slots | Queued: 1 | Completed: 2 | Failed: 0
```

## Question Auto-Answer Guidelines

**Answer automatically when:**
- Answer exists in AGENTS.md (e.g., "use pytest", "use .venv")
- Answer is in the plan file task description
- It's a straightforward convention question (file location, naming, etc.)
- The codebase has a clear existing pattern

**Escalate to user when:**
- Product/design decision not covered in plan
- Multiple equally valid technical approaches
- Question is about requirements outside the task scope
- You're not confident in the answer

When auto-answering, log:
```
  ↳ Jules asked: "question"
  ↳ Claude answered: "answer" (source: AGENTS.md)
```

## Integration

- **jules.py library** — all API calls go through `jules.JulesSession`
- **jules.plan_parser** — parses plan files
- **jules.orchestrator** — manages state, concurrency, dashboard
- **jules_config.ini** — configuration
- **superpowers:subagent-driven-development** — used for `executor: claude` tasks
- **superpowers:finishing-a-development-branch** — used after all tasks complete

## Red Flags

- Never auto-merge without checking session state is COMPLETED
- Never answer Jules questions about requirements you're unsure of
- Never exceed max_concurrent_sessions
- Never skip failed tasks without logging the error
- Never launch dependent tasks before dependencies complete
