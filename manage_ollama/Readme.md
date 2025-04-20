# Scripts to manage Ollama

- [Scripts to manage Ollama](#scripts-to-manage-ollama)
- [Ollama Model Update](#ollama-model-update)
  - [Description](#description)
- [Load Daily Driver Models](#load-daily-driver-models)
  - [Description](#description-1)

# Ollama Model Update

## Description

This Bash script updates models in the `ollama` container, excluding those listed in an exclusion file.

[Documentation](docs/update_models.md)


# Load Daily Driver Models

## Description

This bash script loads models in to Ollama if GPU have enough free VRAM. Models are kept in GPU memory indefinitely until some other model requires the space.

[Documentation](docs/daily_drivers.md)