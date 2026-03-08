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
