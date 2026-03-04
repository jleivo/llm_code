#!/usr/bin/env python3
"""Sync Ollama models to LiteLLM config file."""

import sys
import requests
import yaml
from typing import List, Dict, Any


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


def generate_litellm_config_entry(model_name: str, api_base: str, context_size: int) -> str:
    """Generate a LiteLLM config entry for an Ollama model in YAML format.

    Args:
        model_name: Name of the Ollama model
        api_base: Base URL of Ollama server
        context_size: Maximum context size for the model

    Returns:
        YAML formatted config entry as a string
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


def update_config_file(config_path: str, ollama_models: list[str], api_base: str, running_models: dict[str, int]) -> bool:
    """Update LiteLLM config file with Ollama models.

    Args:
        config_path: Path to the LiteLLM config file
        ollama_models: List of available Ollama models
        api_base: Base URL of Ollama server
        running_models: Dict of running models with their context sizes

    Returns:
        True if successful, False otherwise
    """
    try:
        # Load existing config
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        except FileNotFoundError:
            config = {'model_list': []}

        # Ensure model_list exists
        if 'model_list' not in config:
            config['model_list'] = []

        # Filter out existing Ollama models from config
        non_ollama_models = [
            model for model in config['model_list']
            if not (isinstance(model, dict) and
                   'litellm_params' in model and
                   isinstance(model['litellm_params'], dict) and
                   model['litellm_params'].get('model', '').startswith('ollama_chat/'))
        ]

        # Generate new config entries for Ollama models
        new_ollama_entries = []
        for model_name in ollama_models:
            # Use context size from running models if available, otherwise default
            context_size = running_models.get(model_name, 2048)

            # Create the config entry as a dict
            entry = {
                'model_name': model_name,
                'litellm_params': {
                    'model': f'ollama_chat/{model_name}',
                    'api_base': api_base,
                    'keep_alive': '180m',
                    'model_info': {
                        'supports_function_calling': True,
                        'supports_tools': True,
                        'max_input_tokens': context_size
                    }
                }
            }
            new_ollama_entries.append(entry)

        # Combine non-Ollama models with new Ollama models
        config['model_list'] = non_ollama_models + new_ollama_entries

        # Write updated config back to file
        with open(config_path, 'w') as f:
            yaml.dump(config, f, sort_keys=False, default_flow_style=False)

        return True
    except Exception as e:
        print(f"Error updating config file: {e}", file=sys.stderr)
        return False


def main():
    """Main entry point."""
    sys.exit(0)


if __name__ == '__main__':
    main()
