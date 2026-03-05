#!/usr/bin/env python3
"""Sync Ollama models to LiteLLM config file."""

import sys
import requests
import yaml
import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any


@dataclass
class ModelMetadata:
    name: str
    context_size: int
    is_embedding: bool = False
    supports_tools: bool = False
    supports_vision: bool = False
    supports_thinking: bool = False


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

        # Ensure model_list exists and is a list
        if 'model_list' not in config or config['model_list'] is None:
            config['model_list'] = []

        # Filter out existing Ollama models from config
        # Only process dict entries, skip strings/other types
        non_ollama_models = []
        for model in config['model_list']:
            if not isinstance(model, dict):
                continue  # Skip non-dict entries (strings, etc.)
            if 'litellm_params' not in model:
                non_ollama_models.append(model)
                continue
            if not isinstance(model['litellm_params'], dict):
                continue  # Skip if litellm_params is not a dict
            if model['litellm_params'].get('model', '').startswith('ollama_chat/'):
                continue  # Skip Ollama models (will be replaced)
            non_ollama_models.append(model)

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
            print(f"Config file not found: {config_path}")
            response = input("Create it? [y/N]: ")
            if response.lower() != 'y':
                print("Aborted", file=sys.stderr)
                sys.exit(1)
            # Create empty config
            config = {'model_list': []}
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, 'w') as f:
                yaml.dump(config, f, sort_keys=False, default_flow_style=False)
            print(f"Created config file: {config_path}")

        print(f"Updating config file: {config_path}")
        update_config_file(config_path, models, args.ollama_url, model_contexts)
        print("Config file updated successfully!")


if __name__ == '__main__':
    main()
