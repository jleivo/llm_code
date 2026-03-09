import pytest
import subprocess
from unittest.mock import patch, MagicMock
from jules import JulesSession, JulesError, detect_github_repo, auth_check, list_sessions, VALID_STATES
from jules.jules import JULES_API_BASE

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


# --- load_config tests ---

def test_load_config_defaults():
    """Load config returns defaults when no file exists."""
    from jules.jules import load_config
    import os

    # Use a non-existent path
    config = load_config("/nonexistent/path/config.ini")
    assert config["max_concurrent_sessions"] == 3
    assert config["poll_interval_seconds"] == 30
    assert config["default_executor"] == "jules"
    assert config["auto_merge"] is True


def test_load_config_custom(tmp_path):
    """Load config reads custom values from file."""
    from jules.jules import load_config

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


# --- auth_check tests ---

def test_auth_check_success(requests_mock):
    """auth_check returns ok dict with correct keys and sends pageSize=1."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions",
        json={"sessions": []}
    )
    result = auth_check()
    assert result["status"] == "ok"
    assert result["endpoint"] == JULES_API_BASE
    assert "project" in result
    assert requests_mock.last_request.qs == {"pagesize": ["1"]}


def test_auth_check_extracts_project(requests_mock):
    """auth_check extracts project from session name when available."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions",
        json={"sessions": [{"id": "s1", "name": "projects/my-project/sessions/s1", "state": "CODING"}]}
    )
    result = auth_check()
    assert result["project"] == "my-project"


def test_auth_check_unknown_project_when_no_sessions(requests_mock):
    """auth_check returns project=unknown when session list is empty."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions",
        json={"sessions": []}
    )
    result = auth_check()
    assert result["project"] == "unknown"


def test_auth_check_failure(requests_mock):
    """auth_check raises JulesError on 401."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions",
        status_code=401,
        json={"error": {"message": "API key not valid"}}
    )
    with pytest.raises(JulesError):
        auth_check()


# --- list_sessions tests ---

def test_list_sessions_all(requests_mock):
    """list_sessions returns all sessions across states when no filter given."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions",
        json={
            "sessions": [
                {"id": "s1", "state": "CODING", "title": "Fix bug", "url": "https://jules.google.com/s1", "createTime": "2026-03-09T10:00:00Z"},
                {"id": "s2", "state": "COMPLETED", "title": "Add tests", "url": "https://jules.google.com/s2", "createTime": "2026-03-09T09:00:00Z"},
            ]
        }
    )
    result = list_sessions()
    assert len(result) == 2
    assert result[0]["id"] == "s1"
    assert result[1]["id"] == "s2"
    assert {r["state"] for r in result} == {"CODING", "COMPLETED"}


def test_list_sessions_empty(requests_mock):
    """list_sessions returns empty list when no sessions exist."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions",
        json={"sessions": []}
    )
    result = list_sessions()
    assert result == []


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
    result = list_sessions(state_filter="CODING")
    assert len(result) == 2
    assert all(s["state"] == "CODING" for s in result)


def test_list_sessions_filter_case_insensitive(requests_mock):
    """list_sessions filter is case-insensitive."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions",
        json={"sessions": [{"id": "s1", "state": "CODING", "title": "Fix bug"}]}
    )
    result = list_sessions(state_filter="coding")
    assert len(result) == 1
    assert result[0]["state"] == "CODING"


def test_list_sessions_pagination(requests_mock):
    """list_sessions handles pagination and combines results from all pages."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions?pageSize=50",
        json={"sessions": [{"id": "s1", "state": "CODING"}], "nextPageToken": "tok1"}
    )
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions?pageSize=50&pageToken=tok1",
        json={"sessions": [{"id": "s2", "state": "COMPLETED"}]}
    )
    result = list_sessions()
    assert len(result) == 2
    assert result[0]["id"] == "s1"
    assert result[1]["id"] == "s2"


def test_list_sessions_pagination_with_filter(requests_mock):
    """list_sessions applies filter after collecting all pages."""
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions?pageSize=50",
        json={"sessions": [{"id": "s1", "state": "CODING"}], "nextPageToken": "tok1"}
    )
    requests_mock.get(
        "https://jules.googleapis.com/v1alpha/sessions?pageSize=50&pageToken=tok1",
        json={"sessions": [{"id": "s2", "state": "COMPLETED"}, {"id": "s3", "state": "CODING"}]}
    )
    result = list_sessions(state_filter="CODING")
    assert len(result) == 2
    assert all(s["state"] == "CODING" for s in result)
