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