# Jules + Claude Code Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate Jules as the default task executor in Claude Code's plan-based workflow, with dashboard monitoring, auto-answer for Jules questions, and auto-merge on completion.

**Architecture:** Refactor `jules_cli.py` into a library + thin CLI wrapper. Create a `/jules` Claude Code skill that parses plan files, launches Jules sessions, monitors them in a dashboard loop, and handles questions/merges automatically. Configuration via INI file.

**Tech Stack:** Python 3.12, pytest, requests, requests_mock, configparser. Claude Code skill in Markdown.

---

### Task 1: Create requirements.txt for jules/

**Files:**
- Create: `jules/requirements.txt`

**Step 1: Write requirements.txt**

```
requests==2.32.3
requests-mock==1.12.1
pytest==8.3.4
```

Pin to latest stable versions. These are the dependencies already used by the existing code.

**Step 2: Install and verify**

Run: `source .venv/bin/activate && pip install -r jules/requirements.txt`
Expected: All packages install successfully (likely already installed).

**Step 3: Commit**

```bash
git add jules/requirements.txt
git commit --author="lunatic <lunatic@discord-bot>" -m "Feat: Add requirements.txt for jules module"
```

---

### Task 2: Refactor jules_cli.py into library (jules.py)

**Files:**
- Create: `jules/jules.py`
- Create: `jules/__init__.py`
- Modify: `jules/jules_cli.py` (gut it to thin wrapper)

**Step 1: Write failing tests for the library**

Create `jules/test_jules.py`:

```python
import pytest
import subprocess
from unittest.mock import patch, MagicMock
from jules import JulesSession, JulesError, detect_github_repo

# --- detect_github_repo tests ---

def test_detect_github_repo_https():
    """Auto-detect repo from HTTPS git remote."""
    mock_result = MagicMock()
    mock_result.stdout = "origin\thttps://github.com/myuser/myrepo.git (fetch)\norigin\thttps://github.com/myuser/myrepo.git (push)\n"
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        owner, repo = detect_github_repo()
        assert owner == "myuser"
        assert repo == "myrepo"
        mock_run.assert_called_once()

def test_detect_github_repo_ssh():
    """Auto-detect repo from SSH git remote."""
    mock_result = MagicMock()
    mock_result.stdout = "origin\tgit@github.com:myuser/myrepo.git (fetch)\norigin\tgit@github.com:myuser/myrepo.git (push)\n"
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        owner, repo = detect_github_repo()
        assert owner == "myuser"
        assert repo == "myrepo"

def test_detect_github_repo_no_remote():
    """Raise JulesError when no GitHub remote found."""
    mock_result = MagicMock()
    mock_result.stdout = ""
    with patch("subprocess.run", return_value=mock_result):
        with pytest.raises(JulesError, match="Could not detect GitHub repo"):
            detect_github_repo()

# --- JulesSession tests ---

@pytest.fixture(autouse=True)
def mock_api_key(monkeypatch):
    monkeypatch.setenv("JULES_API_KEY_FILE", "/dev/null")
    monkeypatch.setattr("jules.jules.get_jules_api_key", lambda: "fake-api-key")

def test_session_create(requests_mock):
    """Create a Jules session with auto-detected repo."""
    mock_response = {
        "id": "session-123",
        "name": "sessions/session-123",
        "url": "https://jules.google.com/session/session-123",
        "state": "STARTING"
    }
    requests_mock.post("https://jules.googleapis.com/v1alpha/sessions", json=mock_response)

    session = JulesSession.create(
        prompt="Fix the bug",
        title="Bugfix",
        owner="myuser",
        repo="myrepo",
        branch="main"
    )
    assert session.session_id == "session-123"
    assert session.url == "https://jules.google.com/session/session-123"

    payload = requests_mock.request_history[0].json()
    assert payload["prompt"] == "Fix the bug"
    assert payload["sourceContext"]["source"] == "sources/github-myuser-myrepo"
    assert payload["sourceContext"]["githubRepoContext"]["startingBranch"] == "main"
    assert payload["requirePlanApproval"] is False
    assert payload["automationMode"] == "AUTO_CREATE_PR"

def test_session_status(requests_mock):
    """Fetch session status."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions/session-123",
        json={"id": "session-123", "state": "COMPLETED"}
    )

    session = JulesSession(session_id="session-123")
    state = session.status()
    assert state == "COMPLETED"

def test_session_send_message(requests_mock):
    """Send a message to a session."""
    requests_mock.post(
        "https://jules.googleapis.com/v1alpha/sessions/session-123:sendMessage",
        json={}
    )

    session = JulesSession(session_id="session-123")
    session.send_message("Use pytest")

    payload = requests_mock.request_history[0].json()
    assert payload["prompt"] == "Use pytest"

def test_session_get_activities_pagination(requests_mock):
    """Get all activities with pagination."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions/session-123/activities?pageSize=50",
        json={"activities": [{"id": "act1"}], "nextPageToken": "token1"}
    )
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions/session-123/activities?pageSize=50&pageToken=token1",
        json={"activities": [{"id": "act2"}]}
    )

    session = JulesSession(session_id="session-123")
    activities = session.get_activities()
    assert len(activities) == 2
    assert activities[0]["id"] == "act1"
    assert activities[1]["id"] == "act2"

def test_session_get_pr_url(requests_mock):
    """Extract PR URL from completed session."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions/session-123",
        json={
            "id": "session-123",
            "state": "COMPLETED",
            "outputs": [{"pullRequest": {"url": "https://github.com/myuser/myrepo/pull/42"}}]
        }
    )

    session = JulesSession(session_id="session-123")
    pr_url = session.get_pr_url()
    assert pr_url == "https://github.com/myuser/myrepo/pull/42"

def test_session_get_pr_url_no_pr(requests_mock):
    """Return None when no PR exists."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions/session-123",
        json={"id": "session-123", "state": "RUNNING"}
    )

    session = JulesSession(session_id="session-123")
    pr_url = session.get_pr_url()
    assert pr_url is None

def test_session_merge_pr(requests_mock, monkeypatch):
    """Merge PR via GitHub API."""
    monkeypatch.setattr("jules.jules.get_github_token", lambda: "fake-token")

    # Mock get_pr_url
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions/session-123",
        json={
            "id": "session-123",
            "state": "COMPLETED",
            "outputs": [{"pullRequest": {"url": "https://github.com/myuser/myrepo/pull/42"}}]
        }
    )
    requests_mock.put(
        "https://api.github.com/repos/myuser/myrepo/pulls/42/merge",
        json={"merged": True},
        status_code=200
    )

    session = JulesSession(session_id="session-123")
    result = session.merge_pr()
    assert result is True

def test_session_has_pending_question(requests_mock):
    """Detect when Jules has asked a question."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions/session-123/activities?pageSize=50",
        json={
            "activities": [
                {"id": "act1", "originator": "agent", "agentMessaged": {"agentMessage": "Should I use JWT?"}},
            ]
        }
    )

    session = JulesSession(session_id="session-123")
    question = session.get_latest_question()
    assert question == "Should I use JWT?"
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest jules/test_jules.py -v`
Expected: FAIL — `jules` module doesn't exist yet.

**Step 3: Write the library**

Create `jules/__init__.py`:

```python
from jules.jules import JulesSession, JulesError, detect_github_repo
```

Create `jules/jules.py`:

```python
#!/usr/bin/env python3
# 1.0.0
"""
Jules library - Programmatic interface to the Jules AI coding agent API.
"""

import os
import re
import subprocess
import requests


JULES_API_BASE = "https://jules.googleapis.com/v1alpha"


class JulesError(Exception):
    """Base exception for Jules library errors."""


def get_jules_api_key():
    """Retrieves the Jules API key from a file."""
    key_file = os.environ.get("JULES_API_KEY_FILE", "jules_api_key.txt")
    try:
        with open(key_file, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        raise JulesError(
            f"API key file not found: {key_file}. "
            "Create jules_api_key.txt or set JULES_API_KEY_FILE env var."
        )


def get_github_token():
    """Retrieves the GitHub token from a file or environment variable."""
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return token
    try:
        with open("github_token.txt", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        raise JulesError(
            "GitHub token not found. Set GITHUB_TOKEN env var or create github_token.txt."
        )


def detect_github_repo():
    """Auto-detect GitHub owner/repo from git remote.

    Returns:
        tuple: (owner, repo) strings

    Raises:
        JulesError: If no GitHub remote is found.
    """
    result = subprocess.run(
        ["git", "remote", "-v"],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        # Match HTTPS: https://github.com/owner/repo.git
        match = re.search(r"github\.com[/:]([^/]+)/([^/\s]+?)(?:\.git)?(?:\s|\Z)", line)
        if match:
            return match.group(1), match.group(2)
    raise JulesError("Could not detect GitHub repo from git remote -v")


def detect_current_branch():
    """Detect the current git branch.

    Returns:
        str: Branch name.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def _jules_request(method, endpoint, data=None, params=None):
    """Makes a request to the Jules API.

    Returns:
        dict or None: Parsed JSON response.

    Raises:
        JulesError: On API errors.
    """
    url = f"{JULES_API_BASE}/{endpoint.lstrip('/')}"
    headers = {
        "x-goog-api-key": get_jules_api_key(),
        "Content-Type": "application/json"
    }

    try:
        response = requests.request(method, url, headers=headers, json=data, params=params)
        response.raise_for_status()
        if response.text:
            return response.json()
        return None
    except requests.exceptions.HTTPError as e:
        msg = f"Jules API error: {e}"
        if e.response is not None:
            msg += f" — {e.response.text}"
        raise JulesError(msg)


class JulesSession:
    """Represents a Jules coding session."""

    def __init__(self, session_id, url=None):
        self.session_id = session_id
        self.url = url
        self._last_seen_activity_id = None

    @classmethod
    def create(cls, prompt, title="Task via Jules CLI", owner=None, repo=None, branch=None):
        """Create a new Jules session.

        Args:
            prompt: Task description for Jules.
            title: Session title.
            owner: GitHub repo owner (auto-detected if None).
            repo: GitHub repo name (auto-detected if None).
            branch: Git branch (auto-detected if None).

        Returns:
            JulesSession: The created session.
        """
        if owner is None or repo is None:
            owner, repo = detect_github_repo()
        if branch is None:
            branch = detect_current_branch()

        source = f"sources/github-{owner}-{repo}"

        data = {
            "prompt": prompt,
            "title": title,
            "sourceContext": {
                "source": source,
                "githubRepoContext": {
                    "startingBranch": branch
                }
            },
            "requirePlanApproval": False,
            "automationMode": "AUTO_CREATE_PR"
        }
        resp = _jules_request("POST", "sessions", data=data)
        return cls(session_id=resp["id"], url=resp.get("url"))

    def status(self):
        """Get the current session state.

        Returns:
            str: Session state (e.g., STARTING, RUNNING, COMPLETED, FAILED).
        """
        resp = _jules_request("GET", f"sessions/{self.session_id}")
        return resp.get("state")

    def get_session_data(self):
        """Get full session data.

        Returns:
            dict: Full session response.
        """
        return _jules_request("GET", f"sessions/{self.session_id}")

    def send_message(self, prompt):
        """Send a message to the session.

        Args:
            prompt: Message text.
        """
        data = {"prompt": prompt}
        _jules_request("POST", f"sessions/{self.session_id}:sendMessage", data=data)

    def get_activities(self, page_size=50):
        """Get all activities for this session, handling pagination.

        Returns:
            list: All activity dicts.
        """
        activities = []
        page_token = None
        while True:
            params = {"pageSize": page_size}
            if page_token:
                params["pageToken"] = page_token
            resp = _jules_request("GET", f"sessions/{self.session_id}/activities", params=params)
            if not resp:
                break
            activities.extend(resp.get("activities", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return activities

    def get_new_activities(self):
        """Get activities since last check.

        Returns:
            list: New activity dicts since last call.
        """
        all_activities = self.get_activities()
        if self._last_seen_activity_id is None:
            self._last_seen_activity_id = all_activities[-1]["id"] if all_activities else None
            return all_activities

        new = []
        found = False
        for act in all_activities:
            if found:
                new.append(act)
            elif act["id"] == self._last_seen_activity_id:
                found = True

        if new:
            self._last_seen_activity_id = new[-1]["id"]
        return new

    def get_latest_question(self):
        """Check if Jules has asked a question.

        Returns:
            str or None: The question text, or None.
        """
        activities = self.get_activities()
        for act in reversed(activities):
            if act.get("originator") == "agent" and "agentMessaged" in act:
                return act["agentMessaged"].get("agentMessage")
        return None

    def get_pr_url(self):
        """Get the PR URL from a completed session.

        Returns:
            str or None: The PR URL, or None if no PR.
        """
        data = self.get_session_data()
        for output in data.get("outputs", []):
            if "pullRequest" in output:
                return output["pullRequest"].get("url")
        return None

    def merge_pr(self):
        """Merge the PR created by this session.

        Returns:
            bool: True if merged successfully.

        Raises:
            JulesError: If merge fails or no PR found.
        """
        pr_url = self.get_pr_url()
        if not pr_url:
            raise JulesError("No PR URL found in session outputs")

        match = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
        if not match:
            raise JulesError(f"Could not parse PR URL: {pr_url}")

        owner, repo, pr_number = match.groups()
        token = get_github_token()

        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/merge"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

        response = requests.put(url, headers=headers)
        if response.status_code == 200:
            return True
        raise JulesError(f"Failed to merge PR: {response.status_code} — {response.text}")
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest jules/test_jules.py -v`
Expected: All 11 tests PASS.

**Step 5: Commit**

```bash
git add jules/__init__.py jules/jules.py jules/test_jules.py
git commit --author="lunatic <lunatic@discord-bot>" -m "Feat: Refactor Jules into library with JulesSession class

Auto-detect repo from git remote, raise exceptions instead of sys.exit,
support programmatic usage for skill integration."
```

---

### Task 3: Refactor jules_cli.py to use the library

**Files:**
- Modify: `jules/jules_cli.py` (rewrite as thin wrapper)
- Modify: `jules/test_jules_cli.py` (update imports)

**Step 1: Write failing test for CLI wrapper**

Update `jules/test_jules_cli.py` to test the CLI uses the library:

```python
import pytest
from unittest.mock import patch, MagicMock
from jules_cli import main


def test_cli_create(capsys):
    """CLI create command uses JulesSession.create."""
    mock_session = MagicMock()
    mock_session.session_id = "session-123"
    mock_session.url = "https://jules.google.com/session/session-123"

    with patch("jules_cli.JulesSession") as MockSession:
        MockSession.create.return_value = mock_session
        with patch("sys.argv", ["jules_cli.py", "create", "--prompt", "Fix bug"]):
            main()

    MockSession.create.assert_called_once_with("Fix bug", "Task via Jules CLI")
    captured = capsys.readouterr()
    assert "session-123" in captured.out


def test_cli_status(capsys):
    """CLI status command calls session.status and prints activities."""
    mock_session = MagicMock()
    mock_session.status.return_value = "RUNNING"
    mock_session.get_activities.return_value = [
        {"id": "act1", "originator": "agent", "description": "Working..."}
    ]
    mock_session.get_session_data.return_value = {"state": "RUNNING"}

    with patch("jules_cli.JulesSession", return_value=mock_session):
        with patch("sys.argv", ["jules_cli.py", "status", "--session-id", "session-123"]):
            main()

    captured = capsys.readouterr()
    assert "RUNNING" in captured.out


def test_cli_merge_completed(capsys):
    """CLI merge command merges when session is COMPLETED."""
    mock_session = MagicMock()
    mock_session.status.return_value = "COMPLETED"
    mock_session.merge_pr.return_value = True

    with patch("jules_cli.JulesSession", return_value=mock_session):
        with patch("sys.argv", ["jules_cli.py", "merge", "--session-id", "session-123"]):
            main()

    mock_session.merge_pr.assert_called_once()
    captured = capsys.readouterr()
    assert "merged" in captured.out.lower() or "Merged" in captured.out


def test_cli_merge_not_completed(capsys):
    """CLI merge command refuses when session not COMPLETED."""
    mock_session = MagicMock()
    mock_session.status.return_value = "RUNNING"

    with patch("jules_cli.JulesSession", return_value=mock_session):
        with patch("sys.argv", ["jules_cli.py", "merge", "--session-id", "session-123"]):
            with pytest.raises(SystemExit):
                main()
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest jules/test_jules_cli.py -v`
Expected: FAIL — `jules_cli.py` still uses old implementation.

**Step 3: Rewrite jules_cli.py as thin wrapper**

```python
#!/usr/bin/env python3
# 1.0.0
"""
Jules CLI - Command-line wrapper for the Jules AI agent library.
"""

import argparse
import sys
import time
from jules import JulesSession, JulesError


def poll_and_print(session):
    """Print session status and recent activities."""
    state = session.status()
    print(f"Session State: {state}")

    activities = session.get_activities()
    if activities:
        for act in activities[-5:]:
            originator = act.get("originator", "system")
            description = act.get("description", "")
            print(f"[{originator.upper()}] {description}")
            if "agentMessaged" in act:
                print(f"  Message: {act['agentMessaged'].get('agentMessage')}")
            if "sessionFailed" in act:
                print(f"  Failure Reason: {act['sessionFailed'].get('reason')}")

    data = session.get_session_data()
    if data.get("state") == "COMPLETED":
        for output in data.get("outputs", []):
            if "pullRequest" in output:
                print(f"\nWork completed! PR Created: {output['pullRequest'].get('url')}")


def chat_repl(session):
    """Interactive REPL with Jules."""
    print(f"Entering chat with session {session.session_id}. Type 'exit' or 'quit' to leave.")

    # Initialize activity tracking
    activities = session.get_activities()
    session._last_seen_activity_id = activities[-1]["id"] if activities else None

    while True:
        try:
            user_input = input("You > ")
            if user_input.lower() in ["exit", "quit"]:
                break
            if not user_input.strip():
                continue

            session.send_message(user_input)
            print("Message sent. Waiting for response...")

            found_response = False
            for _ in range(60):
                time.sleep(2)
                new_activities = session.get_new_activities()
                for act in new_activities:
                    if act.get("originator") == "agent" and "agentMessaged" in act:
                        print(f"Jules > {act['agentMessaged'].get('agentMessage')}")
                        found_response = True
                    elif act.get("originator") == "system" and "sessionFailed" in act:
                        print(f"System > Session failed: {act['sessionFailed'].get('reason')}")
                        found_response = True
                if found_response:
                    break

            if not found_response:
                print("(No response from Jules yet. Use 'status' to check later.)")

        except KeyboardInterrupt:
            break


def main():
    parser = argparse.ArgumentParser(
        description="Jules CLI for agentic collaboration.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ./jules_cli.py create --prompt "Refactor tests"
  ./jules_cli.py chat --session-id 12345
  ./jules_cli.py status --session-id 12345
  ./jules_cli.py merge --session-id 12345
"""
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    create_parser = subparsers.add_parser("create", help="Create a new Jules session")
    create_parser.add_argument("--prompt", required=True, help="The task for Jules")
    create_parser.add_argument("--title", help="Optional title", default="Task via Jules CLI")

    chat_parser = subparsers.add_parser("chat", help="Start a REPL with an active session")
    chat_parser.add_argument("--session-id", required=True, help="The session ID")

    status_parser = subparsers.add_parser("status", help="Check session status")
    status_parser.add_argument("--session-id", required=True, help="The session ID")

    merge_parser = subparsers.add_parser("merge", help="Merge the PR from a completed session")
    merge_parser.add_argument("--session-id", required=True, help="The session ID")

    args = parser.parse_args()

    try:
        if args.command == "create":
            session = JulesSession.create(args.prompt, args.title)
            print(f"Session created! ID: {session.session_id}")
            print(f"URL: {session.url}")

        elif args.command == "chat":
            session = JulesSession(session_id=args.session_id)
            chat_repl(session)

        elif args.command == "status":
            session = JulesSession(session_id=args.session_id)
            poll_and_print(session)

        elif args.command == "merge":
            session = JulesSession(session_id=args.session_id)
            state = session.status()
            if state != "COMPLETED":
                print(f"Cannot merge. Session state is {state}, not COMPLETED.")
                sys.exit(1)
            session.merge_pr()
            print("Successfully merged PR!")

        else:
            parser.print_help()

    except JulesError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

**Step 4: Run all jules tests**

Run: `.venv/bin/python -m pytest jules/ -v`
Expected: All tests in both `test_jules.py` and `test_jules_cli.py` PASS.

**Step 5: Commit**

```bash
git add jules/jules_cli.py jules/test_jules_cli.py
git commit --author="lunatic <lunatic@discord-bot>" -m "Feat: Refactor jules_cli.py to thin wrapper over jules library"
```

---

### Task 4: Create jules_config.ini with configparser support

**Files:**
- Create: `jules/jules_config.ini`
- Modify: `jules/jules.py` (add `load_config()` function)
- Modify: `jules/test_jules.py` (add config tests)

**Step 1: Write failing tests for config**

Add to `jules/test_jules.py`:

```python
from jules.jules import load_config
import tempfile
import os

def test_load_config_defaults():
    """Load config returns defaults when no file exists."""
    config = load_config("/nonexistent/path/config.ini")
    assert config["max_concurrent_sessions"] == 3
    assert config["poll_interval_seconds"] == 30
    assert config["default_executor"] == "jules"
    assert config["auto_merge"] is True

def test_load_config_custom(tmp_path):
    """Load config reads custom values from file."""
    config_file = tmp_path / "jules_config.ini"
    config_file.write_text(
        "[jules]\n"
        "max_concurrent_sessions = 5\n"
        "poll_interval_seconds = 15\n"
        "default_executor = claude\n"
        "auto_merge = false\n"
    )
    config = load_config(str(config_file))
    assert config["max_concurrent_sessions"] == 5
    assert config["poll_interval_seconds"] == 15
    assert config["default_executor"] == "claude"
    assert config["auto_merge"] is False
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest jules/test_jules.py::test_load_config_defaults jules/test_jules.py::test_load_config_custom -v`
Expected: FAIL — `load_config` doesn't exist.

**Step 3: Implement load_config in jules.py**

Add to `jules/jules.py`:

```python
import configparser

DEFAULTS = {
    "max_concurrent_sessions": 3,
    "poll_interval_seconds": 30,
    "default_executor": "jules",
    "auto_merge": True,
}


def load_config(config_path="jules/jules_config.ini"):
    """Load configuration from INI file, falling back to defaults.

    Args:
        config_path: Path to the config file.

    Returns:
        dict: Configuration values.
    """
    cp = configparser.ConfigParser()
    cp.read(config_path)

    config = dict(DEFAULTS)
    if cp.has_section("jules"):
        config["max_concurrent_sessions"] = cp.getint("jules", "max_concurrent_sessions", fallback=DEFAULTS["max_concurrent_sessions"])
        config["poll_interval_seconds"] = cp.getint("jules", "poll_interval_seconds", fallback=DEFAULTS["poll_interval_seconds"])
        config["default_executor"] = cp.get("jules", "default_executor", fallback=DEFAULTS["default_executor"])
        config["auto_merge"] = cp.getboolean("jules", "auto_merge", fallback=DEFAULTS["auto_merge"])
    return config
```

**Step 4: Create jules_config.ini**

```ini
[jules]
max_concurrent_sessions = 3
poll_interval_seconds = 30
default_executor = jules
auto_merge = true
```

**Step 5: Update `jules/__init__.py` to export load_config**

```python
from jules.jules import JulesSession, JulesError, detect_github_repo, load_config
```

**Step 6: Run tests**

Run: `.venv/bin/python -m pytest jules/test_jules.py -v`
Expected: All tests PASS.

**Step 7: Commit**

```bash
git add jules/jules_config.ini jules/jules.py jules/__init__.py jules/test_jules.py
git commit --author="lunatic <lunatic@discord-bot>" -m "Feat: Add jules_config.ini with configurable concurrency and polling"
```

---

### Task 5: Create plan file parser

**Files:**
- Create: `jules/plan_parser.py`
- Create: `jules/test_plan_parser.py`
- Modify: `jules/__init__.py` (export parser)

**Step 1: Write failing tests**

Create `jules/test_plan_parser.py`:

```python
import pytest
from jules.plan_parser import parse_plan

SAMPLE_PLAN = """# Feature Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans

**Goal:** Build the thing.

---

### Task 1: Add authentication

- executor: jules
- depends: none
- Description: Implement JWT auth for the API.

Detailed instructions here about what to build.

### Task 2: Update config schema

- executor: claude
- depends: [1]
- Description: Add auth fields to config.

More details about config changes.

### Task 3: Write integration tests

- depends: [1, 2]
- Description: Test the auth + config together.

Testing instructions here.

### Task 4: Update docs

- executor: jules
- Description: Update README with auth docs.
"""

def test_parse_plan_extracts_tasks():
    """Parse plan file extracts all tasks."""
    tasks = parse_plan(SAMPLE_PLAN)
    assert len(tasks) == 4

def test_parse_plan_task_numbers():
    """Tasks have correct numbers."""
    tasks = parse_plan(SAMPLE_PLAN)
    assert [t["number"] for t in tasks] == [1, 2, 3, 4]

def test_parse_plan_task_titles():
    """Tasks have correct titles."""
    tasks = parse_plan(SAMPLE_PLAN)
    assert tasks[0]["title"] == "Add authentication"
    assert tasks[1]["title"] == "Update config schema"

def test_parse_plan_executor_explicit():
    """Explicit executor is parsed."""
    tasks = parse_plan(SAMPLE_PLAN)
    assert tasks[0]["executor"] == "jules"
    assert tasks[1]["executor"] == "claude"

def test_parse_plan_executor_default():
    """Missing executor defaults to 'jules'."""
    tasks = parse_plan(SAMPLE_PLAN)
    # Task 3 has no executor field
    assert tasks[2]["executor"] == "jules"

def test_parse_plan_executor_default_override():
    """Default executor can be overridden."""
    tasks = parse_plan(SAMPLE_PLAN, default_executor="claude")
    assert tasks[2]["executor"] == "claude"
    # Explicit executors are not overridden
    assert tasks[0]["executor"] == "jules"

def test_parse_plan_depends_none():
    """depends: none means no dependencies."""
    tasks = parse_plan(SAMPLE_PLAN)
    assert tasks[0]["depends"] == []

def test_parse_plan_depends_list():
    """depends: [1, 2] is parsed as list of ints."""
    tasks = parse_plan(SAMPLE_PLAN)
    assert tasks[2]["depends"] == [1, 2]

def test_parse_plan_depends_default_sequential():
    """Missing depends defaults to previous task."""
    tasks = parse_plan(SAMPLE_PLAN)
    # Task 4 has no depends field, defaults to [3]
    assert tasks[3]["depends"] == [3]

def test_parse_plan_body():
    """Task body contains the full text after metadata."""
    tasks = parse_plan(SAMPLE_PLAN)
    assert "Implement JWT auth" in tasks[0]["body"]
    assert "Detailed instructions" in tasks[0]["body"]
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest jules/test_plan_parser.py -v`
Expected: FAIL — module doesn't exist.

**Step 3: Implement plan_parser.py**

```python
#!/usr/bin/env python3
# 1.0.0
"""
Plan file parser - Extracts tasks from markdown implementation plans.
"""

import re


def parse_plan(content, default_executor="jules"):
    """Parse a markdown plan file into structured tasks.

    Args:
        content: The full markdown content of the plan file.
        default_executor: Default executor for tasks without an explicit one.

    Returns:
        list[dict]: Tasks with keys: number, title, executor, depends, body.
    """
    # Split on ### Task N: Title
    task_pattern = re.compile(r"^### Task (\d+):\s*(.+)$", re.MULTILINE)
    matches = list(task_pattern.finditer(content))

    tasks = []
    for i, match in enumerate(matches):
        number = int(match.group(1))
        title = match.group(2).strip()

        # Extract body: from after the heading to the next heading (or end)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end].strip()

        # Parse metadata from body
        executor = _extract_field(body, "executor", default_executor)
        depends = _extract_depends(body, number)

        # Remove metadata lines from body for clean task text
        clean_body = _remove_metadata(body)

        tasks.append({
            "number": number,
            "title": title,
            "executor": executor,
            "depends": depends,
            "body": clean_body,
        })

    return tasks


def _extract_field(body, field_name, default):
    """Extract a metadata field value from task body."""
    pattern = re.compile(rf"^-\s*{field_name}:\s*(.+)$", re.MULTILINE | re.IGNORECASE)
    match = pattern.search(body)
    if match:
        return match.group(1).strip()
    return default


def _extract_depends(body, task_number):
    """Extract dependency list from task body."""
    raw = _extract_field(body, "depends", None)
    if raw is None:
        # Default: depend on previous task (except task 1)
        return [task_number - 1] if task_number > 1 else []
    if raw.lower() == "none":
        return []
    # Parse [1, 2, 3] format
    nums = re.findall(r"\d+", raw)
    return [int(n) for n in nums]


def _remove_metadata(body):
    """Remove metadata lines (- key: value) from the start of the body."""
    lines = body.split("\n")
    clean_lines = []
    past_metadata = False
    for line in lines:
        if not past_metadata and re.match(r"^-\s*(executor|depends|Description):", line, re.IGNORECASE):
            continue
        past_metadata = True
        clean_lines.append(line)
    return "\n".join(clean_lines).strip()
```

**Step 4: Update `jules/__init__.py`**

```python
from jules.jules import JulesSession, JulesError, detect_github_repo, load_config
from jules.plan_parser import parse_plan
```

**Step 5: Run tests**

Run: `.venv/bin/python -m pytest jules/test_plan_parser.py -v`
Expected: All 10 tests PASS.

**Step 6: Commit**

```bash
git add jules/plan_parser.py jules/test_plan_parser.py jules/__init__.py
git commit --author="lunatic <lunatic@discord-bot>" -m "Feat: Add plan file parser with executor and dependency support"
```

---

### Task 6: Create the Jules orchestrator

**Files:**
- Create: `jules/orchestrator.py`
- Create: `jules/test_orchestrator.py`
- Modify: `jules/__init__.py`

This is the core component: manages task queue, concurrency, polling, dashboard, question handling, and auto-merge.

**Step 1: Write failing tests**

Create `jules/test_orchestrator.py`:

```python
import pytest
from unittest.mock import patch, MagicMock, call
from jules.orchestrator import JulesOrchestrator

@pytest.fixture
def sample_tasks():
    return [
        {"number": 1, "title": "Auth", "executor": "jules", "depends": [], "body": "Add JWT auth"},
        {"number": 2, "title": "Config", "executor": "claude", "depends": [1], "body": "Update config"},
        {"number": 3, "title": "Tests", "executor": "jules", "depends": [], "body": "Write tests"},
    ]

@pytest.fixture
def config():
    return {
        "max_concurrent_sessions": 2,
        "poll_interval_seconds": 1,
        "default_executor": "jules",
        "auto_merge": True,
    }

def test_orchestrator_identifies_ready_tasks(sample_tasks, config):
    """Tasks with no unresolved dependencies are ready."""
    orch = JulesOrchestrator(sample_tasks, config)
    ready = orch.get_ready_tasks()
    # Task 1 (no deps) and Task 3 (no deps) are ready
    # Task 2 depends on 1, not ready
    assert [t["number"] for t in ready] == [1, 3]

def test_orchestrator_respects_concurrency(sample_tasks, config):
    """Don't launch more than max_concurrent_sessions."""
    config["max_concurrent_sessions"] = 1
    orch = JulesOrchestrator(sample_tasks, config)
    ready = orch.get_launchable_tasks()
    assert len(ready) <= 1

def test_orchestrator_unblocks_after_completion(sample_tasks, config):
    """Completing task 1 unblocks task 2."""
    orch = JulesOrchestrator(sample_tasks, config)
    orch.mark_completed(1)
    ready = orch.get_ready_tasks()
    assert 2 in [t["number"] for t in ready]

def test_orchestrator_skips_claude_tasks(sample_tasks, config):
    """Claude tasks are tracked but not launched as Jules sessions."""
    orch = JulesOrchestrator(sample_tasks, config)
    jules_tasks = orch.get_jules_tasks()
    assert [t["number"] for t in jules_tasks] == [1, 3]

def test_orchestrator_dashboard_format(sample_tasks, config):
    """Dashboard returns formatted string with all tasks."""
    orch = JulesOrchestrator(sample_tasks, config)
    dashboard = orch.render_dashboard()
    assert "Auth" in dashboard
    assert "Config" in dashboard
    assert "Tests" in dashboard
    assert "jules" in dashboard
    assert "claude" in dashboard

def test_orchestrator_all_done(sample_tasks, config):
    """all_done returns True when every task is completed or failed."""
    orch = JulesOrchestrator(sample_tasks, config)
    assert orch.all_done() is False
    orch.mark_completed(1)
    orch.mark_completed(2)
    orch.mark_completed(3)
    assert orch.all_done() is True

def test_orchestrator_mark_failed(sample_tasks, config):
    """Failed tasks count as done but not completed."""
    orch = JulesOrchestrator(sample_tasks, config)
    orch.mark_failed(1, "API error")
    assert orch.task_states[1]["status"] == "FAILED"
    assert orch.task_states[1]["error"] == "API error"

def test_orchestrator_summary(sample_tasks, config):
    """Summary shows counts of completed, failed, etc."""
    orch = JulesOrchestrator(sample_tasks, config)
    orch.mark_completed(1)
    orch.mark_completed(3)
    orch.mark_failed(2, "error")
    summary = orch.render_summary()
    assert "2" in summary  # 2 completed
    assert "1" in summary  # 1 failed
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest jules/test_orchestrator.py -v`
Expected: FAIL — module doesn't exist.

**Step 3: Implement orchestrator.py**

```python
#!/usr/bin/env python3
# 1.0.0
"""
Jules orchestrator - Manages task queuing, concurrency, dashboard, and lifecycle.
"""


class JulesOrchestrator:
    """Orchestrates task execution across Jules and Claude."""

    def __init__(self, tasks, config):
        """
        Args:
            tasks: List of parsed task dicts from plan_parser.
            config: Config dict from load_config().
        """
        self.tasks = {t["number"]: t for t in tasks}
        self.config = config
        self.task_states = {}
        for t in tasks:
            self.task_states[t["number"]] = {
                "status": "QUEUED",
                "session_id": None,
                "session_url": None,
                "pr_url": None,
                "error": None,
            }

    def get_ready_tasks(self):
        """Get tasks whose dependencies are all completed.

        Returns:
            list[dict]: Tasks ready to launch.
        """
        ready = []
        for num, task in self.tasks.items():
            state = self.task_states[num]
            if state["status"] != "QUEUED":
                continue
            deps_met = all(
                self.task_states[d]["status"] in ("COMPLETED", "MERGED")
                for d in task["depends"]
                if d in self.task_states
            )
            if deps_met:
                ready.append(task)
        return sorted(ready, key=lambda t: t["number"])

    def get_launchable_tasks(self):
        """Get ready tasks limited by concurrency.

        Returns:
            list[dict]: Tasks to launch now.
        """
        active_count = sum(
            1 for s in self.task_states.values()
            if s["status"] in ("ACTIVE", "NEEDS_INPUT")
        )
        slots = self.config["max_concurrent_sessions"] - active_count
        if slots <= 0:
            return []
        ready = [t for t in self.get_ready_tasks() if t["executor"] == "jules"]
        return ready[:slots]

    def get_jules_tasks(self):
        """Get all tasks designated for Jules.

        Returns:
            list[dict]: Jules executor tasks.
        """
        return sorted(
            [t for t in self.tasks.values() if t["executor"] == "jules"],
            key=lambda t: t["number"]
        )

    def get_claude_tasks(self):
        """Get all tasks designated for Claude.

        Returns:
            list[dict]: Claude executor tasks.
        """
        return sorted(
            [t for t in self.tasks.values() if t["executor"] == "claude"],
            key=lambda t: t["number"]
        )

    def mark_active(self, task_number, session_id, session_url=None):
        """Mark a task as actively running."""
        self.task_states[task_number]["status"] = "ACTIVE"
        self.task_states[task_number]["session_id"] = session_id
        self.task_states[task_number]["session_url"] = session_url

    def mark_completed(self, task_number, pr_url=None):
        """Mark a task as completed."""
        self.task_states[task_number]["status"] = "COMPLETED"
        self.task_states[task_number]["pr_url"] = pr_url

    def mark_merged(self, task_number):
        """Mark a task as merged."""
        self.task_states[task_number]["status"] = "MERGED"

    def mark_failed(self, task_number, error):
        """Mark a task as failed."""
        self.task_states[task_number]["status"] = "FAILED"
        self.task_states[task_number]["error"] = error

    def mark_needs_input(self, task_number, question):
        """Mark a task as waiting for user input."""
        self.task_states[task_number]["status"] = "NEEDS_INPUT"
        self.task_states[task_number]["question"] = question

    def all_done(self):
        """Check if all tasks are in a terminal state.

        Returns:
            bool: True if all tasks completed, merged, or failed.
        """
        return all(
            s["status"] in ("COMPLETED", "MERGED", "FAILED")
            for s in self.task_states.values()
        )

    def render_dashboard(self):
        """Render a text dashboard of all tasks.

        Returns:
            str: Formatted dashboard table.
        """
        lines = []
        lines.append(f"{'Task':<6} {'Description':<30} {'Executor':<10} {'Status':<14} {'PR':<12}")
        lines.append("-" * 72)
        for num in sorted(self.tasks.keys()):
            task = self.tasks[num]
            state = self.task_states[num]
            pr = state.get("pr_url", "")
            if pr:
                # Extract PR number
                import re
                m = re.search(r"/pull/(\d+)", pr)
                pr_display = f"#{m.group(1)}" if m else pr
            else:
                pr_display = "-"
            lines.append(
                f"{num:<6} {task['title'][:30]:<30} {task['executor']:<10} "
                f"{state['status']:<14} {pr_display:<12}"
            )

        # Summary line
        active = sum(1 for s in self.task_states.values() if s["status"] in ("ACTIVE", "NEEDS_INPUT"))
        queued = sum(1 for s in self.task_states.values() if s["status"] == "QUEUED")
        completed = sum(1 for s in self.task_states.values() if s["status"] in ("COMPLETED", "MERGED"))
        failed = sum(1 for s in self.task_states.values() if s["status"] == "FAILED")
        lines.append("")
        lines.append(
            f"Active: {active}/{self.config['max_concurrent_sessions']} slots | "
            f"Queued: {queued} | Completed: {completed} | Failed: {failed}"
        )

        return "\n".join(lines)

    def render_summary(self):
        """Render final summary.

        Returns:
            str: Summary of completed/failed tasks.
        """
        completed = sum(1 for s in self.task_states.values() if s["status"] in ("COMPLETED", "MERGED"))
        failed = sum(1 for s in self.task_states.values() if s["status"] == "FAILED")
        total = len(self.task_states)

        lines = [
            "=" * 40,
            "EXECUTION COMPLETE",
            "=" * 40,
            f"Total tasks: {total}",
            f"Completed:   {completed}",
            f"Failed:      {failed}",
        ]

        if failed > 0:
            lines.append("")
            lines.append("Failed tasks:")
            for num, state in sorted(self.task_states.items()):
                if state["status"] == "FAILED":
                    lines.append(f"  Task {num}: {state['error']}")

        return "\n".join(lines)
```

**Step 4: Update `jules/__init__.py`**

```python
from jules.jules import JulesSession, JulesError, detect_github_repo, load_config
from jules.plan_parser import parse_plan
from jules.orchestrator import JulesOrchestrator
```

**Step 5: Run tests**

Run: `.venv/bin/python -m pytest jules/test_orchestrator.py -v`
Expected: All 8 tests PASS.

**Step 6: Commit**

```bash
git add jules/orchestrator.py jules/test_orchestrator.py jules/__init__.py
git commit --author="lunatic <lunatic@discord-bot>" -m "Feat: Add Jules orchestrator with concurrency, dashboard, and dependency management"
```

---

### Task 7: Create the /jules Claude Code skill

**Files:**
- Create: `~/.claude/skills/jules-executor/SKILL.md`

This skill ties everything together. It's a Markdown skill file that instructs Claude how to orchestrate Jules execution.

**Step 1: Create the skill directory**

```bash
mkdir -p ~/.claude/skills/jules-executor
```

**Step 2: Write SKILL.md**

Create `~/.claude/skills/jules-executor/SKILL.md`:

```markdown
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
```

**Step 3: Verify skill is discoverable**

Run: Start a new Claude Code session or use `/skills` to verify `jules-executor` appears.

**Step 4: Commit**

```bash
git add ~/.claude/skills/jules-executor/SKILL.md
git commit --author="lunatic <lunatic@discord-bot>" -m "Feat: Add /jules Claude Code skill for Jules-first development"
```

---

### Task 8: Update README and documentation

**Files:**
- Modify: `jules/README_JULES_CLI.md`

**Step 1: Update README**

Rewrite `jules/README_JULES_CLI.md` to cover both the library and CLI:

```markdown
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

Direct CLI usage (same commands as before):

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
```

**Step 2: Commit**

```bash
git add jules/README_JULES_CLI.md
git commit --author="lunatic <lunatic@discord-bot>" -m "Docs: Update Jules README with library, skill, and config docs"
```

---

### Task 9: Run full test suite and verify

**Step 1: Run all tests**

Run: `.venv/bin/python -m pytest jules/ -v`
Expected: All tests pass across all test files.

**Step 2: Run pylint**

Run: `.venv/bin/python -m pylint jules/jules.py jules/plan_parser.py jules/orchestrator.py jules/jules_cli.py`
Expected: Clean or only minor warnings.

**Step 3: Verify CLI still works**

Run: `.venv/bin/python jules/jules_cli.py --help`
Expected: Help text prints correctly.

**Step 4: Final commit if any fixes needed**

```bash
git commit --author="lunatic <lunatic@discord-bot>" -m "Fix: Address linting and test issues"
```
