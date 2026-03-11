#!/usr/bin/env python3
# 1.0.0
"""
Plan execution runner - Entry point for dispatching implementation plans to Jules.

Usage:
    # Interactive: runs full loop until all tasks done
    python3 run_plan.py <plan-file>

    # Poll-once: loads state, polls, updates, exits (for cron/loop)
    python3 run_plan.py <plan-file> --poll-once --state-file /tmp/jules_state.json
"""

import argparse
import json
import os
import sys
import time

# Allow running as script from the scripts/ directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jules import JulesSession, JulesError, load_config, detect_github_repo, detect_current_branch
from plan_parser import parse_plan
from orchestrator import JulesOrchestrator


def load_state(state_file):
    """Load execution state from a JSON file."""
    if not os.path.exists(state_file):
        return None
    with open(state_file, "r") as f:
        return json.load(f)


def save_state(state_file, orchestrator, sessions, plan_file, config):
    """Save execution state to a JSON file."""
    state = {
        "sessions": {
            str(k): {"session_id": v.session_id, "session_url": v.url}
            for k, v in sessions.items()
        },
        "task_states": {str(k): v for k, v in orchestrator.task_states.items()},
        "plan_file": plan_file,
        "config": {k: v for k, v in config.items()},
    }
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def restore_orchestrator(state, tasks, config):
    """Restore an orchestrator and sessions from saved state."""
    orch = JulesOrchestrator(tasks, config)
    for num_str, ts in state["task_states"].items():
        num = int(num_str)
        if num in orch.task_states:
            orch.task_states[num] = ts

    sessions = {}
    for num_str, sdata in state.get("sessions", {}).items():
        num = int(num_str)
        sessions[num] = JulesSession(
            session_id=sdata["session_id"],
            url=sdata.get("session_url"),
        )
    return orch, sessions


def launch_task(task, owner, repo, branch):
    """Create a Jules session for a task."""
    prompt = f"Task {task['number']}: {task['title']}\n\n{task['body']}"
    session = JulesSession.create(
        prompt=prompt,
        title=f"Task {task['number']}: {task['title']}",
        owner=owner,
        repo=repo,
        branch=branch,
    )
    print(f"  Launched task {task['number']}: session {session.session_id}")
    return session


def poll_sessions(orchestrator, sessions, config):
    """Poll all active sessions and update orchestrator state."""
    for num, session in list(sessions.items()):
        state = orchestrator.task_states[num]
        if state["status"] not in ("ACTIVE", "NEEDS_INPUT"):
            continue

        try:
            session_state = session.status()
        except JulesError as e:
            print(f"  Task {num}: poll error — {e}")
            continue

        if session_state == "COMPLETED":
            pr_url = session.get_pr_url()
            orchestrator.mark_completed(num, pr_url=pr_url)
            print(f"  Task {num}: COMPLETED (PR: {pr_url or 'none'})")

            if pr_url and config.get("auto_merge"):
                try:
                    session.merge_pr()
                    orchestrator.mark_merged(num)
                    print(f"  Task {num}: PR merged")
                except JulesError as e:
                    print(f"  Task {num}: merge failed — {e}")

        elif session_state == "FAILED":
            orchestrator.mark_failed(num, "Session failed")
            print(f"  Task {num}: FAILED")

        elif session_state == "WAITING_FOR_USER_RESPONSE":
            question = session.get_latest_question()
            if question:
                orchestrator.mark_needs_input(num, question)
                print(f"  Task {num}: NEEDS INPUT — {question[:80]}")

        elif session_state == "CANCELLED":
            orchestrator.mark_failed(num, "Session cancelled")
            print(f"  Task {num}: CANCELLED")


def run_interactive(plan_file, config):
    """Run full interactive loop until all tasks complete."""
    with open(plan_file, "r") as f:
        content = f.read()

    tasks = parse_plan(content, default_executor=config.get("default_executor", "jules"))
    if not tasks:
        print("No tasks found in plan file.")
        return

    orchestrator = JulesOrchestrator(tasks, config)
    sessions = {}

    owner, repo = detect_github_repo()
    branch = detect_current_branch()
    print(f"Repo: {owner}/{repo} Branch: {branch}")
    print(f"Tasks: {len(tasks)}, Max concurrent: {config['max_concurrent_sessions']}")
    print()

    while not orchestrator.all_done():
        # Launch new tasks
        launchable = orchestrator.get_launchable_tasks()
        for task in launchable:
            try:
                session = launch_task(task, owner, repo, branch)
                sessions[task["number"]] = session
                orchestrator.mark_active(task["number"], session.session_id, session.url)
            except JulesError as e:
                orchestrator.mark_failed(task["number"], str(e))
                print(f"  Task {task['number']}: launch failed — {e}")

        # Poll active sessions
        poll_sessions(orchestrator, sessions, config)

        # Print dashboard
        print()
        print(orchestrator.render_dashboard())
        print()

        if orchestrator.all_done():
            break

        interval = config.get("poll_interval_seconds", 30)
        print(f"Next poll in {interval}s...")
        time.sleep(interval)

    print()
    print(orchestrator.render_summary())


def run_poll_once(plan_file, state_file, config):
    """Single poll cycle: load state, poll, update, save, exit."""
    with open(plan_file, "r") as f:
        content = f.read()

    tasks = parse_plan(content, default_executor=config.get("default_executor", "jules"))
    if not tasks:
        print("No tasks found in plan file.")
        return

    saved = load_state(state_file)
    if saved:
        orchestrator, sessions = restore_orchestrator(saved, tasks, config)
        print("Restored state from", state_file)
    else:
        orchestrator = JulesOrchestrator(tasks, config)
        sessions = {}
        print("Fresh start — no existing state file.")

    owner, repo = detect_github_repo()
    branch = detect_current_branch()

    # Poll active sessions
    poll_sessions(orchestrator, sessions, config)

    # Launch new tasks if slots available
    launchable = orchestrator.get_launchable_tasks()
    for task in launchable:
        try:
            session = launch_task(task, owner, repo, branch)
            sessions[task["number"]] = session
            orchestrator.mark_active(task["number"], session.session_id, session.url)
        except JulesError as e:
            orchestrator.mark_failed(task["number"], str(e))
            print(f"  Task {task['number']}: launch failed — {e}")

    # Print dashboard
    print()
    print(orchestrator.render_dashboard())

    if orchestrator.all_done():
        print()
        print(orchestrator.render_summary())
    else:
        # Save state for next poll
        save_state(state_file, orchestrator, sessions, plan_file, config)
        print(f"\nState saved to {state_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Execute an implementation plan via Jules sessions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("plan_file", help="Path to the markdown plan file")
    parser.add_argument(
        "--poll-once",
        action="store_true",
        help="Single poll cycle (for cron/loop usage)",
    )
    parser.add_argument(
        "--state-file",
        default="/tmp/jules_state.json",
        help="Path to state file (default: /tmp/jules_state.json)",
    )
    parser.add_argument(
        "--config",
        help="Path to jules_config.ini (default: auto-detect)",
    )

    args = parser.parse_args()

    config_path = args.config
    config = load_config(config_path)

    if args.poll_once:
        run_poll_once(args.plan_file, args.state_file, config)
    else:
        run_interactive(args.plan_file, config)


if __name__ == "__main__":
    main()
