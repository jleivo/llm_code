# Ollama to LiteLLM Sync — Capability Detection Design

## Overview

Enhance the existing `sync_ollama_to_litellm.py` script to detect model capabilities (tools, vision, thinking, embedding) using Ollama's `/api/show` endpoint, and handle embedding models with the correct LiteLLM configuration format.

## Architecture & Data Flow

```
Ollama Server
└── /api/tags → list of model names
       ↓ (for each model)
└── /api/show → capabilities, context_length
       ↓
ModelMetadata (dataclass)
  - name: str
  - context_size: int
  - is_embedding: bool
  - supports_tools: bool
  - supports_vision: bool
  - supports_thinking: bool
       ↓
YAML Generator
  - embedding  → ollama/ prefix, mode: embedding, no tool flags
  - chat       → ollama_chat/ prefix, tool/vision/thinking flags as detected
       ↓
Config File Handler (existing logic, updated signature)
```

### Key changes to existing code

- `get_ollama_running_models()` replaced by `get_model_info(model_name)` calling `/api/show`
- `ModelMetadata` dataclass added
- `generate_litellm_config_entry()` branches on `is_embedding`
- `main()` no longer calls `/api/ps`, instead calls `get_model_info()` per model

## Capability Detection Logic

### `/api/show` response structure (relevant parts)

```json
{
  "capabilities": ["completion", "tools", "vision", "thinking", "embedding"],
  "model_info": {
    "llama.context_length": 131072
  }
}
```

### Capability mapping

| `capabilities` value | LiteLLM field |
|---|---|
| `"tools"` | `supports_function_calling: true`, `supports_tools: true` |
| `"vision"` | `supports_vision: true` |
| `"thinking"` | `supports_thinking: true` |
| `"embedding"` | use `ollama/` prefix, `mode: "embedding"`, omit tool flags |

### Context size detection

Search `model_info` for any key ending in `.context_length`, take the first match. If none found, default to `2048` and warn per model.

### When `capabilities` is absent entirely

Warn once globally (not per model), treat model as basic chat (no tools, no vision, no thinking), continue processing.

```
Warning: /api/show did not return 'capabilities' for model llama2:7b.
Defaulting to basic chat. Upgrade Ollama for accurate capability detection.
```

## YAML Output Format

### Chat model with tools and vision

```yaml
- model_name: "llama3.2-vision:11b"
  litellm_params:
    model: "ollama_chat/llama3.2-vision:11b"
    api_base: "http://tuprpisrvp02.intra.leivo:7900"
    keep_alive: "180m"
    model_info:
      supports_function_calling: true
      supports_tools: true
      supports_vision: true
      max_input_tokens: 131072
```

### Thinking model

```yaml
- model_name: "qwq:32b"
  litellm_params:
    model: "ollama_chat/qwq:32b"
    api_base: "http://tuprpisrvp02.intra.leivo:7900"
    keep_alive: "180m"
    model_info:
      supports_function_calling: true
      supports_tools: true
      supports_thinking: true
      max_input_tokens: 32768
```

### Embedding model

```yaml
- model_name: "nomic-embed-text:latest"
  litellm_params:
    model: "ollama/nomic-embed-text:latest"
    api_base: "http://tuprpisrvp02.intra.leivo:7900"
    keep_alive: "180m"
    model_info:
      mode: "embedding"
      max_input_tokens: 8192
```

Only fields that are `true` are emitted — no `supports_vision: false` clutter.

## Error Handling & Warnings

| Situation | Behaviour |
|---|---|
| `/api/show` call fails for a model | Warn, skip model, continue. Model listed in skipped summary. |
| `capabilities` field absent | Warn once globally, default to basic chat, include model. |
| Context length not in `model_info` | Default to 2048, warn per model. |
| No models from `/api/tags` | Exit with error (existing behaviour). |

### Summary output at end of run

```
Synced 12 models: 9 chat, 2 embedding
Skipped 1 model (API error): llama2:7b
```

```
Synced 11 models: 9 chat, 2 embedding
Skipped 2 models (API error): llama2:7b, codellama:13b
```
