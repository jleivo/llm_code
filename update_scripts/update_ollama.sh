#!/bin/bash
#
# Author: Juha Leivo
# Version: 1.0.0
# Date: 2026-03-17
#
# History
#   1.0.0 - 2026-03-17,     Added official header, changed ollama GPU config to 
#                           use variable and centralized GPU config file
#

source ./GPU_config

GPU_CONFIG="--gpus=all -e CUDA_VISIBLE_DEVICES=$GPU0,$GPU2,$GPU3,$GPU4"
OLLAMA_VERSION="0.17.4"

function stop_container() {
    docker stop "$1" > /dev/null  || { echo "Stopping $1 failed?!"; }
}

function remove_container() {
    docker container rm -f "$1" > /dev/null || { echo "Clean up failed for $1!"; exit 1; }
}

function update_container() {
    docker pull -q "$1" || { echo "Updating $1 container failed!"; exit 1; }
}

function cleanup() {
    echo "Pruning containers"
    docker image prune -f
}

function ollama_start() {
    echo -n "  Starting ollama "
    docker run -d "$GPU_CONFIG" \
        -v ollama:/root/.ollama \
        -v ollama-import:/import \
        -v /srv/ollama/container_modelfiles:/modelfiles \
        -p 11434:11434 \
        -e OLLAMA_MAX_LOADED_MODELS=4 \
        -e OLLAMA_NUM_PARALLEL=4 \
        -e OLLAMA_FLASH_ATTENTION=1 \
        -e OLLAMA_KV_CACHE_TYPE=q8_0 \
        -e OLLAMA_KEEP_ALIVE=24h \
        --name ollama \
        --restart always ollama/ollama:$OLLAMA_VERSION && { echo "Updated ollama container successfully!"; return 0; }
    return 1
}

function open-webui_start() {
    echo -n "  Starting open-webui"
    docker run -d -p 3000:8080 --add-host=host.docker.internal:host-gateway -v /srv/open-webui/creds:/creds -v /srv/open-webui/creds/token.json:/app/backend/token.json -v open-webui:/app/backend/data -e AIOHTTP_CLIENT_TIMEOUT=300 --name open-webui --restart always ghcr.io/open-webui/open-webui:main &&  { echo "Updated open-webui container successfully!"; return 0; }
    return 1
}

for container in ollama open-webui; do

    echo "Removing $container current container"
    echo "  Stopping $container"
    stop_container $container

    echo "  Cleaning up the container $container"
    remove_container $container
done

echo ""
echo "Updating Ollama"
echo -n "  Pulling new container "
update_container ollama/ollama

echo ""
echo "Updating open-webui"
echo -n "  Pulling new container "
update_container ghcr.io/open-webui/open-webui:main

if ! ollama_start; then
    echo "Starting updated ollama failed..."
fi

#if ! open-webui_start; then
#    echo "Starting Open webUI failed..."
#fi


cleanup
