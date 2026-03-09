import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the jules directory to path so jules_cli can be imported directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jules_cli import main


def test_cli_create(capsys):
    """CLI create command uses JulesSession.create."""
    mock_session = MagicMock()
    mock_session.session_id = "session-123"
    mock_session.url = "https://jules.google.com/session/session-123"

    with patch("jules_cli.JulesSession") as MockSession:
        MockSession.create.return_value = mock_session
        with patch("sys.argv", ["jules_cli.py", "create", "--prompt", "Fix bug"]):
            main()

    MockSession.create.assert_called_once_with("Fix bug", "Task via Jules CLI")
    captured = capsys.readouterr()
    assert "session-123" in captured.out


def test_cli_status(capsys):
    """CLI status command prints session state."""
    mock_session = MagicMock()
    mock_session.status.return_value = "RUNNING"
    mock_session.get_activities.return_value = [
        {"id": "act1", "originator": "agent", "description": "Working..."}
    ]
    mock_session.get_session_data.return_value = {"state": "RUNNING", "outputs": []}

    with patch("jules_cli.JulesSession") as MockSession:
        MockSession.return_value = mock_session
        with patch("sys.argv", ["jules_cli.py", "status", "--session-id", "session-123"]):
            main()

    captured = capsys.readouterr()
    assert "RUNNING" in captured.out


def test_cli_merge_completed(capsys):
    """CLI merge command merges when session is COMPLETED."""
    mock_session = MagicMock()
    mock_session.status.return_value = "COMPLETED"
    mock_session.merge_pr.return_value = True

    with patch("jules_cli.JulesSession") as MockSession:
        MockSession.return_value = mock_session
        with patch("sys.argv", ["jules_cli.py", "merge", "--session-id", "session-123"]):
            main()

    mock_session.merge_pr.assert_called_once()
    captured = capsys.readouterr()
    assert "merged" in captured.out.lower() or "Successfully" in captured.out


def test_cli_merge_not_completed():
    """CLI merge command exits with error when session not COMPLETED."""
    mock_session = MagicMock()
    mock_session.status.return_value = "RUNNING"

    with patch("jules_cli.JulesSession") as MockSession:
        MockSession.return_value = mock_session
        with patch("sys.argv", ["jules_cli.py", "merge", "--session-id", "session-123"]):
            with pytest.raises(SystemExit):
                main()


def test_cli_auth_success(capsys):
    """CLI auth command prints OK with endpoint and project on success."""
    with patch("jules_cli.auth_check", return_value={"status": "ok", "endpoint": "https://jules.googleapis.com/v1alpha", "project": "my-project"}):
        with patch("sys.argv", ["jules_cli.py", "auth"]):
            main()
    captured = capsys.readouterr()
    assert "Authentication OK" in captured.out
    assert "my-project" in captured.out
    assert "https://jules.googleapis.com/v1alpha" in captured.out


def test_cli_auth_failure(capsys):
    """CLI auth command prints failure message and exits 1 on JulesError."""
    from jules import JulesError
    with patch("jules_cli.auth_check", side_effect=JulesError("Invalid or missing API key")):
        with patch("sys.argv", ["jules_cli.py", "auth"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Authentication failed" in captured.out


def test_cli_list_all(capsys):
    """CLI list command prints all sessions."""
    sessions = [
        {"id": "s1", "state": "CODING", "title": "Fix bug"},
        {"id": "s2", "state": "COMPLETED", "title": "Add tests"},
    ]
    with patch("jules_cli.list_sessions", return_value=sessions):
        with patch("sys.argv", ["jules_cli.py", "list"]):
            main()
    captured = capsys.readouterr()
    assert "s1" in captured.out
    assert "CODING" in captured.out
    assert "Fix bug" in captured.out
    assert "s2" in captured.out


def test_cli_list_filtered(capsys):
    """CLI list --state passes filter to list_sessions."""
    with patch("jules_cli.list_sessions", return_value=[]) as mock_list:
        with patch("sys.argv", ["jules_cli.py", "list", "--state", "CODING"]):
            main()
    mock_list.assert_called_once_with(state_filter="CODING")


def test_cli_list_invalid_state(capsys):
    """CLI list --state with unknown state prints a warning."""
    with patch("jules_cli.list_sessions", return_value=[]):
        with patch("sys.argv", ["jules_cli.py", "list", "--state", "BOGUS"]):
            main()
    captured = capsys.readouterr()
    assert "states" in captured.out.lower() or "valid" in captured.out.lower()


def test_cli_list_empty(capsys):
    """CLI list prints a message when no sessions found."""
    with patch("jules_cli.list_sessions", return_value=[]):
        with patch("sys.argv", ["jules_cli.py", "list"]):
            main()
    captured = capsys.readouterr()
    assert "no sessions" in captured.out.lower()


def test_cli_states(capsys):
    """CLI states command prints all valid states."""
    with patch("sys.argv", ["jules_cli.py", "states"]):
        main()
    captured = capsys.readouterr()
    assert "CODING" in captured.out
    assert "COMPLETED" in captured.out
    assert "FAILED" in captured.out
    assert "STARTING" in captured.out
