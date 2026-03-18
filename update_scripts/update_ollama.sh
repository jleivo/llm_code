#!/usr/bin/env bash
#
# Author: Juha Leivo
# Version: 2.0.0
# Date: 2026-03-17
#
# History
#   1.0.0 - 2026-03-17,     Added official header, changed ollama GPU config to
#                           use variable and centralized GPU config file
#   2.0.0 - 2026-03-17,     Refactored to use container_utils shared library,
#                           removed open-webui parts
#
set -euo pipefail

# shellcheck source=lib/container_utils.sh
source "$(dirname "$0")/lib/container_utils.sh"

source_gpu_config

OLLAMA_VERSION="0.17.4"
GPU_OPTS=(--gpus=all -e "CUDA_VISIBLE_DEVICES=$GPU0,$GPU2,$GPU3,$GPU4")

register_container "ollama" "ollama/ollama:${OLLAMA_VERSION}" \
    "${GPU_OPTS[@]}" \
    -v ollama:/root/.ollama \
    -v ollama-import:/import \
    -v /srv/ollama/container_modelfiles:/modelfiles \
    -p 11434:11434 \
    -e OLLAMA_MAX_LOADED_MODELS=4 \
    -e OLLAMA_NUM_PARALLEL=4 \
    -e OLLAMA_FLASH_ATTENTION=1 \
    -e OLLAMA_KV_CACHE_TYPE=q8_0 \
    -e OLLAMA_KEEP_ALIVE=24h \
    --restart always

run_updates
