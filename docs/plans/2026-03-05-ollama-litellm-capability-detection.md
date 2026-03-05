# Ollama-LiteLLM Capability Detection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance `sync_ollama_to_litellm.py` to detect model capabilities (tools, vision, thinking, embedding) via Ollama's `/api/show` endpoint and generate correct LiteLLM config entries for each model type.

**Architecture:** Replace the `/api/ps` running-models call with per-model `/api/show` calls that return a `ModelMetadata` dataclass. YAML generation branches on `is_embedding` to use `ollama/` vs `ollama_chat/` prefix and only emits capability flags that are `true`. A run summary at the end lists synced counts and any skipped models by name.

**Tech Stack:** Python 3.12+, requests, PyYAML, dataclasses (stdlib)

---

### Task 1: Add `ModelMetadata` Dataclass

**Files:**
- Modify: `litellm/scripts/sync_ollama_to_litellm.py`
- Modify: `litellm/tests/test_sync_ollama_to_litellm.py`

**Step 1: Write the failing test**

Add to `litellm/tests/test_sync_ollama_to_litellm.py` after the imports:

```python
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
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/juha/git/llm_code && python -m pytest litellm/tests/test_sync_ollama_to_litellm.py::test_model_metadata_defaults litellm/tests/test_sync_ollama_to_litellm.py::test_model_metadata_embedding litellm/tests/test_sync_ollama_to_litellm.py::test_model_metadata_full_capabilities -v
```

Expected: FAIL with `ImportError: cannot import name 'ModelMetadata'`

**Step 3: Add dataclass to script**

Add after the imports in `litellm/scripts/sync_ollama_to_litellm.py` (before `get_ollama_models`):

```python
from dataclasses import dataclass, field


@dataclass
class ModelMetadata:
    name: str
    context_size: int
    is_embedding: bool = False
    supports_tools: bool = False
    supports_vision: bool = False
    supports_thinking: bool = False
```

**Step 4: Run tests to verify they pass**

```bash
cd /home/juha/git/llm_code && python -m pytest litellm/tests/test_sync_ollama_to_litellm.py::test_model_metadata_defaults litellm/tests/test_sync_ollama_to_litellm.py::test_model_metadata_embedding litellm/tests/test_sync_ollama_to_litellm.py::test_model_metadata_full_capabilities -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add litellm/scripts/sync_ollama_to_litellm.py litellm/tests/test_sync_ollama_to_litellm.py
git commit -m "feat: add ModelMetadata dataclass for ollama model capability tracking"
```

---

### Task 2: Implement `get_model_info()` Using `/api/show`

**Files:**
- Modify: `litellm/scripts/sync_ollama_to_litellm.py`
- Modify: `litellm/tests/test_sync_ollama_to_litellm.py`

**Step 1: Write the failing tests**

Add to `litellm/tests/test_sync_ollama_to_litellm.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/juha/git/llm_code && python -m pytest litellm/tests/test_sync_ollama_to_litellm.py::test_get_model_info_full_capabilities litellm/tests/test_sync_ollama_to_litellm.py::test_get_model_info_embedding litellm/tests/test_sync_ollama_to_litellm.py::test_get_model_info_thinking litellm/tests/test_sync_ollama_to_litellm.py::test_get_model_info_missing_capabilities_warns litellm/tests/test_sync_ollama_to_litellm.py::test_get_model_info_missing_context_length_warns litellm/tests/test_sync_ollama_to_litellm.py::test_get_model_info_api_failure_returns_none -v
```

Expected: FAIL with `ImportError: cannot import name 'get_model_info'`

**Step 3: Implement `get_model_info()`**

Add to `litellm/scripts/sync_ollama_to_litellm.py` after `get_ollama_running_models` (keep the old function for now — it will be removed in Task 5):

```python
def get_model_info(ollama_url: str, model_name: str) -> ModelMetadata | None:
    """Get model metadata from Ollama /api/show endpoint.

    Args:
        ollama_url: Base URL of Ollama server
        model_name: Name of the model to query

    Returns:
        ModelMetadata if successful, None if API call failed
    """
    try:
        response = requests.post(
            f"{ollama_url}/api/show",
            json={"model": model_name},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        # Detect context length from model_info (key ends with .context_length)
        model_info = data.get("model_info", {})
        context_size = 2048
        context_found = False
        for key, value in model_info.items():
            if key.endswith(".context_length") and isinstance(value, int):
                context_size = value
                context_found = True
                break
        if not context_found:
            print(
                f"Warning: Context length not found in /api/show for {model_name}, "
                "using default 2048",
                file=sys.stderr,
            )

        # Detect capabilities
        capabilities = data.get("capabilities")
        if capabilities is None:
            print(
                f"Warning: /api/show did not return 'capabilities' for model {model_name}. "
                "Defaulting to basic chat. Upgrade Ollama for accurate capability detection.",
                file=sys.stderr,
            )
            return ModelMetadata(name=model_name, context_size=context_size)

        return ModelMetadata(
            name=model_name,
            context_size=context_size,
            is_embedding="embedding" in capabilities,
            supports_tools="tools" in capabilities,
            supports_vision="vision" in capabilities,
            supports_thinking="thinking" in capabilities,
        )
    except Exception as e:
        print(f"Error fetching model info for {model_name}: {e}", file=sys.stderr)
        return None
```

**Step 4: Run tests to verify they pass**

```bash
cd /home/juha/git/llm_code && python -m pytest litellm/tests/test_sync_ollama_to_litellm.py::test_get_model_info_full_capabilities litellm/tests/test_sync_ollama_to_litellm.py::test_get_model_info_embedding litellm/tests/test_sync_ollama_to_litellm.py::test_get_model_info_thinking litellm/tests/test_sync_ollama_to_litellm.py::test_get_model_info_missing_capabilities_warns litellm/tests/test_sync_ollama_to_litellm.py::test_get_model_info_missing_context_length_warns litellm/tests/test_sync_ollama_to_litellm.py::test_get_model_info_api_failure_returns_none -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add litellm/scripts/sync_ollama_to_litellm.py litellm/tests/test_sync_ollama_to_litellm.py
git commit -m "feat: implement get_model_info() using ollama /api/show endpoint"
```

---

### Task 3: Update `generate_litellm_config_entry()` to Use `ModelMetadata`

**Files:**
- Modify: `litellm/scripts/sync_ollama_to_litellm.py`
- Modify: `litellm/tests/test_sync_ollama_to_litellm.py`

**Background:** The function currently takes `(model_name, api_base, context_size)` and returns a YAML string. Change it to take `(metadata: ModelMetadata, api_base: str)` and return a `dict`. This dict is used by both `update_config_file()` and stdout output (via `yaml.dump`). Only emit capability keys that are `True`. Embedding models use `ollama/` prefix and `mode: "embedding"`.

**Step 1: Replace the existing `test_generate_litellm_config_entry` test**

Find and replace the existing `test_generate_litellm_config_entry` function in `litellm/tests/test_sync_ollama_to_litellm.py` with:

```python
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
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/juha/git/llm_code && python -m pytest litellm/tests/test_sync_ollama_to_litellm.py::test_generate_litellm_config_entry_chat_with_tools litellm/tests/test_sync_ollama_to_litellm.py::test_generate_litellm_config_entry_thinking litellm/tests/test_sync_ollama_to_litellm.py::test_generate_litellm_config_entry_embedding litellm/tests/test_sync_ollama_to_litellm.py::test_generate_litellm_config_entry_basic_chat_no_capabilities -v
```

Expected: FAIL (wrong number of args or wrong return type)

**Step 3: Replace `generate_litellm_config_entry()` in the script**

Replace the entire existing `generate_litellm_config_entry` function in `litellm/scripts/sync_ollama_to_litellm.py` with:

```python
def generate_litellm_config_entry(metadata: ModelMetadata, api_base: str) -> dict:
    """Generate a LiteLLM config entry dict for an Ollama model.

    Args:
        metadata: Model metadata including capabilities and context size
        api_base: Base URL of Ollama server

    Returns:
        Dict representing the config entry
    """
    if metadata.is_embedding:
        return {
            "model_name": metadata.name,
            "litellm_params": {
                "model": f"ollama/{metadata.name}",
                "api_base": api_base,
                "keep_alive": "180m",
                "model_info": {
                    "mode": "embedding",
                    "max_input_tokens": metadata.context_size,
                },
            },
        }

    model_info: dict[str, Any] = {}
    if metadata.supports_tools:
        model_info["supports_function_calling"] = True
        model_info["supports_tools"] = True
    if metadata.supports_vision:
        model_info["supports_vision"] = True
    if metadata.supports_thinking:
        model_info["supports_thinking"] = True
    model_info["max_input_tokens"] = metadata.context_size

    return {
        "model_name": metadata.name,
        "litellm_params": {
            "model": f"ollama_chat/{metadata.name}",
            "api_base": api_base,
            "keep_alive": "180m",
            "model_info": model_info,
        },
    }
```

**Step 4: Run tests to verify they pass**

```bash
cd /home/juha/git/llm_code && python -m pytest litellm/tests/test_sync_ollama_to_litellm.py::test_generate_litellm_config_entry_chat_with_tools litellm/tests/test_sync_ollama_to_litellm.py::test_generate_litellm_config_entry_thinking litellm/tests/test_sync_ollama_to_litellm.py::test_generate_litellm_config_entry_embedding litellm/tests/test_sync_ollama_to_litellm.py::test_generate_litellm_config_entry_basic_chat_no_capabilities -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add litellm/scripts/sync_ollama_to_litellm.py litellm/tests/test_sync_ollama_to_litellm.py
git commit -m "feat: update generate_litellm_config_entry to use ModelMetadata, support embedding models"
```

---

### Task 4: Update `update_config_file()` to Use `list[ModelMetadata]`

**Files:**
- Modify: `litellm/scripts/sync_ollama_to_litellm.py`
- Modify: `litellm/tests/test_sync_ollama_to_litellm.py`

**Background:** The function signature changes from `(config_path, ollama_models: list[str], api_base: str, running_models: dict)` to `(config_path, model_metadatas: list[ModelMetadata], api_base: str)`. The existing Ollama model filter must also catch `ollama/` prefix (embedding models). All test calls need updating.

**Step 1: Update the filter logic and signature in the script**

Replace the `update_config_file` function in `litellm/scripts/sync_ollama_to_litellm.py`:

```python
def update_config_file(config_path: str, model_metadatas: list[ModelMetadata], api_base: str) -> bool:
    """Update LiteLLM config file with Ollama models.

    Args:
        config_path: Path to the LiteLLM config file
        model_metadatas: List of ModelMetadata for all Ollama models
        api_base: Base URL of Ollama server

    Returns:
        True if successful, False otherwise
    """
    try:
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        except FileNotFoundError:
            config = {'model_list': []}

        if 'model_list' not in config or config['model_list'] is None:
            config['model_list'] = []

        # Remove existing Ollama models (both ollama_chat/ and ollama/ prefixes)
        non_ollama_models = []
        for model in config['model_list']:
            if not isinstance(model, dict):
                continue
            if 'litellm_params' not in model:
                non_ollama_models.append(model)
                continue
            if not isinstance(model['litellm_params'], dict):
                continue
            model_str = model['litellm_params'].get('model', '')
            if model_str.startswith('ollama_chat/') or model_str.startswith('ollama/'):
                continue
            non_ollama_models.append(model)

        new_entries = [
            generate_litellm_config_entry(metadata, api_base)
            for metadata in model_metadatas
        ]

        config['model_list'] = non_ollama_models + new_entries

        with open(config_path, 'w') as f:
            yaml.dump(config, f, sort_keys=False, default_flow_style=False)

        return True
    except Exception as e:
        print(f"Error updating config file: {e}", file=sys.stderr)
        return False
```

**Step 2: Update all `update_config_file` test calls**

In `litellm/tests/test_sync_ollama_to_litellm.py`, update every test that calls `update_config_file`. The new call pattern passes a `list[ModelMetadata]` instead of separate lists. Here is the complete updated set of test functions to replace their existing versions:

```python
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


def test_update_config_file_empty_file():
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


def test_update_config_file_null_model_list():
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
```

Also remove the old duplicate test functions: `test_update_config_file_empty_file` (first occurrence), `test_update_config_file_null_model_list` (first occurrence), `test_update_config_file_malformed_entries` (first occurrence), `test_update_config_file_no_model_list` (first occurrence) — keep only the updated versions above.

**Step 3: Run the updated update_config_file tests**

```bash
cd /home/juha/git/llm_code && python -m pytest litellm/tests/test_sync_ollama_to_litellm.py -k "update_config" -v
```

Expected: All PASS

**Step 4: Commit**

```bash
git add litellm/scripts/sync_ollama_to_litellm.py litellm/tests/test_sync_ollama_to_litellm.py
git commit -m "feat: update update_config_file to use ModelMetadata, handle embedding prefix"
```

---

### Task 5: Update `main()` — Remove `/api/ps`, Use `get_model_info()`, Add Summary

**Files:**
- Modify: `litellm/scripts/sync_ollama_to_litellm.py`
- Modify: `litellm/tests/test_sync_ollama_to_litellm.py`

**Step 1: Write the updated integration test**

Replace `test_main_integration` and both `test_main_config_file_not_found_*` tests in `litellm/tests/test_sync_ollama_to_litellm.py`:

```python
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
```

**Step 2: Run new integration tests to verify they fail**

```bash
cd /home/juha/git/llm_code && python -m pytest litellm/tests/test_sync_ollama_to_litellm.py::test_main_integration litellm/tests/test_sync_ollama_to_litellm.py::test_main_skips_models_with_api_errors litellm/tests/test_sync_ollama_to_litellm.py::test_main_summary_shows_chat_and_embedding_counts -v
```

Expected: FAIL (still calling old `get_ollama_running_models` path)

**Step 3: Rewrite `main()` and remove `get_ollama_running_models`**

Replace the entire `main()` function and delete `get_ollama_running_models()` from `litellm/scripts/sync_ollama_to_litellm.py`:

```python
def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Sync Ollama models to LiteLLM config')
    parser.add_argument('--ollama-url',
                        default='http://tuprpisrvp02.intra.leivo:7900',
                        help='Ollama server URL (default: http://tuprpisrvp02.intra.leivo:7900)')
    parser.add_argument('--config-file',
                        default='litellm/config.yaml',
                        help='Path to LiteLLM config file (default: litellm/config.yaml)')
    parser.add_argument('--output',
                        choices=['file', 'stdout'],
                        default='file',
                        help='Output destination (default: file)')

    args = parser.parse_args()

    print(f"Fetching models from {args.ollama_url}...")
    models = get_ollama_models(args.ollama_url)
    if not models:
        print("No models found or error connecting to Ollama", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(models)} models: {', '.join(models)}")
    print("Fetching model details via /api/show...")

    model_metadatas: list[ModelMetadata] = []
    skipped: list[str] = []

    for model_name in models:
        metadata = get_model_info(args.ollama_url, model_name)
        if metadata is None:
            skipped.append(model_name)
        else:
            model_metadatas.append(metadata)

    chat_count = sum(1 for m in model_metadatas if not m.is_embedding)
    embedding_count = sum(1 for m in model_metadatas if m.is_embedding)

    if args.output == 'stdout':
        for metadata in model_metadatas:
            entry = generate_litellm_config_entry(metadata, args.ollama_url)
            print(yaml.dump([entry], default_flow_style=False), end="")
    else:
        config_path = Path(args.config_file)
        if not config_path.exists():
            print(f"Config file not found: {config_path}")
            response = input("Create it? [y/N]: ")
            if response.lower() != 'y':
                print("Aborted", file=sys.stderr)
                sys.exit(1)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, 'w') as f:
                yaml.dump({'model_list': []}, f, sort_keys=False, default_flow_style=False)
            print(f"Created config file: {config_path}")

        print(f"Updating config file: {config_path}")
        update_config_file(config_path, model_metadatas, args.ollama_url)
        print("Config file updated successfully!")

    print(f"Synced {len(model_metadatas)} models: {chat_count} chat, {embedding_count} embedding")
    if skipped:
        noun = "model" if len(skipped) == 1 else "models"
        print(f"Skipped {len(skipped)} {noun} (API error): {', '.join(skipped)}")
```

**Step 4: Run all tests**

```bash
cd /home/juha/git/llm_code && python -m pytest litellm/tests/test_sync_ollama_to_litellm.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add litellm/scripts/sync_ollama_to_litellm.py litellm/tests/test_sync_ollama_to_litellm.py
git commit -m "feat: update main() to use get_model_info per model and print run summary"
```

---

### Task 6: Full Verification

**Files:** No changes — verification only

**Step 1: Run the full test suite**

```bash
cd /home/juha/git/llm_code && python -m pytest litellm/tests/test_sync_ollama_to_litellm.py -v
```

Expected: All tests PASS, no warnings about deprecated calls.

**Step 2: Smoke test the CLI**

```bash
cd /home/juha/git/llm_code && python litellm/scripts/sync_ollama_to_litellm.py --help
```

Expected: Help output showing all options.

**Step 3: Test stdout output against live Ollama (if accessible)**

```bash
cd /home/juha/git/llm_code && python litellm/scripts/sync_ollama_to_litellm.py --output stdout
```

Expected: YAML entries printed for each model. Embedding models show `ollama/` prefix and `mode: embedding`. Chat models show only capability flags that are `true`.

**Step 4: Commit final cleanup if needed**

```bash
git add -A
git commit -m "chore: final cleanup after capability detection implementation"
```

---

## Summary

Changes after this plan:
- New `ModelMetadata` dataclass bundles all per-model info
- New `get_model_info()` calls `/api/show` per model for capabilities + context length
- `generate_litellm_config_entry()` takes `ModelMetadata`, returns dict, branches on `is_embedding`
- `update_config_file()` filters both `ollama_chat/` and `ollama/` prefixes, accepts `list[ModelMetadata]`
- `main()` loops `get_model_info()` per model, collects skipped list, prints summary
- `get_ollama_running_models()` removed
