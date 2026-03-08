#!/usr/bin/env python3
"""
Jules CLI - A tool for collaborating with the Jules AI agent.
Allows Openclaw or other agentic systems to interact with jules.google.com.
"""

import argparse
import json
import os
import sys
import time
import requests
import re

JULES_API_BASE = "https://jules.googleapis.com/v1alpha"
FIXED_REPO = "sources/github-jleivo-Claw_jules_collaboration"
DEFAULT_BRANCH = "master"

def get_jules_api_key():
    """Retrieves the Jules API key from a file."""
    # This function is designed to be easily updated to retrieve keys from
    # Hashicorp Vault or other secret managers in the future.
    try:
        with open("jules_api_key.txt", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        print("Error: jules_api_key.txt not found.")
        print("Please create this file and paste your Jules API key into it.")
        sys.exit(1)

def get_github_token():
    """Retrieves the GitHub token from a file or environment variable."""
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return token
    try:
        with open("github_token.txt", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

def jules_request(method, endpoint, data=None, params=None):
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
        print(f"API Error: {e}")
        if e.response is not None:
            print(f"Response: {e.response.text}")
        sys.exit(1)

def create_session(prompt, title=None):
    """Creates a new Jules session."""
    data = {
        "prompt": prompt,
        "title": title or "Task via Jules CLI",
        "sourceContext": {
            "source": FIXED_REPO,
            "githubRepoContext": {
                "startingBranch": DEFAULT_BRANCH
            }
        },
        "requirePlanApproval": False, # Setting to False for more autonomous workflow
        "automationMode": "AUTO_CREATE_PR"
    }
    return jules_request("POST", "sessions", data=data)

def get_session(session_id):
    """Retrieves session details."""
    return jules_request("GET", f"sessions/{session_id}")

def send_message(session_id, prompt):
    """Sends a message to an active session."""
    data = {"prompt": prompt}
    return jules_request("POST", f"sessions/{session_id}:sendMessage", data=data)

def list_activities(session_id, page_size=50, page_token=None):
    """Lists activities for a session."""
    params = {"pageSize": page_size}
    if page_token:
        params["pageToken"] = page_token
    return jules_request("GET", f"sessions/{session_id}/activities", params=params)

def get_all_activities(session_id):
    """Retrieves all activities handling pagination."""
    activities = []
    page_token = None
    while True:
        resp = list_activities(session_id, page_token=page_token)
        if not resp:
            break
        activities.extend(resp.get("activities", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return activities

def poll_status(session_id):
    """Polls the session status and prints latest updates."""
    session = get_session(session_id)
    print(f"Session State: {session.get('state')}")

    activities = get_all_activities(session_id)
    if activities:
        # Show the last 5 activities
        last_activities = activities[-5:]
        for act in last_activities:
            originator = act.get("originator", "system")
            description = act.get("description", "")
            print(f"[{originator.upper()}] {description}")

            # Check for agent messages
            if "agentMessaged" in act:
                print(f"  Message: {act['agentMessaged'].get('agentMessage')}")

            # Check for failure reason
            if "sessionFailed" in act:
                print(f"  Failure Reason: {act['sessionFailed'].get('reason')}")

    if session.get("state") == "COMPLETED":
        if "outputs" in session:
            for output in session["outputs"]:
                if "pullRequest" in output:
                    pr = output["pullRequest"]
                    print(f"\nWork completed! PR Created: {pr.get('url')}")

    return session

def github_merge_pr(pr_url):
    """Merges a Pull Request using the GitHub API."""
    token = get_github_token()
    if not token:
        print("Error: GitHub token not found. Set GITHUB_TOKEN env var or create github_token.txt.")
        print("To create a token with minimal permissions:")
        print("1. Go to GitHub -> Settings -> Developer settings -> Personal access tokens -> Fine-grained tokens.")
        print("2. Generate new token.")
        print("3. Repository access: Only select 'jleivo/Claw_jules_collaboration'.")
        print("4. Permissions: Repository permissions -> Pull requests: Read and write.")
        sys.exit(1)

    # Extract owner, repo, and PR number from URL
    match = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
    if not match:
        print(f"Error: Could not parse PR URL: {pr_url}")
        return

    owner, repo, pr_number = match.groups()
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/merge"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    response = requests.put(url, headers=headers)
    if response.status_code == 200:
        print("Successfully merged PR!")
    else:
        print(f"Failed to merge PR: {response.status_code}")
        print(response.text)

def chat_repl(session_id):
    """Starts an interactive REPL loop with Jules."""
    print(f"Entering chat with session {session_id}. Type 'exit' or 'quit' to leave.")

    # Track the last seen activity ID to avoid printing old messages
    activities = get_all_activities(session_id)
    last_seen_activity_id = activities[-1]["id"] if activities else None

    while True:
        try:
            user_input = input("You > ")
            if user_input.lower() in ["exit", "quit"]:
                break
            if not user_input.strip():
                continue

            send_message(session_id, user_input)
            print("Message sent. Waiting for response...")

            # Simple polling loop to wait for agent response
            found_response = False
            for _ in range(60): # Wait up to 120 seconds
                time.sleep(2)
                activities_resp = get_all_activities(session_id)
                if activities_resp:
                    new_activities = []
                    if last_seen_activity_id is None:
                        new_activities = activities_resp
                    else:
                        found_last_seen = False
                        for act in activities_resp:
                            if found_last_seen:
                                new_activities.append(act)
                            elif act["id"] == last_seen_activity_id:
                                found_last_seen = True

                    for act in new_activities:
                        last_seen_activity_id = act["id"]
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

Note: Requires jules_api_key.txt for all commands and github_token.txt for 'merge'.
"""
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new Jules session")
    create_parser.add_argument("--prompt", required=True, help="The task for Jules")
    create_parser.add_argument("--title", help="Optional title for the session")

    # Chat command
    chat_parser = subparsers.add_parser("chat", help="Start a REPL with an active session")
    chat_parser.add_argument("--session-id", required=True, help="The session ID")

    # Status command
    status_parser = subparsers.add_parser("status", help="Check session status")
    status_parser.add_argument("--session-id", required=True, help="The session ID")

    # Merge command
    merge_parser = subparsers.add_parser("merge", help="Merge the PR associated with a completed session")
    merge_parser.add_argument("--session-id", required=True, help="The session ID")

    args = parser.parse_args()

    if args.command == "create":
        session = create_session(args.prompt, args.title)
        print(f"Session created! ID: {session['id']}")
        print(f"URL: {session['url']}")

    elif args.command == "chat":
        chat_repl(args.session_id)

    elif args.command == "status":
        poll_status(args.session_id)

    elif args.command == "merge":
        session = get_session(args.session_id)
        if session.get("state") != "COMPLETED":
            print(f"Cannot merge. Session state is {session.get('state')}, not COMPLETED.")
            return

        pr_url = None
        if "outputs" in session:
            for output in session["outputs"]:
                if "pullRequest" in output:
                    pr_url = output["pullRequest"].get("url")
                    break

        if pr_url:
            github_merge_pr(pr_url)
        else:
            print("Error: No PR URL found in session outputs.")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
