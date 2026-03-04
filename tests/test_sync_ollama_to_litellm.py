import pytest
from unittest.mock import patch, Mock
from litellm.scripts.sync_ollama_to_litellm import main


def test_main_function_exists():
    """Test that main function exists and can be called"""
    with patch('sys.argv', ['sync_ollama_to_litellm.py']):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
