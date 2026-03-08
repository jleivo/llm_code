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
