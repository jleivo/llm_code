# AGENTS.md

This file contains important information for AI agents working with this repository.

## Virtual Environment

**Always use the virtual environment located in `.venv` directory at the root of the repository.**

When running Python commands, activate the virtual environment first:

```bash
# Using . command (recommended)
. .venv/bin/activate

# Or using source command
source .venv/bin/activate
```

For testing with pytest:
```bash
. .venv/bin/activate
pytest tests/ -v
```

When invoking commands in background tasks or scripts, use the full path to the virtual environment Python:

```bash
/home/juha/git/llm_code/.venv/bin/python -m pytest
```

For running scripts:
```bash
. .venv/bin/activate
python litellm/scripts/sync_ollama_to_litellm.py
```

To deactivate:
```bash
deactivate
```

## Project Structure

- `litellm/` - LiteLLM configuration and scripts
- `manage_ollama/` - Ollama management tools
- `tests/` - Test files
- `docs/plans/` - Implementation plans and design docs

## Key Commands

- Run all tests: `/home/juha/git/llm_code/.venv/bin/python -m pytest tests/ -v`
- Run specific test: `/home/juha/git/llm_code/.venv/bin/python -m pytest tests/test_sync_ollama_to_litellm.py -v`
- Sync Ollama to LiteLLM: `python litellm/scripts/sync_ollama_to_litellm.py`

## Development Workflow

1. Always activate the virtual environment before installing packages
2. Use `pip install -r requirements.txt` to install project dependencies
3. Run tests with `pytest` before committing changes
4. Follow the existing code style and patterns

## AI Agent Guidelines

- Use TDD (Test-Driven Development) for new features
- Review existing code before making changes
- Update documentation when adding new functionality
- Commit changes with clear, descriptive messages
