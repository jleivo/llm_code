# Jules Auth Check + Session Listing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `auth_check()` and `list_sessions()` to the Jules library, and expose them as `auth`, `list`, and `states` subcommands in the CLI.

**Architecture:** Add two functions and a `VALID_STATES` constant to `jules/jules.py`, then wire them up as three new subcommands in `jules/jules_cli.py`. Follow existing TDD patterns: `test_jules.py` for library, `test_jules_cli.py` for CLI.

**Tech Stack:** Python 3, `requests`, `requests_mock` (tests), `pytest`

---

### Task 1: Add `VALID_STATES` and `auth_check()` to the library

**Files:**
- Modify: `jules/jules.py`
- Test: `jules/test_jules.py`

**Step 1: Write the failing tests**

Add to `jules/test_jules.py` (after the existing `load_config` tests):

```python
# --- auth_check tests ---

def test_auth_check_success(requests_mock):
    """auth_check returns ok dict when API key is valid."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions",
        json={"sessions": [{"id": "s1", "name": "projects/my-project/sessions/s1", "state": "CODING"}]}
    )
    from jules.jules import auth_check, JULES_API_BASE
    result = auth_check()
    assert result["status"] == "ok"
    assert result["endpoint"] == JULES_API_BASE
    assert "project" in result


def test_auth_check_extracts_project(requests_mock):
    """auth_check extracts project from session name when available."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions",
        json={"sessions": [{"id": "s1", "name": "projects/my-project/sessions/s1", "state": "CODING"}]}
    )
    from jules.jules import auth_check
    result = auth_check()
    assert result["project"] == "my-project"


def test_auth_check_unknown_project_when_no_sessions(requests_mock):
    """auth_check returns project=unknown when session list is empty."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions",
        json={"sessions": []}
    )
    from jules.jules import auth_check
    result = auth_check()
    assert result["project"] == "unknown"


def test_auth_check_failure(requests_mock):
    """auth_check raises JulesError on 401."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions",
        status_code=401,
        json={"error": {"message": "API key not valid"}}
    )
    from jules.jules import auth_check
    with pytest.raises(JulesError):
        auth_check()
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/juha/git/llm_code/.worktrees/jules-integration
source .venv/bin/activate
python -m pytest jules/test_jules.py::test_auth_check_success jules/test_jules.py::test_auth_check_extracts_project jules/test_jules.py::test_auth_check_unknown_project_when_no_sessions jules/test_jules.py::test_auth_check_failure -v
```

Expected: FAIL with `ImportError: cannot import name 'auth_check'`

**Step 3: Add `VALID_STATES` and `auth_check()` to `jules/jules.py`**

Add the `VALID_STATES` constant after the `DEFAULTS` dict (around line 23):

```python
VALID_STATES = (
    "STARTING",
    "WAITING_FOR_USER_RESPONSE",
    "CODING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
)
```

Add `auth_check()` as a module-level function after `get_github_token()` (before `detect_github_repo()`):

```python
def auth_check():
    """Verify API key works by making a minimal authenticated request.

    Returns:
        dict: {"status": "ok", "endpoint": str, "project": str}

    Raises:
        JulesError: If the API key is invalid or missing.
    """
    resp = _jules_request("GET", "sessions", params={"pageSize": 1})
    project = "unknown"
    sessions = (resp or {}).get("sessions", [])
    if sessions:
        name = sessions[0].get("name", "")
        parts = name.split("/")
        if len(parts) >= 2 and parts[0] == "projects":
            project = parts[1]
    return {"status": "ok", "endpoint": JULES_API_BASE, "project": project}
```

Note: `_jules_request` already raises `JulesError` on HTTP errors (including 401/403), so no additional error handling is needed here.

**Step 4: Run tests to verify they pass**

```bash
python -m pytest jules/test_jules.py::test_auth_check_success jules/test_jules.py::test_auth_check_extracts_project jules/test_jules.py::test_auth_check_unknown_project_when_no_sessions jules/test_jules.py::test_auth_check_failure -v
```

Expected: 4 PASSED

**Step 5: Run the full test suite to check for regressions**

```bash
python -m pytest jules/test_jules.py -v
```

Expected: all PASSED

**Step 6: Commit**

```bash
git add jules/jules.py jules/test_jules.py
git commit --author="lunatic <lunatic@discord-bot>" -m "feat: add VALID_STATES and auth_check() to Jules library"
```

---

### Task 2: Add `list_sessions()` to the library

**Files:**
- Modify: `jules/jules.py`
- Test: `jules/test_jules.py`

**Step 1: Write the failing tests**

Add to `jules/test_jules.py` (after the `auth_check` tests):

```python
# --- list_sessions tests ---

def test_list_sessions_all(requests_mock):
    """list_sessions returns all sessions when no filter given."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions",
        json={
            "sessions": [
                {"id": "s1", "state": "CODING", "title": "Fix bug", "url": "https://jules.google.com/s1", "createTime": "2026-03-09T10:00:00Z"},
                {"id": "s2", "state": "COMPLETED", "title": "Add tests", "url": "https://jules.google.com/s2", "createTime": "2026-03-09T09:00:00Z"},
            ]
        }
    )
    from jules.jules import list_sessions
    result = list_sessions()
    assert len(result) == 2
    assert result[0]["id"] == "s1"
    assert result[1]["id"] == "s2"


def test_list_sessions_filtered(requests_mock):
    """list_sessions filters by state when state_filter is given."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions",
        json={
            "sessions": [
                {"id": "s1", "state": "CODING", "title": "Fix bug"},
                {"id": "s2", "state": "COMPLETED", "title": "Add tests"},
                {"id": "s3", "state": "CODING", "title": "Refactor"},
            ]
        }
    )
    from jules.jules import list_sessions
    result = list_sessions(state_filter="CODING")
    assert len(result) == 2
    assert all(s["state"] == "CODING" for s in result)


def test_list_sessions_filter_case_insensitive(requests_mock):
    """list_sessions filter is case-insensitive."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions",
        json={"sessions": [{"id": "s1", "state": "CODING", "title": "Fix bug"}]}
    )
    from jules.jules import list_sessions
    result = list_sessions(state_filter="coding")
    assert len(result) == 1


def test_list_sessions_pagination(requests_mock):
    """list_sessions handles pagination."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions?pageSize=50",
        json={"sessions": [{"id": "s1", "state": "CODING"}], "nextPageToken": "tok1"}
    )
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions?pageSize=50&pageToken=tok1",
        json={"sessions": [{"id": "s2", "state": "COMPLETED"}]}
    )
    from jules.jules import list_sessions
    result = list_sessions()
    assert len(result) == 2
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest jules/test_jules.py::test_list_sessions_all jules/test_jules.py::test_list_sessions_filtered jules/test_jules.py::test_list_sessions_filter_case_insensitive jules/test_jules.py::test_list_sessions_pagination -v
```

Expected: FAIL with `ImportError: cannot import name 'list_sessions'`

**Step 3: Add `list_sessions()` to `jules/jules.py`**

Add after `auth_check()`:

```python
def list_sessions(state_filter=None, page_size=50):
    """List all Jules sessions, optionally filtered by state.

    Args:
        state_filter: If given, only return sessions with this state (case-insensitive).
        page_size: Number of sessions per page.

    Returns:
        list: Session dicts with keys: id, state, title, url, createTime.
    """
    sessions = []
    page_token = None
    while True:
        params = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        resp = _jules_request("GET", "sessions", params=params)
        if not resp:
            break
        sessions.extend(resp.get("sessions", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    if state_filter:
        sessions = [s for s in sessions if s.get("state", "").upper() == state_filter.upper()]
    return sessions
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest jules/test_jules.py::test_list_sessions_all jules/test_jules.py::test_list_sessions_filtered jules/test_jules.py::test_list_sessions_filter_case_insensitive jules/test_jules.py::test_list_sessions_pagination -v
```

Expected: 4 PASSED

**Step 5: Run the full test suite**

```bash
python -m pytest jules/test_jules.py -v
```

Expected: all PASSED

**Step 6: Commit**

```bash
git add jules/jules.py jules/test_jules.py
git commit --author="lunatic <lunatic@discord-bot>" -m "feat: add list_sessions() to Jules library"
```

---

### Task 3: Add `auth`, `list`, and `states` CLI subcommands

**Files:**
- Modify: `jules/jules_cli.py`
- Test: `jules/test_jules_cli.py`

**Step 1: Write the failing tests**

Add to `jules/test_jules_cli.py`:

```python
def test_cli_auth_success(capsys):
    """CLI auth command prints OK with endpoint and project on success."""
    with patch("jules_cli.auth_check", return_value={"status": "ok", "endpoint": "https://jules.googleapis.com/v1alpha", "project": "my-project"}):
        with patch("sys.argv", ["jules_cli.py", "auth"]):
            main()
    captured = capsys.readouterr()
    assert "Authentication OK" in captured.out
    assert "my-project" in captured.out
    assert "https://jules.googleapis.com/v1alpha" in captured.out


def test_cli_auth_failure(capsys):
    """CLI auth command prints failure message and exits 1 on JulesError."""
    from jules import JulesError
    with patch("jules_cli.auth_check", side_effect=JulesError("Invalid or missing API key")):
        with patch("sys.argv", ["jules_cli.py", "auth"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Authentication failed" in captured.out


def test_cli_list_all(capsys):
    """CLI list command prints all sessions."""
    sessions = [
        {"id": "s1", "state": "CODING", "title": "Fix bug", "url": "https://jules.google.com/s1", "createTime": "2026-03-09T10:00:00Z"},
        {"id": "s2", "state": "COMPLETED", "title": "Add tests", "url": "https://jules.google.com/s2", "createTime": "2026-03-09T09:00:00Z"},
    ]
    with patch("jules_cli.list_sessions", return_value=sessions):
        with patch("sys.argv", ["jules_cli.py", "list"]):
            main()
    captured = capsys.readouterr()
    assert "s1" in captured.out
    assert "CODING" in captured.out
    assert "Fix bug" in captured.out
    assert "s2" in captured.out


def test_cli_list_filtered(capsys):
    """CLI list --state passes filter to list_sessions."""
    with patch("jules_cli.list_sessions", return_value=[]) as mock_list:
        with patch("sys.argv", ["jules_cli.py", "list", "--state", "CODING"]):
            main()
    mock_list.assert_called_once_with(state_filter="CODING")


def test_cli_list_invalid_state(capsys):
    """CLI list --state with unknown state prints a warning."""
    with patch("jules_cli.list_sessions", return_value=[]):
        with patch("sys.argv", ["jules_cli.py", "list", "--state", "BOGUS"]):
            main()
    captured = capsys.readouterr()
    assert "states" in captured.out.lower() or "valid" in captured.out.lower()


def test_cli_list_empty(capsys):
    """CLI list prints a message when no sessions found."""
    with patch("jules_cli.list_sessions", return_value=[]):
        with patch("sys.argv", ["jules_cli.py", "list"]):
            main()
    captured = capsys.readouterr()
    assert "No sessions" in captured.out or "no sessions" in captured.out.lower()


def test_cli_states(capsys):
    """CLI states command prints all valid states."""
    with patch("sys.argv", ["jules_cli.py", "states"]):
        main()
    captured = capsys.readouterr()
    assert "CODING" in captured.out
    assert "COMPLETED" in captured.out
    assert "FAILED" in captured.out
    assert "STARTING" in captured.out
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest jules/test_jules_cli.py::test_cli_auth_success jules/test_jules_cli.py::test_cli_auth_failure jules/test_jules_cli.py::test_cli_list_all jules/test_jules_cli.py::test_cli_list_filtered jules/test_jules_cli.py::test_cli_list_invalid_state jules/test_jules_cli.py::test_cli_list_empty jules/test_jules_cli.py::test_cli_states -v
```

Expected: FAIL (import errors or argument parse errors)

**Step 3: Update `jules/jules_cli.py`**

Add the new imports at the top (after the existing `from jules import JulesSession, JulesError` line):

```python
from jules import JulesSession, JulesError, auth_check, list_sessions, VALID_STATES
```

Add three subcommand parsers inside `main()`, after the existing `merge` subparser (before `args = parser.parse_args()`):

```python
    subparsers.add_parser("auth", help="Check authentication and display identity info")

    list_parser = subparsers.add_parser("list", help="List Jules sessions")
    list_parser.add_argument("--state", help="Filter by session state (see 'states' command)")

    subparsers.add_parser("states", help="List valid session states")
```

Add the three command handlers in the `if/elif` chain inside `main()`, after the `merge` block (before the `else`):

```python
        elif args.command == "auth":
            result = auth_check()
            print("Authentication OK")
            print(f"  API endpoint: {result['endpoint']}")
            print(f"  Project: {result['project']}")

        elif args.command == "list":
            state_filter = getattr(args, "state", None)
            if state_filter and state_filter.upper() not in VALID_STATES:
                print(f"Warning: '{state_filter}' is not a known state. Run 'states' to see valid values.")
            sessions = list_sessions(state_filter=state_filter)
            if not sessions:
                print("No sessions found.")
            else:
                print(f"{'ID':<20} {'State':<30} {'Title'}")
                print("-" * 70)
                for s in sessions:
                    print(f"{s.get('id', ''):<20} {s.get('state', ''):<30} {s.get('title', '')}")

        elif args.command == "states":
            print("Valid session states:")
            for state in VALID_STATES:
                print(f"  {state}")
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest jules/test_jules_cli.py::test_cli_auth_success jules/test_jules_cli.py::test_cli_auth_failure jules/test_jules_cli.py::test_cli_list_all jules/test_jules_cli.py::test_cli_list_filtered jules/test_jules_cli.py::test_cli_list_invalid_state jules/test_jules_cli.py::test_cli_list_empty jules/test_jules_cli.py::test_cli_states -v
```

Expected: 7 PASSED

**Step 5: Run the full test suite**

```bash
python -m pytest jules/ -v
```

Expected: all PASSED

**Step 6: Commit**

```bash
git add jules/jules_cli.py jules/test_jules_cli.py
git commit --author="lunatic <lunatic@discord-bot>" -m "feat: add auth, list, and states CLI subcommands"
```
