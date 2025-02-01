# Ollama Model Update Script

## Description
This Bash script updates models in the `ollama` container, excluding those listed in an exclusion file.

## Usage
Run the script to update all non-excluded models:
```bash
./update_ollama_models.sh
```

## Configuration Files
- **Exclude File**: `/srv/ollama/ollama_update_exclude.conf`
  - List models to exclude from updates, one per line.
  - Comments start with `#` and are ignored.

## Log File
- **Log Location**: `/var/log/ollama_model_update.log`
  - Contains logs of the update process including timestamps.

## Temporary Files
Temporary files are created securely in `/tmp`, cleaned up after execution.

## Dependencies
- Docker must be installed and accessible.
- `ollama` container should be running.

## Example Exclude File Content
```plaintext
# Models to exclude from updates
model1
model2
```

## Log Sample
```plaintext
==========
Update started at Thu Oct 5 14:30:00 UTC 2023
Updating model: modelA
Updating model: modelB
Update finished at Thu Oct 5 14:30:05 UTC 2023
```

## Author
Juha Leivo

# Load Daily Driver Models Script

## Overview
This script, `load_daily_driver_v2.sh`, automates the process of loading specific machine learning models into memory using Docker and Ollama. It checks if the required models are already loaded and calculates available GPU VRAM to determine if additional models can be loaded.

## Usage
1. Ensure you have Docker installed and running.
2. Run the script with `bash load_daily_driver_v2.sh`.

## Models Managed
- `day-qwen2.5:32b`
- `day-deepseek-r1:32b`

## Requirements
- NVIDIA GPU (excluding 3060)
- Docker and Ollama installed
- `nvidia-smi` for VRAM monitoring

## Workflow
1. Initializes the status of each model.
2. Checks which models are already loaded via Docker.
3. Calculates available VRAM across all GPUs, excluding 3060s.
4. Loads models if there is enough free VRAM (~24 GB per model).
5. Outputs a message if not enough VRAM is available.

## Notes
- The script assumes the Ollama service is running and accessible at `localhost:11434`.