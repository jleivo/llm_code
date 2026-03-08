import pytest
from jules.orchestrator import JulesOrchestrator

@pytest.fixture
def sample_tasks():
    return [
        {"number": 1, "title": "Auth", "executor": "jules", "depends": [], "body": "Add JWT auth"},
        {"number": 2, "title": "Config", "executor": "claude", "depends": [1], "body": "Update config"},
        {"number": 3, "title": "Tests", "executor": "jules", "depends": [], "body": "Write tests"},
    ]

@pytest.fixture
def config():
    return {
        "max_concurrent_sessions": 2,
        "poll_interval_seconds": 1,
        "default_executor": "jules",
        "auto_merge": True,
    }

def test_orchestrator_identifies_ready_tasks(sample_tasks, config):
    """Tasks with no unresolved dependencies are ready."""
    orch = JulesOrchestrator(sample_tasks, config)
    ready = orch.get_ready_tasks()
    assert [t["number"] for t in ready] == [1, 3]

def test_orchestrator_respects_concurrency(sample_tasks, config):
    """Don't launch more than max_concurrent_sessions."""
    config["max_concurrent_sessions"] = 1
    orch = JulesOrchestrator(sample_tasks, config)
    ready = orch.get_launchable_tasks()
    assert len(ready) <= 1

def test_orchestrator_unblocks_after_completion(sample_tasks, config):
    """Completing task 1 unblocks task 2."""
    orch = JulesOrchestrator(sample_tasks, config)
    orch.mark_completed(1)
    ready = orch.get_ready_tasks()
    assert 2 in [t["number"] for t in ready]

def test_orchestrator_skips_claude_tasks(sample_tasks, config):
    """Only Jules tasks are returned by get_jules_tasks."""
    orch = JulesOrchestrator(sample_tasks, config)
    jules_tasks = orch.get_jules_tasks()
    assert [t["number"] for t in jules_tasks] == [1, 3]

def test_orchestrator_dashboard_format(sample_tasks, config):
    """Dashboard returns formatted string with all tasks."""
    orch = JulesOrchestrator(sample_tasks, config)
    dashboard = orch.render_dashboard()
    assert "Auth" in dashboard
    assert "Config" in dashboard
    assert "Tests" in dashboard
    assert "jules" in dashboard
    assert "claude" in dashboard

def test_orchestrator_all_done(sample_tasks, config):
    """all_done returns True when every task is completed or failed."""
    orch = JulesOrchestrator(sample_tasks, config)
    assert orch.all_done() is False
    orch.mark_completed(1)
    orch.mark_completed(2)
    orch.mark_completed(3)
    assert orch.all_done() is True

def test_orchestrator_mark_failed(sample_tasks, config):
    """Failed tasks count as done but not completed."""
    orch = JulesOrchestrator(sample_tasks, config)
    orch.mark_failed(1, "API error")
    assert orch.task_states[1]["status"] == "FAILED"
    assert orch.task_states[1]["error"] == "API error"

def test_orchestrator_summary(sample_tasks, config):
    """Summary shows counts of completed, failed, etc."""
    orch = JulesOrchestrator(sample_tasks, config)
    orch.mark_completed(1)
    orch.mark_completed(3)
    orch.mark_failed(2, "error")
    summary = orch.render_summary()
    assert "2" in summary  # 2 completed
    assert "1" in summary  # 1 failed
