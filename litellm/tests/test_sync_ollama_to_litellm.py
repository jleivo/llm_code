import pytest
import yaml
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, Mock
from litellm.scripts.sync_ollama_to_litellm import main, generate_litellm_config_entry, update_config_file


def test_main_function_exists():
    """Test that main function exists and can be called"""
    with patch('sys.argv', ['sync_ollama_to_litellm.py']):
        with patch('litellm.scripts.sync_ollama_to_litellm.get_ollama_models', return_value=[]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1  # Exits with 1 when no models found


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


def test_generate_litellm_config_entry():
    """Test YAML generation for LiteLLM config entry"""
    expected = """- model_name: "llama2:7b"
  litellm_params:
    model: "ollama_chat/llama2:7b"
    api_base: "http://localhost:11434"
    keep_alive: "180m"
    model_info:
      supports_function_calling: true
      supports_tools: true
      max_input_tokens: 4096"""

    result = generate_litellm_config_entry("llama2:7b", "http://localhost:11434", 4096)
    assert result == expected


def test_update_config_file():
    """Test updating config file with Ollama models"""
    # Create a temporary config file
    config_content = """
model_list:
  - model_name: "gpt-4"
    litellm_params:
      model: "openai/gpt-4"
      api_key: "sk-openai-key"
  - model_name: "claude-3-haiku"
    litellm_params:
      model: "anthropic/claude-3-haiku-20240307"
      api_key: "sk-anthropic-key"
  - model_name: "llama2:7b"
    litellm_params:
      model: "ollama_chat/llama2:7b"
      api_base: "http://localhost:11434"
      keep_alive: "180m"
      model_info:
        supports_function_calling: true
        supports_tools: true
        max_input_tokens: 2048
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write(config_content)
        tmp_path = tmp.name

    # Define Ollama models with context sizes
    ollama_models = {
        "llama2:7b": 4096,  # Updated context size
        "mistral:7b": 8192,  # New model
        "llama3:8b": 4096   # New model
    }

    # Update the config file
    update_config_file(tmp_path, ollama_models, "http://localhost:11434", ollama_models)

    # Read the updated config
    with open(tmp_path, 'r') as f:
        updated_config = yaml.safe_load(f)

    print("Models found in config:")
    for model in updated_config['model_list']:
        print(f"  - model_name: {model['model_name']}")
        print(f"    model: {model['litellm_params']['model']}")

    # Verify that non-Ollama models are preserved
    non_ollama_models = [m for m in updated_config['model_list'] if 'ollama_chat' not in m['litellm_params']['model']]
    assert len(non_ollama_models) == 2
    assert any(m['model_name'] == 'gpt-4' for m in non_ollama_models)
    assert any(m['model_name'] == 'claude-3-haiku' for m in non_ollama_models)

    # Verify Ollama models are updated/added correctly
    ollama_models_in_config = [m for m in updated_config['model_list'] if 'ollama_chat' in m['litellm_params']['model']]

    # Count each model
    llama2_model = next((m for m in ollama_models_in_config if m['model_name'] == 'llama2:7b'), None)
    mistral_model = next((m for m in ollama_models_in_config if m['model_name'] == 'mistral:7b'), None)
    llama3_model = next((m for m in ollama_models_in_config if m['model_name'] == 'llama3:8b'), None)

    # Verify llama2:7b was updated (context size changed from 2048 to 4096)
    assert llama2_model is not None
    assert llama2_model['model_name'] == 'llama2:7b'
    assert 'ollama_chat/llama2:7b' in llama2_model['litellm_params']['model']
    assert llama2_model['litellm_params']['model_info']['max_input_tokens'] == 4096

    # Verify new models were added
    assert mistral_model is not None
    assert mistral_model['model_name'] == 'mistral:7b'
    assert 'ollama_chat/mistral:7b' in mistral_model['litellm_params']['model']
    assert mistral_model['litellm_params']['model_info']['max_input_tokens'] == 8192

    assert llama3_model is not None
    assert llama3_model['model_name'] == 'llama3:8b'
    assert 'ollama_chat/llama3:8b' in llama3_model['litellm_params']['model']
    assert llama3_model['litellm_params']['model_info']['max_input_tokens'] == 4096

    # Clean up
    Path(tmp_path).unlink()


@patch('litellm.scripts.sync_ollama_to_litellm.get_ollama_models')
@patch('litellm.scripts.sync_ollama_to_litellm.get_ollama_running_models')
@patch('litellm.scripts.sync_ollama_to_litellm.update_config_file')
def test_main_integration(mock_update, mock_running, mock_models):
    """Test main function integration"""
    from litellm.scripts.sync_ollama_to_litellm import main

    mock_models.return_value = ["llama2:7b", "mistral:7b"]
    mock_running.return_value = {"llama2:7b": 4096}

    test_args = [
        'sync_ollama_to_litellm.py',
        '--ollama-url', 'http://localhost:11434',
        '--config-file', 'tests/fixtures/temp_config.yaml'
    ]

    with patch('sys.argv', test_args):
        with patch('pathlib.Path.exists', return_value=True):
            main()

    mock_models.assert_called_once_with('http://localhost:11434')
    mock_running.assert_called_once_with('http://localhost:11434')
    mock_update.assert_called_once()


def test_update_config_file_with_empty_file():
    """Test handling of completely empty config file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write("")  # Completely empty file
        tmp_path = tmp.name

    ollama_models = ["llama2:7b"]

    try:
        result = update_config_file(tmp_path, ollama_models, "http://localhost:11434", {"llama2:7b": 4096})

        assert result is True

        with open(tmp_path, 'r') as f:
            updated_config = yaml.safe_load(f)

        assert updated_config is not None
        assert 'model_list' in updated_config
        assert len(updated_config['model_list']) == 1
        assert updated_config['model_list'][0]['model_name'] == 'llama2:7b'
    finally:
        Path(tmp_path).unlink()


def test_update_config_file_with_empty_model_list():
    """Test handling of config file with empty model_list"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write("model_list: []")  # Empty model_list
        tmp_path = tmp.name

    ollama_models = ["llama2:7b"]

    try:
        result = update_config_file(tmp_path, ollama_models, "http://localhost:11434", {"llama2:7b": 4096})

        assert result is True

        with open(tmp_path, 'r') as f:
            updated_config = yaml.safe_load(f)

        assert updated_config is not None
        assert 'model_list' in updated_config
        assert len(updated_config['model_list']) == 1
    finally:
        Path(tmp_path).unlink()


def test_update_config_file_with_malformed_entry():
    """Test handling of config file with malformed entries (strings instead of dicts)"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write("""model_list:
  - "some string entry"
  - model_name: "valid-model"
    litellm_params:
      model: "openai/gpt-4"
      api_key: "sk-key"
""")  # Mix of string and dict entries
        tmp_path = tmp.name

    ollama_models = ["llama2:7b"]

    try:
        result = update_config_file(tmp_path, ollama_models, "http://localhost:11434", {"llama2:7b": 4096})

        assert result is True

        with open(tmp_path, 'r') as f:
            updated_config = yaml.safe_load(f)

        # String entry should be filtered out, valid model and new ollama model should remain
        assert updated_config is not None
        assert 'model_list' in updated_config
        # Should have the valid model and the new ollama model
        assert len(updated_config['model_list']) == 2
    finally:
        Path(tmp_path).unlink()


def test_update_config_file_with_null_model_list():
    """Test handling of config where model_list is None"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write("model_list: null")  # Explicitly null
        tmp_path = tmp.name

    ollama_models = ["llama2:7b"]

    try:
        result = update_config_file(tmp_path, ollama_models, "http://localhost:11434", {"llama2:7b": 4096})

        assert result is True

        with open(tmp_path, 'r') as f:
            updated_config = yaml.safe_load(f)

        assert updated_config is not None
        assert 'model_list' in updated_config
        assert len(updated_config['model_list']) == 1
    finally:
        Path(tmp_path).unlink()


def test_main_config_file_not_found_user_declines():
    """Test that main exits when config file doesn't exist and user says no"""
    with tempfile.TemporaryDirectory() as tmpdir:
        nonexistent_path = Path(tmpdir) / "nonexistent.yaml"

        test_args = [
            'sync_ollama_to_litellm.py',
            '--ollama-url', 'http://localhost:11434',
            '--config-file', str(nonexistent_path)
        ]

        with patch('sys.argv', test_args):
            with patch('litellm.scripts.sync_ollama_to_litellm.get_ollama_models', return_value=["llama2:7b"]):
                with patch('litellm.scripts.sync_ollama_to_litellm.get_ollama_running_models', return_value={"llama2:7b": 4096}):
                    with patch('builtins.input', return_value='n'):
                        with pytest.raises(SystemExit) as exc_info:
                            main()
                        assert exc_info.value.code == 1
        assert not nonexistent_path.exists()


def test_main_config_file_not_found_user_accepts():
    """Test that main creates config file when it doesn't exist and user says yes"""
    with tempfile.TemporaryDirectory() as tmpdir:
        new_config = Path(tmpdir) / "new_config.yaml"

        test_args = [
            'sync_ollama_to_litellm.py',
            '--ollama-url', 'http://localhost:11434',
            '--config-file', str(new_config)
        ]

        with patch('sys.argv', test_args):
            with patch('litellm.scripts.sync_ollama_to_litellm.get_ollama_models', return_value=["llama2:7b"]):
                with patch('litellm.scripts.sync_ollama_to_litellm.get_ollama_running_models', return_value={"llama2:7b": 4096}):
                    with patch('builtins.input', return_value='y'):
                        main()

        assert new_config.exists()
        with open(new_config) as f:
            config = yaml.safe_load(f)
        assert 'model_list' in config
        assert any(m['model_name'] == 'llama2:7b' for m in config['model_list'])


def test_update_config_file_empty_file():
    """Test handling of empty config file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write("")  # Empty file
        tmp_path = tmp.name

    ollama_models = {"llama2:7b": 4096}

    result = update_config_file(tmp_path, ollama_models, "http://localhost:11434", ollama_models)

    assert result is True

    # Verify config was created correctly
    with open(tmp_path, 'r') as f:
        updated_config = yaml.safe_load(f)

    assert updated_config is not None
    assert 'model_list' in updated_config
    assert len(updated_config['model_list']) == 1
    assert updated_config['model_list'][0]['model_name'] == 'llama2:7b'

    Path(tmp_path).unlink()


def test_update_config_file_null_model_list():
    """Test handling of config with null/None model_list"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write("model_list: null")
        tmp_path = tmp.name

    ollama_models = {"llama2:7b": 4096}

    result = update_config_file(tmp_path, ollama_models, "http://localhost:11434", ollama_models)

    assert result is True

    with open(tmp_path, 'r') as f:
        updated_config = yaml.safe_load(f)

    assert updated_config is not None
    # When model_list is null, it should be replaced with the new Ollama models
    assert len(updated_config['model_list']) == 1
    assert updated_config['model_list'][0]['model_name'] == 'llama2:7b'

    Path(tmp_path).unlink()


def test_update_config_file_malformed_entries():
    """Test handling of config with malformed/mixed entry types"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        # Config with both dict entries and string entries (malformed YAML)
        tmp.write("""
model_list:
  - model_name: "gpt-4"
    litellm_params:
      model: "openai/gpt-4"
      api_key: "sk-openai-key"
  - "malformed string entry"
  - model_name: "llama2:7b"
    litellm_params:
      model: "ollama_chat/llama2:7b"
      api_base: "http://localhost:11434"
""")
        tmp_path = tmp.name

    ollama_models = {"mistral:7b": 8192}

    result = update_config_file(tmp_path, ollama_models, "http://localhost:11434", ollama_models)

    assert result is True

    with open(tmp_path, 'r') as f:
        updated_config = yaml.safe_load(f)

    # Non-dict entries should be filtered out
    dict_entries = [m for m in updated_config['model_list'] if isinstance(m, dict)]
    assert len(dict_entries) == 2  # gpt-4 + mistral (llama2 should be replaced)

    # Verify gpt-4 preserved
    assert any(m['model_name'] == 'gpt-4' for m in dict_entries)

    # Verify new ollama model added
    assert any('ollama_chat' in m['litellm_params']['model'] for m in dict_entries)

    Path(tmp_path).unlink()


def test_update_config_file_no_model_list():
    """Test handling of config without model_list key"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write("other_key: some_value")
        tmp_path = tmp.name

    ollama_models = {"llama2:7b": 4096}

    result = update_config_file(tmp_path, ollama_models, "http://localhost:11434", ollama_models)

    assert result is True

    with open(tmp_path, 'r') as f:
        updated_config = yaml.safe_load(f)

    assert 'model_list' in updated_config
    assert len(updated_config['model_list']) == 1

    Path(tmp_path).unlink()


def test_model_metadata_defaults():
    from litellm.scripts.sync_ollama_to_litellm import ModelMetadata
    m = ModelMetadata(name="llama3:8b", context_size=4096)
    assert m.name == "llama3:8b"
    assert m.context_size == 4096
    assert m.is_embedding is False
    assert m.supports_tools is False
    assert m.supports_vision is False
    assert m.supports_thinking is False


def test_model_metadata_embedding():
    from litellm.scripts.sync_ollama_to_litellm import ModelMetadata
    m = ModelMetadata(name="nomic-embed-text:latest", context_size=8192, is_embedding=True)
    assert m.is_embedding is True
    assert m.supports_tools is False


def test_model_metadata_full_capabilities():
    from litellm.scripts.sync_ollama_to_litellm import ModelMetadata
    m = ModelMetadata(
        name="llama3.2-vision:11b",
        context_size=131072,
        supports_tools=True,
        supports_vision=True,
    )
    assert m.supports_tools is True
    assert m.supports_vision is True
    assert m.supports_thinking is False

