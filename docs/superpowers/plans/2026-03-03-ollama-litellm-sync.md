# Ollama to LiteLLM Config Sync Script Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a Python script that queries Ollama's REST API and generates LiteLLM config entries for all models with context size information.

**Architecture:** Single Python script with modular functions for API calls, data processing, and YAML generation. Uses requests for HTTP calls and maintains clean separation of concerns.

**Tech Stack:** Python 3.12+, requests library, yaml library (PyYAML)

---

### Task 1: Create Project Structure

**Files:**
- Create: `litellm/scripts/sync_ollama_to_litellm.py`
- Create: `litellm/scripts/__init__.py`
- Create: `tests/test_sync_ollama_to_litellm.py`

**Step 1: Write the failing test**

```python
import pytest
from unittest.mock import patch, Mock
from litellm.scripts.sync_ollama_to_litellm import main

def test_main_function_exists():
    """Test that main function exists and can be called"""
    with patch('sys.argv', ['sync_ollama_to_litellm.py']):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_sync_ollama_to_litellm.py::test_main_function_exists -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'litellm.scripts'"

**Step 3: Create script file with minimal main function**

```python
#!/usr/bin/env python3
"""Sync Ollama models to LiteLLM config file."""

import sys


def main():
    """Main entry point."""
    sys.exit(0)


if __name__ == '__main__':
    main()
```

**Step 4: Create __init__.py files**

```python
# litellm/scripts/__init__.py
"""Scripts for LiteLLM configuration management."""
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_sync_ollama_to_litellm.py::test_main_function_exists -v`
Expected: PASS

**Step 6: Commit**

```bash
git add litellm/scripts/sync_ollama_to_litellm.py litellm/scripts/__init__.py tests/test_sync_ollama_to_litellm.py
git commit -m "feat: create project structure for ollama-litellm sync script"
```

---

### Task 2: Implement Ollama API Client

**Files:**
- Modify: `litellm/scripts/sync_ollama_to_litellm.py`
- Test: `tests/test_sync_ollama_to_litellm.py`

**Step 1: Write failing tests for API functions**

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sync_ollama_to_litellm.py::test_get_ollama_models_success tests/test_sync_ollama_to_litellm.py::test_get_ollama_models_failure -v`
Expected: FAIL with "ImportError: cannot import name 'get_ollama_models'"

**Step 3: Implement API client functions**

```python
#!/usr/bin/env python3
"""Sync Ollama models to LiteLLM config file."""

import sys
import requests
from typing import List


def get_ollama_models(ollama_url: str) -> List[str]:
    """Get list of models from Ollama API.

    Args:
        ollama_url: Base URL of Ollama server

    Returns:
        List of model names
    """
    try:
        response = requests.get(f"{ollama_url}/api/tags", timeout=30)
        response.raise_for_status()
        data = response.json()
        return [model["name"] for model in data.get("models", [])]
    except Exception as e:
        print(f"Error fetching models from Ollama: {e}", file=sys.stderr)
        return []


def get_ollama_running_models(ollama_url: str) -> dict:
    """Get running models with context sizes from Ollama API.

    Args:
        ollama_url: Base URL of Ollama server

    Returns:
        Dict mapping model names to context sizes
    """
    try:
        response = requests.get(f"{ollama_url}/api/ps", timeout=30)
        response.raise_for_status()
        data = response.json()
        return {
            model["name"]: model.get("context_size", 2048)
            for model in data.get("models", [])
        }
    except Exception as e:
        print(f"Error fetching running models from Ollama: {e}", file=sys.stderr)
        return {}


def main():
    """Main entry point."""
    sys.exit(0)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sync_ollama_to_litellm.py::test_get_ollama_models_success tests/test_sync_ollama_to_litellm.py::test_get_ollama_models_failure -v`
Expected: PASS

**Step 5: Commit**

```bash
git add litellm/scripts/sync_ollama_to_litellm.py tests/test_sync_ollama_to_litellm.py
git commit -m "feat: implement ollama api client functions"
```

---

### Task 3: Implement YAML Generation

**Files:**
- Modify: `litellm/scripts/sync_ollama_to_litellm.py`
- Test: `tests/test_sync_ollama_to_litellm.py`

**Step 1: Write failing tests for YAML generation**

```python
def test_generate_litellm_config_entry():
    """Test generation of LiteLLM config entry"""
    from litellm.scripts.sync_ollama_to_litellm import generate_litellm_config_entry

    result = generate_litellm_config_entry("llama2:7b", "http://localhost:11434", 4096)
    expected = """- model_name: "llama2:7b"
  litellm_params:
    model: "ollama_chat/llama2:7b"
    api_base: "http://localhost:11434"
    keep_alive: "180m"
    model_info:
      supports_function_calling: true
      supports_tools: true
      max_input_tokens: 4096"""

    assert result.strip() == expected.strip()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_sync_ollama_to_litellm.py::test_generate_litellm_config_entry -v`
Expected: FAIL with "ImportError: cannot import name 'generate_litellm_config_entry'"

**Step 3: Implement YAML generation function**

```python
def generate_litellm_config_entry(model_name: str, api_base: str, context_size: int) -> str:
    """Generate a LiteLLM config entry for a model.

    Args:
        model_name: Name of the model
        api_base: Ollama API base URL
        context_size: Context size in tokens

    Returns:
        YAML string for the config entry
    """
    return f"""- model_name: "{model_name}"
  litellm_params:
    model: "ollama_chat/{model_name}"
    api_base: "{api_base}"
    keep_alive: "180m"
    model_info:
      supports_function_calling: true
      supports_tools: true
      max_input_tokens: {context_size}"""


def main():
    """Main entry point."""
    sys.exit(0)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_sync_ollama_to_litellm.py::test_generate_litellm_config_entry -v`
Expected: PASS

**Step 5: Commit**

```bash
git add litellm/scripts/sync_ollama_to_litellm.py tests/test_sync_ollama_to_litellm.py
git commit -m "feat: implement yaml generation function"
```

---

### Task 4: Implement Config File Handling

**Files:**
- Modify: `litellm/scripts/sync_ollama_to_litellm.py`
- Test: `tests/test_sync_ollama_to_litellm.py`
- Create: `tests/fixtures/test_config.yaml`

**Step 1: Create test fixture**

```yaml
# tests/fixtures/test_config.yaml
# config.yaml – Litellm proxy
model_list:
  # Existing Ollama models
  - model_name: "existing-model"
    litellm_params:
      model: "ollama_chat/existing-model"
      api_base: "http://localhost:11434"
      keep_alive: "180m"
      model_info:
        supports_function_calling: true
        supports_tools: true

  # Anthropic
  - model_name: "claude-sonnet-4-6"
    litellm_params:
      model: "anthropic/claude-sonnet-4-6"
      api_key: "os.environ/ANTHROPIC_API_KEY"

router_settings:
  fallbacks: [{"kimi-k2": ["ollama-kimi-k2"]}]
```

**Step 2: Write failing tests for config file handling**

```python
import yaml
from pathlib import Path


def test_update_config_file():
    """Test updating config file with new models"""
    from litellm.scripts.sync_ollama_to_litellm import update_config_file

    # Create temp config file
    test_config = Path("tests/fixtures/test_config.yaml")
    temp_config = Path("tests/fixtures/temp_config.yaml")
    temp_config.write_text(test_config.read_text())

    try:
        new_models = ["llama2:7b", "mistral:7b"]
        model_contexts = {"llama2:7b": 4096, "mistral:7b": 8192}

        update_config_file(temp_config, new_models, model_contexts, "http://localhost:11434")

        # Verify the updated config
        with open(temp_config) as f:
            config = yaml.safe_load(f)

        model_names = [m["model_name"] for m in config["model_list"]]
        assert "llama2:7b" in model_names
        assert "mistral:7b" in model_names
        assert "existing-model" in model_names  # Original should be preserved
        assert "claude-sonnet-4-6" in model_names  # Non-Ollama should be preserved
    finally:
        if temp_config.exists():
            temp_config.unlink()
```

**Step 3: Run test to verify it fails**

Run: `pytest tests/test_sync_ollama_to_litellm.py::test_update_config_file -v`
Expected: FAIL with "ImportError: cannot import name 'update_config_file'"

**Step 4: Implement config file handling functions**

```python
import yaml
from pathlib import Path
from typing import List, Dict


def update_config_file(config_path: Path, models: List[str], model_contexts: Dict[str, int], api_base: str):
    """Update LiteLLM config file with new Ollama models.

    Args:
        config_path: Path to config file
        models: List of model names to add
        model_contexts: Dict mapping model names to context sizes
        api_base: Ollama API base URL
    """
    # Load existing config
    with open(config_path) as f:
        config = yaml.safe_load(f) or {"model_list": []}

    # Remove existing Ollama models (identified by ollama_chat prefix)
    config["model_list"] = [
        m for m in config["model_list"]
        if not m.get("litellm_params", {}).get("model", "").startswith("ollama_chat/")
    ]

    # Add new Ollama models
    for model in models:
        context_size = model_contexts.get(model, 2048)  # Default to 2048 if not found
        entry_yaml = generate_litellm_config_entry(model, api_base, context_size)
        entry = yaml.safe_load(entry_yaml)
        config["model_list"].append(entry)

    # Write updated config
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def main():
    """Main entry point."""
    sys.exit(0)
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_sync_ollama_to_litellm.py::test_update_config_file -v`
Expected: PASS

**Step 6: Commit**

```bash
git add litellm/scripts/sync_ollama_to_litellm.py tests/test_sync_ollama_to_litellm.py tests/fixtures/test_config.yaml
git commit -m "feat: implement config file handling"
```

---

### Task 5: Implement Main Function with CLI

**Files:**
- Modify: `litellm/scripts/sync_ollama_to_litellm.py`
- Test: `tests/test_sync_ollama_to_litellm.py`

**Step 1: Write failing test for main functionality**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_sync_ollama_to_litellm.py::test_main_integration -v`
Expected: FAIL with "ImportError: cannot import name 'main' (updated version)"

**Step 3: Implement main function with CLI argument parsing**

```python
import argparse


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

    # Get models from Ollama
    print(f"Fetching models from {args.ollama_url}...")
    models = get_ollama_models(args.ollama_url)
    if not models:
        print("No models found or error connecting to Ollama", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(models)} models: {', '.join(models)}")

    # Get running models with context sizes
    print("Fetching running model details...")
    running_models = get_ollama_running_models(args.ollama_url)

    # Build context size mapping
    model_contexts = {}
    for model in models:
        if model in running_models:
            model_contexts[model] = running_models[model]
        else:
            print(f"Warning: Context size not found for {model}, using default 2048")
            model_contexts[model] = 2048

    # Output results
    if args.output == 'stdout':
        # Print to stdout
        for model in models:
            context_size = model_contexts[model]
            entry = generate_litellm_config_entry(model, args.ollama_url, context_size)
            print(entry)
            print()  # Blank line between entries
    else:
        # Update config file
        config_path = Path(args.config_file)
        if not config_path.exists():
            print(f"Config file not found: {config_path}", file=sys.stderr)
            sys.exit(1)

        print(f"Updating config file: {config_path}")
        update_config_file(config_path, models, model_contexts, args.ollama_url)
        print("Config file updated successfully!")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_sync_ollama_to_litellm.py::test_main_integration -v`
Expected: PASS

**Step 5: Add script shebang and make executable**

Add to top of file:
```python
#!/usr/bin/env python3
```

Then make executable:
```bash
chmod +x litellm/scripts/sync_ollama_to_litellm.py
```

**Step 6: Commit**

```bash
git add litellm/scripts/sync_ollama_to_litellm.py tests/test_sync_ollama_to_litellm.py
git commit -m "feat: implement main function with CLI interface"
```

---

### Task 6: Add Requirements and Documentation

**Files:**
- Create: `litellm/scripts/requirements.txt`
- Create: `litellm/scripts/README.md`

**Step 1: Create requirements file**

```txt
requests>=2.28.0
PyYAML>=6.0
```

**Step 2: Create README**

```markdown
# Ollama to LiteLLM Config Sync Script

This script automatically syncs models from your Ollama server to your LiteLLM configuration file.

## Features

- Queries Ollama's REST API for all available models
- Fetches context sizes from running models
- Generates properly formatted LiteLLM config entries
- Updates config file in-place or outputs to stdout
- Preserves non-Ollama models in the config

## Usage

Basic usage with default settings:
```bash
python sync_ollama_to_litellm.py
```

Custom Ollama server and config file:
```bash
python sync_ollama_to_litellm.py \
  --ollama-url http://localhost:11434 \
  --config-file /path/to/config.yaml
```

Output to stdout for review:
```bash
python sync_ollama_to_litellm.py --output stdout
```

## Options

- `--ollama-url`: Ollama server URL (default: http://tuprpisrvp02.intra.leivo:7900)
- `--config-file`: Path to LiteLLM config file (default: litellm/config.yaml)
- `--output`: Output destination - 'file' or 'stdout' (default: file)

## Installation

Install dependencies:
```bash
pip install -r requirements.txt
```
```

**Step 3: Commit**

```bash
git add litellm/scripts/requirements.txt litellm/scripts/README.md
git commit -m "docs: add requirements and documentation"
```

---

### Task 7: Run Full Integration Test

**Files:**
- Test: All existing tests

**Step 1: Run all tests**

```bash
pytest tests/test_sync_ollama_to_litellm.py -v
```
Expected: All tests PASS

**Step 2: Test script manually with --help**

```bash
python litellm/scripts/sync_ollama_to_litellm.py --help
```
Expected: Shows help message with all options

**Step 3: Test with stdout output (if Ollama is accessible)**

```bash
python litellm/scripts/sync_ollama_to_litellm.py --output stdout
```
Expected: Outputs YAML entries for all Ollama models

**Step 4: Commit final version**

```bash
git add -A
git commit -m "feat: complete ollama to litellm sync script with tests"
```

---

## Summary

The script is now complete with:
- Full API integration with Ollama (/api/tags and /api/ps endpoints)
- Context size detection and inclusion
- YAML generation for LiteLLM config format
- Config file updating while preserving non-Ollama models
- Command-line interface with flexible options
- Comprehensive test coverage
- Documentation and requirements

**Usage:**
```bash
# Basic usage
python litellm/scripts/sync_ollama_to_litellm.py

# Preview changes
python litellm/scripts/sync_ollama_to_litellm.py --output stdout

# Custom server and config
python litellm/scripts/sync_ollama_to_litellm.py \
  --ollama-url http://localhost:11434 \
  --config-file /custom/path/config.yaml
```