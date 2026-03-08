# Jules - AI Coding Agent Integration

Library and CLI for collaborating with the Jules AI agent. Designed for both
programmatic use (from Claude Code skills) and direct command-line usage.

## Setup

1. **Jules API Key**: Create `jules_api_key.txt` in the repo root with your
   key from [jules.google.com/settings](https://jules.google.com/settings).

2. **GitHub Token**: For auto-merge, set `GITHUB_TOKEN` env var or create
   `github_token.txt`. Needs Pull Request read/write permission on the repo.

3. **Install dependencies**: `pip install -r jules/requirements.txt`

## Usage

### As Claude Code skill (/jules)

The primary way to use Jules. From Claude Code:

```
/jules docs/plans/2026-03-08-my-feature.md
```

This parses the plan, launches Jules sessions for each task, and enters
a monitoring dashboard. See the skill docs for details.

### Plan file format

Tasks in plan files support `executor` and `depends` metadata:

```markdown
### Task 1: Add authentication
- executor: jules       (default, can be omitted)
- depends: none         (no dependencies, can run in parallel)

### Task 2: Update config
- executor: claude      (run via Claude subagent instead)
- depends: [1]          (wait for task 1)
```

### CLI commands

Direct CLI usage:

```bash
# Create a session
./jules_cli.py create --prompt "Fix the auth bug" --title "Bugfix"

# Interactive chat
./jules_cli.py chat --session-id <ID>

# Check status
./jules_cli.py status --session-id <ID>

# Merge completed PR
./jules_cli.py merge --session-id <ID>
```

### Python library

```python
from jules import JulesSession, detect_github_repo

owner, repo = detect_github_repo()
session = JulesSession.create(
    prompt="Implement feature X",
    owner=owner,
    repo=repo,
)
print(f"Session: {session.session_id}")
print(f"Status: {session.status()}")
```

## Configuration

Edit `jules/jules_config.ini`:

```ini
[jules]
max_concurrent_sessions = 3    ; parallel Jules sessions
poll_interval_seconds = 30     ; dashboard refresh rate
default_executor = jules       ; default for tasks without executor:
auto_merge = true              ; auto-merge completed PRs
```

## File Structure

```
jules/
├── jules.py              # Library (JulesSession, load_config, etc.)
├── jules_cli.py          # CLI wrapper
├── jules_config.ini      # Configuration
├── orchestrator.py       # Task orchestration and dashboard
├── plan_parser.py        # Plan file parser
├── requirements.txt      # Dependencies
├── test_jules.py         # Library tests
├── test_jules_cli.py     # CLI tests
├── test_orchestrator.py  # Orchestrator tests
├── test_plan_parser.py   # Parser tests
└── README_JULES_CLI.md   # This file
```
