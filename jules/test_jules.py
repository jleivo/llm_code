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
