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


def main():
    """Main entry point."""
    sys.exit(0)


if __name__ == '__main__':
    main()
