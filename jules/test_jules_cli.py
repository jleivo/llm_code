import pytest
import requests_mock
from jules_cli import create_session, get_session, list_activities, FIXED_REPO, JULES_API_BASE, get_all_activities
import os
import json

# Mock the API key file
@pytest.fixture(autouse=True)
def mock_api_key(monkeypatch):
    def mock_get_key():
        return "fake-api-key"
    monkeypatch.setattr("jules_cli.get_jules_api_key", mock_get_key)

def test_create_session(requests_mock):
    mock_response = {
        "id": "session-123",
        "name": "sessions/session-123",
        "url": "https://jules.google.com/session/session-123"
    }
    requests_mock.post(f"{JULES_API_BASE}/sessions", json=mock_response)

    result = create_session("Test prompt", "Test title")

    assert result["id"] == "session-123"
    assert requests_mock.called
    history = requests_mock.request_history[0]
    assert history.json()["prompt"] == "Test prompt"
    assert history.json()["sourceContext"]["source"] == FIXED_REPO

def test_get_session(requests_mock):
    mock_response = {
        "id": "session-123",
        "state": "COMPLETED",
        "outputs": [
            {
                "pullRequest": {"url": "https://github.com/jleivo/repo/pull/1"}
            }
        ]
    }
    requests_mock.get(f"{JULES_API_BASE}/sessions/session-123", json=mock_response)

    result = get_session("session-123")
    assert result["state"] == "COMPLETED"
    assert result["outputs"][0]["pullRequest"]["url"] == "https://github.com/jleivo/repo/pull/1"

def test_get_all_activities_pagination(requests_mock):
    # Page 1
    requests_mock.get(
        f"{JULES_API_BASE}/sessions/session-123/activities?pageSize=50",
        json={
            "activities": [{"id": "act1"}],
            "nextPageToken": "token1"
        }
    )
    # Page 2
    requests_mock.get(
        f"{JULES_API_BASE}/sessions/session-123/activities?pageSize=50&pageToken=token1",
        json={
            "activities": [{"id": "act2"}]
        }
    )

    activities = get_all_activities("session-123")
    assert len(activities) == 2
    assert activities[0]["id"] == "act1"
    assert activities[1]["id"] == "act2"

def test_github_merge_pr(requests_mock, monkeypatch):
    monkeypatch.setattr("jules_cli.get_github_token", lambda: "fake-token")

    pr_url = "https://github.com/jleivo/Claw_jules_collaboration/pull/123"
    requests_mock.put("https://api.github.com/repos/jleivo/Claw_jules_collaboration/pulls/123/merge", status_code=200)

    from jules_cli import github_merge_pr
    github_merge_pr(pr_url)

    assert requests_mock.called
    assert requests_mock.request_history[0].url == "https://api.github.com/repos/jleivo/Claw_jules_collaboration/pulls/123/merge"
    assert requests_mock.request_history[0].method == "PUT"
