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
    """Detect the current git branch."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def _jules_request(method, endpoint, data=None, params=None):
    """Makes a request to the Jules API."""
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
        """Create a new Jules session."""
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
        """Get the current session state."""
        resp = _jules_request("GET", f"sessions/{self.session_id}")
        return resp.get("state")

    def get_session_data(self):
        """Get full session data."""
        return _jules_request("GET", f"sessions/{self.session_id}")

    def send_message(self, prompt):
        """Send a message to the session."""
        data = {"prompt": prompt}
        _jules_request("POST", f"sessions/{self.session_id}:sendMessage", data=data)

    def get_activities(self, page_size=50):
        """Get all activities for this session, handling pagination."""
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
        """Get activities since last check."""
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
        """Check if Jules has asked a question."""
        activities = self.get_activities()
        for act in reversed(activities):
            if act.get("originator") == "agent" and "agentMessaged" in act:
                return act["agentMessaged"].get("agentMessage")
        return None

    def get_pr_url(self):
        """Get the PR URL from a completed session."""
        data = self.get_session_data()
        for output in data.get("outputs", []):
            if "pullRequest" in output:
                return output["pullRequest"].get("url")
        return None

    def merge_pr(self):
        """Merge the PR created by this session."""
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
