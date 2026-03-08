# Ollama to LiteLLM Config Sync Script Design

## Overview
A Python script that automatically synchronizes Ollama models to LiteLLM configuration by querying Ollama's REST API endpoints and generating appropriate YAML entries.

## Requirements
- Query all models from Ollama `/api/tags` endpoint
- Retrieve context sizes from Ollama `/api/ps` endpoint for running models
- Generate LiteLLM-compatible YAML configuration entries
- Allow customizable Ollama server URL (default: http://tuprpisrvp02.intra.leivo:7900)
- Enable function calling and tools support for all models
- Set consistent keep_alive value (180m) for all models
- Handle models both with and without context size information

## Architecture

### Components
1. **API Client Module**
   - `get_all_models()` - Queries `/api/tags` endpoint
   - `get_running_models()` - Queries `/api/ps` endpoint
   - Error handling for network and API failures

2. **Model Processor Module**
   - `match_models_with_context()` - Merges model lists
   - `get_default_context_size()` - Returns fallback context size
   - Model name validation and sanitization

3. **YAML Generator Module**
   - `generate_litellm_entry()` - Creates individual model entries
   - `format_yaml_output()` - Proper YAML formatting
   - Consistent parameter application

4. **File Handler Module**
   - `read_config()` - Reads existing LiteLLM config
   - `update_config()` - Safely updates config file
   - Backup creation before modifications

### Data Flow
```
Ollama Server
├── /api/tags → All Models List
└── /api/ps → Running Models + Context Sizes
       ↓
Model Processor (Merge & Match)
       ↓
YAML Generator (Create Entries)
       ↓
File Output (Stdout or Config File)
```

## Configuration
- Default Ollama URL: `http://tuprpisrvp02.intra.leivo:7900`
- Default keep_alive: `180m`
- Default context size (fallback): `2048`
- Function calling: Enabled for all models
- Tools support: Enabled for all models

## Error Handling
- Network timeouts and connection errors
- Invalid API responses or malformed JSON
- Missing or stopped Ollama service
- File system permissions and access issues
- Empty model lists from API

## CLI Interface
```bash
python sync_ollama_to_litellm.py [OPTIONS]

Options:
  --ollama-url URL     Ollama server URL (default: http://tuprpisrvp02.intra.leivo:7900)
  --config-file PATH   LiteLLM config file path (default: litellm/config.yaml)
  --output MODE        Output mode: stdout, file, or both (default: stdout)
  --backup             Create backup before modifying config file
  --verbose            Enable detailed logging
```

## Output Format
Generated YAML entries will follow this structure:
```yaml
- model_name: "model-name:tag"
  litellm_params:
    model: "ollama_chat/model-name:tag"
    api_base: "http://tuprpisrvp02.intra.leivo:7900"
    keep_alive: "180m"
    model_info:
      supports_function_calling: true
      supports_tools: true
      max_input_tokens: 4096  # From context_size or default
```

## Implementation Considerations
- Use requests library for HTTP calls
- Use PyYAML for YAML processing
- Implement proper error messages and logging
- Add model name validation (alphanumeric + :.-)
- Handle special characters in model names
- Support both Python 3.8+ versions

## Future Enhancements
- Support for multiple Ollama servers
- Interactive mode for selective model sync
- Configuration file for script settings
- Integration with LiteLLM proxy restart
- Dry-run mode for testing