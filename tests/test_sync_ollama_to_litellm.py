import pytest
from unittest.mock import patch, Mock
from litellm.scripts.sync_ollama_to_litellm import main


def test_main_function_exists():
    """Test that main function exists and can be called"""
    with patch('sys.argv', ['sync_ollama_to_litellm.py']):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0


def test_get_ollama_models_success():
    """Test successful retrieval of model list"""
    from litellm.scripts.sync_ollama_to_litellm import get_ollama_models

    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama2:7b"},
                {"name": "mistral:7b"}
            ]
        }
        mock_get.return_value = mock_response

        result = get_ollama_models("http://localhost:11434")
        assert result == ["llama2:7b", "mistral:7b"]
        mock_get.assert_called_once_with("http://localhost:11434/api/tags", timeout=30)


def test_get_ollama_models_failure():
    """Test handling of API errors"""
    from litellm.scripts.sync_ollama_to_litellm import get_ollama_models

    with patch('requests.get') as mock_get:
        mock_get.side_effect = Exception("Connection refused")

        result = get_ollama_models("http://localhost:11434")
        assert result == []
