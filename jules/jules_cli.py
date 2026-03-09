#!/usr/bin/env python3
# 1.0.0
"""
Jules CLI - Command-line wrapper for the Jules AI agent library.
"""

import argparse
import sys
import time
from jules import JulesSession, JulesError, auth_check, list_sessions, VALID_STATES


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

    subparsers.add_parser("chat", help="Start a REPL with an active session").add_argument(
        "--session-id", required=True, help="The session ID"
    )

    subparsers.add_parser("status", help="Check session status").add_argument(
        "--session-id", required=True, help="The session ID"
    )

    subparsers.add_parser("merge", help="Merge the PR from a completed session").add_argument(
        "--session-id", required=True, help="The session ID"
    )

    subparsers.add_parser("auth", help="Check authentication and display identity info")

    list_parser = subparsers.add_parser("list", help="List Jules sessions")
    list_parser.add_argument("--state", help="Filter by session state (see 'states' command)")

    subparsers.add_parser("states", help="List valid session states")

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

        elif args.command == "auth":
            result = auth_check()
            print("Authentication OK")
            print(f"  API endpoint: {result['endpoint']}")
            print(f"  Project: {result['project']}")

        elif args.command == "list":
            state_filter = args.state
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

        else:
            parser.print_help()

    except JulesError as e:
        prefix = "Authentication failed" if args.command == "auth" else "Error"
        print(f"{prefix}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
