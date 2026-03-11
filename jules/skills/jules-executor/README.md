# Jules Executor Skill

A Claude Code skill that dispatches implementation plan tasks to [Jules](https://jules.google.com) (Google's AI coding agent), monitors progress, and auto-merges completed PRs.

## What It Does

- Parses markdown implementation plans into structured tasks
- Creates Jules sessions for each task with GitHub repo context
- Polls sessions for progress with a live dashboard
- Detects and handles Jules questions (auto-answer or escalate)
- Auto-merges completed PRs via GitHub API
- Manages concurrency limits and task dependencies
- Supports both interactive and poll-once (cron) modes

## Installation

Copy or symlink into your skills directory:

```bash
# Option A: symlink
ln -s /path/to/jules-executor ~/.agents/skills/jules-executor

# Option B: copy
cp -r /path/to/jules-executor ~/.agents/skills/jules-executor
```

Install Python dependencies:

```bash
pip install -r ~/.agents/skills/jules-executor/scripts/requirements.txt
```

## Prerequisites

- **Vault access**: Jules API key at `hosts/tuvmcpsrvp01/jules_api`, GitHub token at `hosts/tuvmcpsrvp01/github_token`
- **Vault AppRole**: Credentials at `/etc/vault/host/{role_id,secret_id}`
- **GitHub remote**: The repo must have a GitHub remote (`git remote -v`)

## Usage

### As a Claude Code skill

Invoke with `/jules <plan-file>` in Claude Code. The skill handles everything automatically.

### Standalone

```bash
# Interactive mode — runs until all tasks complete
python3 scripts/run_plan.py docs/plans/my-feature.md

# Poll-once mode — single cycle for cron/automation
python3 scripts/run_plan.py docs/plans/my-feature.md --poll-once --state-file /tmp/jules_state.json

# CLI commands
python3 scripts/jules_cli.py auth              # Verify API credentials
python3 scripts/jules_cli.py create --prompt "Fix bug"  # Create a session
python3 scripts/jules_cli.py status --session-id <id>   # Check status
python3 scripts/jules_cli.py list --state CODING        # List sessions
```

### Plan File Format

```markdown
### Task 1: Add authentication
- executor: jules
- depends: none

Implement JWT authentication for the API.

### Task 2: Update config
- executor: claude
- depends: [1]

Add auth fields to configuration.
```

## Configuration

Edit `scripts/jules_config.ini`:

```ini
[jules]
max_concurrent_sessions = 3
poll_interval_seconds = 30
default_executor = jules
auto_merge = true
```
