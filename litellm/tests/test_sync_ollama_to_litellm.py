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


def test_generate_litellm_config_entry_chat_with_tools():
    from litellm.scripts.sync_ollama_to_litellm import generate_litellm_config_entry, ModelMetadata
    metadata = ModelMetadata(
        name="llama3.2-vision:11b",
        context_size=131072,
        supports_tools=True,
        supports_vision=True,
    )
    result = generate_litellm_config_entry(metadata, "http://localhost:11434")
    assert result["model_name"] == "llama3.2-vision:11b"
    assert result["litellm_params"]["model"] == "ollama_chat/llama3.2-vision:11b"
    assert result["litellm_params"]["model_info"]["supports_function_calling"] is True
    assert result["litellm_params"]["model_info"]["supports_tools"] is True
    assert result["litellm_params"]["model_info"]["supports_vision"] is True
    assert result["litellm_params"]["model_info"]["max_input_tokens"] == 131072
    assert "supports_thinking" not in result["litellm_params"]["model_info"]


def test_generate_litellm_config_entry_thinking():
    from litellm.scripts.sync_ollama_to_litellm import generate_litellm_config_entry, ModelMetadata
    metadata = ModelMetadata(
        name="qwq:32b",
        context_size=32768,
        supports_tools=True,
        supports_thinking=True,
    )
    result = generate_litellm_config_entry(metadata, "http://localhost:11434")
    assert result["litellm_params"]["model"] == "ollama_chat/qwq:32b"
    assert result["litellm_params"]["model_info"]["supports_thinking"] is True
    assert "supports_vision" not in result["litellm_params"]["model_info"]


def test_generate_litellm_config_entry_embedding():
    from litellm.scripts.sync_ollama_to_litellm import generate_litellm_config_entry, ModelMetadata
    metadata = ModelMetadata(
        name="nomic-embed-text:latest",
        context_size=8192,
        is_embedding=True,
    )
    result = generate_litellm_config_entry(metadata, "http://localhost:11434")
    assert result["model_name"] == "nomic-embed-text:latest"
    assert result["litellm_params"]["model"] == "ollama/nomic-embed-text:latest"
    assert result["litellm_params"]["model_info"]["mode"] == "embedding"
    assert result["litellm_params"]["model_info"]["max_input_tokens"] == 8192
    assert "supports_function_calling" not in result["litellm_params"]["model_info"]
    assert "supports_tools" not in result["litellm_params"]["model_info"]


def test_generate_litellm_config_entry_basic_chat_no_capabilities():
    from litellm.scripts.sync_ollama_to_litellm import generate_litellm_config_entry, ModelMetadata
    metadata = ModelMetadata(name="llama2:7b", context_size=4096)
    result = generate_litellm_config_entry(metadata, "http://localhost:11434")
    assert result["litellm_params"]["model"] == "ollama_chat/llama2:7b"
    model_info = result["litellm_params"]["model_info"]
    assert "supports_function_calling" not in model_info
    assert "supports_tools" not in model_info
    assert "supports_vision" not in model_info
    assert "supports_thinking" not in model_info
    assert model_info["max_input_tokens"] == 4096


def test_update_config_file():
    from litellm.scripts.sync_ollama_to_litellm import update_config_file, ModelMetadata
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

    model_metadatas = [
        ModelMetadata(name="llama2:7b", context_size=4096, supports_tools=True),
        ModelMetadata(name="mistral:7b", context_size=8192, supports_tools=True),
        ModelMetadata(name="llama3:8b", context_size=4096, supports_tools=True),
    ]

    update_config_file(tmp_path, model_metadatas, "http://localhost:11434")

    with open(tmp_path, 'r') as f:
        updated_config = yaml.safe_load(f)

    non_ollama = [m for m in updated_config['model_list']
                  if not m['litellm_params']['model'].startswith('ollama')]
    assert len(non_ollama) == 2
    assert any(m['model_name'] == 'gpt-4' for m in non_ollama)
    assert any(m['model_name'] == 'claude-3-haiku' for m in non_ollama)

    ollama_models_in_config = [m for m in updated_config['model_list']
                                if m['litellm_params']['model'].startswith('ollama')]
    assert len(ollama_models_in_config) == 3

    llama2 = next(m for m in ollama_models_in_config if m['model_name'] == 'llama2:7b')
    assert llama2['litellm_params']['model_info']['max_input_tokens'] == 4096

    mistral = next(m for m in ollama_models_in_config if m['model_name'] == 'mistral:7b')
    assert mistral['litellm_params']['model_info']['max_input_tokens'] == 8192

    Path(tmp_path).unlink()


def test_update_config_file_embedding_model_uses_ollama_prefix():
    from litellm.scripts.sync_ollama_to_litellm import update_config_file, ModelMetadata
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write("model_list: []")
        tmp_path = tmp.name

    model_metadatas = [
        ModelMetadata(name="nomic-embed-text:latest", context_size=8192, is_embedding=True),
    ]

    update_config_file(tmp_path, model_metadatas, "http://localhost:11434")

    with open(tmp_path, 'r') as f:
        updated_config = yaml.safe_load(f)

    entry = updated_config['model_list'][0]
    assert entry['litellm_params']['model'] == "ollama/nomic-embed-text:latest"
    assert entry['litellm_params']['model_info']['mode'] == "embedding"
    Path(tmp_path).unlink()


def test_update_config_file_replaces_existing_embedding_model():
    from litellm.scripts.sync_ollama_to_litellm import update_config_file, ModelMetadata
    config_content = """
model_list:
  - model_name: "nomic-embed-text:latest"
    litellm_params:
      model: "ollama/nomic-embed-text:latest"
      api_base: "http://localhost:11434"
      keep_alive: "180m"
      model_info:
        mode: "embedding"
        max_input_tokens: 512
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write(config_content)
        tmp_path = tmp.name

    model_metadatas = [
        ModelMetadata(name="nomic-embed-text:latest", context_size=8192, is_embedding=True),
    ]

    update_config_file(tmp_path, model_metadatas, "http://localhost:11434")

    with open(tmp_path, 'r') as f:
        updated_config = yaml.safe_load(f)

    assert len(updated_config['model_list']) == 1
    assert updated_config['model_list'][0]['litellm_params']['model_info']['max_input_tokens'] == 8192
    Path(tmp_path).unlink()


def test_update_config_file_with_empty_file():
    from litellm.scripts.sync_ollama_to_litellm import update_config_file, ModelMetadata
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write("")
        tmp_path = tmp.name

    model_metadatas = [ModelMetadata(name="llama2:7b", context_size=4096)]
    result = update_config_file(tmp_path, model_metadatas, "http://localhost:11434")

    assert result is True
    with open(tmp_path, 'r') as f:
        updated_config = yaml.safe_load(f)
    assert len(updated_config['model_list']) == 1
    assert updated_config['model_list'][0]['model_name'] == 'llama2:7b'
    Path(tmp_path).unlink()


def test_update_config_file_with_empty_model_list():
    from litellm.scripts.sync_ollama_to_litellm import update_config_file, ModelMetadata
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write("model_list: []")
        tmp_path = tmp.name

    model_metadatas = [ModelMetadata(name="llama2:7b", context_size=4096)]
    result = update_config_file(tmp_path, model_metadatas, "http://localhost:11434")

    assert result is True
    with open(tmp_path, 'r') as f:
        updated_config = yaml.safe_load(f)
    assert len(updated_config['model_list']) == 1
    Path(tmp_path).unlink()


def test_update_config_file_with_malformed_entry():
    from litellm.scripts.sync_ollama_to_litellm import update_config_file, ModelMetadata
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write("""model_list:
  - "some string entry"
  - model_name: "valid-model"
    litellm_params:
      model: "openai/gpt-4"
      api_key: "sk-key"
""")
        tmp_path = tmp.name

    model_metadatas = [ModelMetadata(name="llama2:7b", context_size=4096)]
    result = update_config_file(tmp_path, model_metadatas, "http://localhost:11434")

    assert result is True
    with open(tmp_path, 'r') as f:
        updated_config = yaml.safe_load(f)
    assert len(updated_config['model_list']) == 2
    Path(tmp_path).unlink()


def test_update_config_file_with_null_model_list():
    from litellm.scripts.sync_ollama_to_litellm import update_config_file, ModelMetadata
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write("model_list: null")
        tmp_path = tmp.name

    model_metadatas = [ModelMetadata(name="llama2:7b", context_size=4096)]
    result = update_config_file(tmp_path, model_metadatas, "http://localhost:11434")

    assert result is True
    with open(tmp_path, 'r') as f:
        updated_config = yaml.safe_load(f)
    assert len(updated_config['model_list']) == 1
    Path(tmp_path).unlink()


def test_update_config_file_malformed_entries():
    from litellm.scripts.sync_ollama_to_litellm import update_config_file, ModelMetadata
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
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

    model_metadatas = [ModelMetadata(name="mistral:7b", context_size=8192)]
    result = update_config_file(tmp_path, model_metadatas, "http://localhost:11434")

    assert result is True
    with open(tmp_path, 'r') as f:
        updated_config = yaml.safe_load(f)

    dict_entries = [m for m in updated_config['model_list'] if isinstance(m, dict)]
    assert len(dict_entries) == 2
    assert any(m['model_name'] == 'gpt-4' for m in dict_entries)
    assert any('ollama' in m['litellm_params']['model'] for m in dict_entries)
    Path(tmp_path).unlink()


def test_update_config_file_no_model_list():
    from litellm.scripts.sync_ollama_to_litellm import update_config_file, ModelMetadata
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write("other_key: some_value")
        tmp_path = tmp.name

    model_metadatas = [ModelMetadata(name="llama2:7b", context_size=4096)]
    result = update_config_file(tmp_path, model_metadatas, "http://localhost:11434")

    assert result is True
    with open(tmp_path, 'r') as f:
        updated_config = yaml.safe_load(f)
    assert 'model_list' in updated_config
    assert len(updated_config['model_list']) == 1
    Path(tmp_path).unlink()


@patch('litellm.scripts.sync_ollama_to_litellm.get_ollama_models')
@patch('litellm.scripts.sync_ollama_to_litellm.get_model_info')
@patch('litellm.scripts.sync_ollama_to_litellm.update_config_file')
def test_main_integration(mock_update, mock_get_info, mock_models):
    from litellm.scripts.sync_ollama_to_litellm import main, ModelMetadata

    mock_models.return_value = ["llama2:7b", "mistral:7b"]
    mock_get_info.side_effect = [
        ModelMetadata(name="llama2:7b", context_size=4096, supports_tools=True),
        ModelMetadata(name="mistral:7b", context_size=8192, supports_tools=True),
    ]

    test_args = [
        'sync_ollama_to_litellm.py',
        '--ollama-url', 'http://localhost:11434',
        '--config-file', 'tests/fixtures/temp_config.yaml',
    ]

    with patch('sys.argv', test_args):
        with patch('pathlib.Path.exists', return_value=True):
            main()

    mock_models.assert_called_once_with('http://localhost:11434')
    assert mock_get_info.call_count == 2
    mock_update.assert_called_once()


@patch('litellm.scripts.sync_ollama_to_litellm.get_ollama_models')
@patch('litellm.scripts.sync_ollama_to_litellm.get_model_info')
def test_main_skips_models_with_api_errors(mock_get_info, mock_models, capsys):
    from litellm.scripts.sync_ollama_to_litellm import main, ModelMetadata

    mock_models.return_value = ["llama2:7b", "broken-model:7b", "mistral:7b"]
    mock_get_info.side_effect = [
        ModelMetadata(name="llama2:7b", context_size=4096),
        None,  # API failure for broken-model
        ModelMetadata(name="mistral:7b", context_size=8192),
    ]

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write("model_list: []")
        tmp_path = tmp.name

    test_args = [
        'sync_ollama_to_litellm.py',
        '--ollama-url', 'http://localhost:11434',
        '--config-file', tmp_path,
    ]

    with patch('sys.argv', test_args):
        main()

    captured = capsys.readouterr()
    assert "Skipped 1 model" in captured.out
    assert "broken-model:7b" in captured.out
    assert "Synced 2 models" in captured.out
    Path(tmp_path).unlink()


@patch('litellm.scripts.sync_ollama_to_litellm.get_ollama_models')
@patch('litellm.scripts.sync_ollama_to_litellm.get_model_info')
def test_main_summary_shows_chat_and_embedding_counts(mock_get_info, mock_models, capsys):
    from litellm.scripts.sync_ollama_to_litellm import main, ModelMetadata

    mock_models.return_value = ["llama2:7b", "nomic-embed-text:latest"]
    mock_get_info.side_effect = [
        ModelMetadata(name="llama2:7b", context_size=4096),
        ModelMetadata(name="nomic-embed-text:latest", context_size=8192, is_embedding=True),
    ]

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
        tmp.write("model_list: []")
        tmp_path = tmp.name

    test_args = [
        'sync_ollama_to_litellm.py',
        '--ollama-url', 'http://localhost:11434',
        '--config-file', tmp_path,
    ]

    with patch('sys.argv', test_args):
        main()

    captured = capsys.readouterr()
    assert "1 chat" in captured.out
    assert "1 embedding" in captured.out
    Path(tmp_path).unlink()


def test_main_config_file_not_found_user_declines():
    with tempfile.TemporaryDirectory() as tmpdir:
        nonexistent_path = Path(tmpdir) / "nonexistent.yaml"

        test_args = [
            'sync_ollama_to_litellm.py',
            '--ollama-url', 'http://localhost:11434',
            '--config-file', str(nonexistent_path),
        ]

        with patch('sys.argv', test_args):
            with patch('litellm.scripts.sync_ollama_to_litellm.get_ollama_models', return_value=["llama2:7b"]):
                from litellm.scripts.sync_ollama_to_litellm import ModelMetadata
                with patch('litellm.scripts.sync_ollama_to_litellm.get_model_info',
                           return_value=ModelMetadata(name="llama2:7b", context_size=4096)):
                    with patch('builtins.input', return_value='n'):
                        with pytest.raises(SystemExit) as exc_info:
                            from litellm.scripts.sync_ollama_to_litellm import main
                            main()
                        assert exc_info.value.code == 1
        assert not nonexistent_path.exists()


def test_main_config_file_not_found_user_accepts():
    with tempfile.TemporaryDirectory() as tmpdir:
        new_config = Path(tmpdir) / "new_config.yaml"

        test_args = [
            'sync_ollama_to_litellm.py',
            '--ollama-url', 'http://localhost:11434',
            '--config-file', str(new_config),
        ]

        with patch('sys.argv', test_args):
            with patch('litellm.scripts.sync_ollama_to_litellm.get_ollama_models', return_value=["llama2:7b"]):
                from litellm.scripts.sync_ollama_to_litellm import ModelMetadata
                with patch('litellm.scripts.sync_ollama_to_litellm.get_model_info',
                           return_value=ModelMetadata(name="llama2:7b", context_size=4096)):
                    with patch('builtins.input', return_value='y'):
                        from litellm.scripts.sync_ollama_to_litellm import main
                        main()

        assert new_config.exists()
        with open(new_config) as f:
            config = yaml.safe_load(f)
        assert 'model_list' in config
        assert any(m['model_name'] == 'llama2:7b' for m in config['model_list'])



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


def test_get_model_info_full_capabilities():
    from litellm.scripts.sync_ollama_to_litellm import get_model_info

    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "capabilities": ["completion", "tools", "vision"],
            "model_info": {"llama.context_length": 131072},
        }
        mock_post.return_value = mock_response

        result = get_model_info("http://localhost:11434", "llama3.2-vision:11b")

    assert result is not None
    assert result.name == "llama3.2-vision:11b"
    assert result.context_size == 131072
    assert result.is_embedding is False
    assert result.supports_tools is True
    assert result.supports_vision is True
    assert result.supports_thinking is False


def test_get_model_info_embedding():
    from litellm.scripts.sync_ollama_to_litellm import get_model_info

    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "capabilities": ["embedding"],
            "model_info": {"bert.context_length": 8192},
        }
        mock_post.return_value = mock_response

        result = get_model_info("http://localhost:11434", "nomic-embed-text:latest")

    assert result is not None
    assert result.is_embedding is True
    assert result.context_size == 8192
    assert result.supports_tools is False


def test_get_model_info_thinking():
    from litellm.scripts.sync_ollama_to_litellm import get_model_info

    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "capabilities": ["completion", "tools", "thinking"],
            "model_info": {"llama.context_length": 32768},
        }
        mock_post.return_value = mock_response

        result = get_model_info("http://localhost:11434", "qwq:32b")

    assert result is not None
    assert result.supports_thinking is True
    assert result.supports_tools is True
    assert result.context_size == 32768


def test_get_model_info_missing_capabilities_warns(capsys):
    from litellm.scripts.sync_ollama_to_litellm import get_model_info

    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model_info": {"llama.context_length": 4096},
        }
        mock_post.return_value = mock_response

        result = get_model_info("http://localhost:11434", "llama2:7b")

    assert result is not None
    assert result.name == "llama2:7b"
    assert result.context_size == 4096
    assert result.is_embedding is False
    assert result.supports_tools is False
    captured = capsys.readouterr()
    assert "capabilities" in captured.err
    assert "llama2:7b" in captured.err


def test_get_model_info_missing_context_length_warns(capsys):
    from litellm.scripts.sync_ollama_to_litellm import get_model_info

    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "capabilities": ["completion", "tools"],
            "model_info": {},
        }
        mock_post.return_value = mock_response

        result = get_model_info("http://localhost:11434", "llama2:7b")

    assert result is not None
    assert result.context_size == 2048
    captured = capsys.readouterr()
    assert "context" in captured.err.lower()
    assert "llama2:7b" in captured.err


def test_get_model_info_api_failure_returns_none():
    from litellm.scripts.sync_ollama_to_litellm import get_model_info

    with patch('requests.post') as mock_post:
        mock_post.side_effect = Exception("Connection refused")

        result = get_model_info("http://localhost:11434", "llama2:7b")

    assert result is None


# --- parse_context_from_name tests ---

def test_parse_context_from_name_128k():
    from litellm.scripts.sync_ollama_to_litellm import parse_context_from_name
    assert parse_context_from_name("qwen3-next-80b:128k") == 128 * 1024


def test_parse_context_from_name_8k():
    from litellm.scripts.sync_ollama_to_litellm import parse_context_from_name
    assert parse_context_from_name("model:8k") == 8 * 1024


def test_parse_context_from_name_case_insensitive():
    from litellm.scripts.sync_ollama_to_litellm import parse_context_from_name
    assert parse_context_from_name("model:64K") == 64 * 1024


def test_parse_context_from_name_parameter_tag_returns_none():
    from litellm.scripts.sync_ollama_to_litellm import parse_context_from_name
    assert parse_context_from_name("llama2:7b") is None


def test_parse_context_from_name_latest_returns_none():
    from litellm.scripts.sync_ollama_to_litellm import parse_context_from_name
    assert parse_context_from_name("mistral:latest") is None


def test_parse_context_from_name_no_tag_returns_none():
    from litellm.scripts.sync_ollama_to_litellm import parse_context_from_name
    assert parse_context_from_name("llama3") is None


def test_parse_context_from_name_complex_tag_with_k_suffix():
    from litellm.scripts.sync_ollama_to_litellm import parse_context_from_name
    assert parse_context_from_name("qwen3:32b-instruct-128k") == 128 * 1024


# --- get_model_info uses name-based context over /api/show ---

def test_get_model_info_name_context_overrides_api_show():
    from litellm.scripts.sync_ollama_to_litellm import get_model_info

    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "capabilities": ["completion", "tools"],
            "model_info": {"llama.context_length": 32768},  # api/show says 32k
        }
        mock_post.return_value = mock_response

        # Model name says 128k — should win
        result = get_model_info("http://localhost:11434", "qwen3:128k")

    assert result is not None
    assert result.context_size == 128 * 1024


def test_get_model_info_falls_back_to_api_show_when_no_name_context():
    from litellm.scripts.sync_ollama_to_litellm import get_model_info

    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "capabilities": ["completion", "tools"],
            "model_info": {"llama.context_length": 32768},
        }
        mock_post.return_value = mock_response

        result = get_model_info("http://localhost:11434", "llama2:7b")

    assert result is not None
    assert result.context_size == 32768
