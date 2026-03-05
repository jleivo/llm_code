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
