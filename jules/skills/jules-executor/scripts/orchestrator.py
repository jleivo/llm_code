#!/usr/bin/env python3
# 1.0.0
"""
Jules orchestrator - Manages task queuing, concurrency, dashboard, and lifecycle.
"""
import re


class JulesOrchestrator:
    """Orchestrates task execution across Jules and Claude."""

    def __init__(self, tasks, config):
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
        """Get tasks whose dependencies are all completed."""
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
        """Get ready Jules tasks limited by concurrency."""
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
        """Get all tasks designated for Jules."""
        return sorted(
            [t for t in self.tasks.values() if t["executor"] == "jules"],
            key=lambda t: t["number"]
        )

    def get_claude_tasks(self):
        """Get all tasks designated for Claude."""
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
        """Check if all tasks are in a terminal state."""
        return all(
            s["status"] in ("COMPLETED", "MERGED", "FAILED")
            for s in self.task_states.values()
        )

    def render_dashboard(self):
        """Render a text dashboard of all tasks."""
        lines = []
        lines.append(f"{'Task':<6} {'Description':<30} {'Executor':<10} {'Status':<14} {'PR':<12}")
        lines.append("-" * 72)
        for num in sorted(self.tasks.keys()):
            task = self.tasks[num]
            state = self.task_states[num]
            pr = state.get("pr_url", "")
            if pr:
                m = re.search(r"/pull/(\d+)", pr)
                pr_display = f"#{m.group(1)}" if m else pr
            else:
                pr_display = "-"
            lines.append(
                f"{num:<6} {task['title'][:30]:<30} {task['executor']:<10} "
                f"{state['status']:<14} {pr_display:<12}"
            )

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
        """Render final summary."""
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
