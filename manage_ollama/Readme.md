# Table of contents
- [Table of contents](#table-of-contents)
- [Ollama Model Update Script](#ollama-model-update-script)
  - [Description](#description)
  - [Usage](#usage)
  - [Configuration Files](#configuration-files)
  - [Log File](#log-file)
  - [Temporary Files](#temporary-files)
  - [Dependencies](#dependencies)
  - [Example Exclude File Content](#example-exclude-file-content)
  - [Log Sample](#log-sample)
  - [Author](#author)
- [Load Daily Driver Models Script](#load-daily-driver-models-script)
  - [Overview](#overview)
  - [Usage](#usage-1)
  - [Models Managed](#models-managed)
  - [Requirements](#requirements)
  - [Workflow](#workflow)
  - [Notes](#notes)
- [Printout Proxy Server](#printout-proxy-server)
  - [Usage](#usage-2)
  - [Dependencies](#dependencies-1)
  - [Notes](#notes-1)

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

# Printout Proxy Server

Simple debugging tool to see the messages being passed to Ollama.

This Python `printout_proxy.py` script sets up a simple HTTP proxy server that forwards requests to another server running on `localhost:11434`. It supports various HTTP methods (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS) and prints the response headers and body from the target server.

## Usage

To run the proxy server:
```bash
./printout_proxy.py
```
The proxy will listen on port 8888. Redirect your requests to http://localhost:8888 to use this proxy.

## Dependencies

- Python 3.x
- requests library (pip install requests)

## Notes

- The script excludes certain headers like 'Host', 'Content-Length', and 'Transfer-Encoding' when forwarding the request.
- The response from the target server is printed, including its status code, reason phrase, headers, and body (if any).
- Error handling is implemented to send a 500 Internal Server Error in case of exceptions.