# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working with Python

This project uses a virtual environment at `.venv/`:

```bash
# Create virtual environment (one-time)
python3 -m venv .venv

# Activate and install dependencies
. .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Or use the absolute path to the venv binaries:

```bash
# Install or update dependencies
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-dev.txt

# Run tests
.venv/bin/python -m pytest

# Run a specific test file
.venv/bin/python -m pytest tests/test_host_manager.py
.venv/bin/python -m pytest tests/test_main.py

# Run with verbose output
.venv/bin/python -m pytest -v

# Run with debug logging
.venv/bin/python main.py --debug

# Start the proxy server
.venv/bin/python main.py
```

## Architecture

This is a Python FastAPI-based proxy server for Ollama that:

1. **Hosts multiple Ollama instances** - Configured via `config.json` with VRAM tracking and host priority
2. **Monitors host status** - Background thread updates host availability, loaded models, and VRAM usage every 60 seconds
3. **Routes requests intelligently**:
   - Selects host based on priority (lower number = higher priority)
   - Among hosts with same priority, prefers host with most free VRAM
   - Model loading priority: loaded in VRAM > available on disk > need to pull
   - Respects host priority configuration in `config.json`
4. **Maintains session stickiness** - Sessions identified by client IP + model + first message content, with 15-minute timeout
5. **Auto-pulls models** - If no host has the requested model, automatically pulls it to the best available host
6. **Aggregated model endpoints** - `/api/tags` and `/api/ps` return combined, deduplicated model lists from all hosts

## Key Files

- `main.py` - FastAPI application with proxy routing, session management, request forwarding, and aggregated model endpoints
- `host_manager.py` - HostManager class for managing Ollama hosts and selection logic
- `tests/` - pytest test suite mocking all external API calls
- `config.json.example` - Configuration template

## Configuration

The proxy reads from `config.json` with this structure:
```json
{
  "server": {"port": 8080},
  "hosts": [
    {"url": "http://host:11434", "total_vram_mb": 16384, "priority": 1}
  ]
}
```

## Logging

Logs to console, `proxy.log` file, and syslog (LOG_LOCAL7 facility). See `LOGGING.md` for rsyslog configuration.
