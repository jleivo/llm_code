# Daily drivers
- [Daily drivers](#daily-drivers)
- [Daily Driver Model Loader](#daily-driver-model-loader)
  - [Dependencies](#dependencies)
  - [Configuration Files](#configuration-files)
  - [Workflow](#workflow)
  - [Logging](#logging)
  - [Configure cron job](#configure-cron-job)
- [Script: update\_modelramdb.sh](#script-update_modelramdbsh)
  - [Overview](#overview)
  - [Requirements](#requirements)
  - [Script Details](#script-details)
    - [Variables](#variables)
    - [Steps Performed](#steps-performed)
  - [Usage](#usage)


# Daily Driver Model Loader

This bash script loads models in to Ollama if GPU have enough free VRAM. Models are kept in GPU memory indefinitely until some other model requires the space. Depends on companion script to update the RAM db file.

## Dependencies

- `nvidia-smi` - To check GPU memory usage.
- `docker` - For managing Docker containers.
- `curl` - For making HTTP requests to the API endpoint that manages model loading.

NOTE! if models are not in .ramdb file they will NOT be loaded.

## Configuration Files

- **models.txt**: A file containing a list of models to be managed by this script, one per line.
- **.ramdb**: A database file in the format `modelname ramusage`, where `ramusage` is the VRAM usage of each model in MB.

## Workflow

1. Add models you want to load to models.txt file.
2. Run `update_modelramdb.sh` script. This will update `.ramdb` file with current RAM usage of models in Ollama container.
3. Run `daily_drivers.sh` script. This will load models in to Ollama if GPU have enough free VRAM.

step 3 should be in a cron job.

## Logging

All actions performed during script execution are logged into `/var/log/ollama_daily_models.log`. The logs include timestamps for each event along with a description of what happened (e.g., loading a model or skipping it).

## Configure cron job

```bash
*/1 * * * * /srv/ollama/load_daily_driver
```

# Script: update_modelramdb.sh

## Overview
The `update_modelramdb.sh` script updates the `.ramdb` database with RAM usage information for models listed in the `models.txt` file. If the model already exists in the `.ramdb`, it skips that entry and moves on to the next one.

## Requirements
- Bash shell
- Curl command-line tool (`curl`)
- SSH client

## Script Details

### Variables
- **MODELFILE**: Path to the input text file containing a list of models. Default is `models.txt`.
- **MODELRAMDB**: Name and path of the RAM database file in which the script stores model names along with their respective RAM usages. Defaults to `.ramdb`.

### Steps Performed
1. Checks if the `MODELFILE` exists.
2. If the `MODELRAMDB` does not exist, it creates a new one.
3. Iterates over each line (model) in the `MODELFILE`.
4. For each model:
   - Checks if the model already exists in the `.ramdb`.
   - If not found, adds the model to the `.ramdb` along with its RAM usage.
     - Uses `curl` to send a request to an internal API to get information about the model.
     - Uses `ssh` and Docker commands to get the current memory usage of the model container and formats it appropriately.

## Usage
1. Ensure that both `models.txt` and `.ramdb` are in the same directory as the script or provide absolute paths for these files.
2. Run the script using:
   ```bash
   ./update_modelramdb.sh