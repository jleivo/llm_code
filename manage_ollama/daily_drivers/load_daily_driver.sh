#!/bin/bash
#
# Author: Juha Leivo
# Version: 5
# Date: 2025-04-20
#
# History
#   1 - 2024-12, initial write
#   2 - ????-??-??, Much better version
#   3 - 2025-04-13, Complete rewrite to proper functions, external config file
#                   and complete logging
#   4 - 2025-04-19, Load models from a file, load them one by one if there is 
#                   enough VRAM available, use MODELRAMDB
#   5 - 2025-04-20, More functions, more variables

LOGFILE='/var/log/ollama_daily_models.log'
MODELRAMDB='.ramdb' # Format is 'modelname ramusage', where RAM is in MB
MODELSTOLOAD='models.txt'

################### Don't touch ###############
MODELS=()
declare -A MODEL_STATUS # Array to track model statuses
TOTAL_FREE=0

############### FUNCTIONS ###############

function init() {
    # read the list of models from a file
    while read -r line; do
        MODELS+=("$line")
    done < "$MODELSTOLOAD"

    # Initialize model status array
    for MODEL in "${MODELS[@]}"; do
        MODEL_STATUS[$MODEL]="not_loaded"
    done
}

function check_gpu_ram_usage {

    # Check total GPU memory usage across all GPUs, excluding 3060
    # 3060 is excluded based on its VRAM amount (12288)
    GPU_USAGE=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits|grep -v 12288)
    
    # Calculate total used and free memory (in MiB)
    TOTAL_USED=0
    TOTAL_FREE=0
    while IFS=',' read -r USED TOTAL; do
        (( TOTAL_USED += USED))
        (( TOTAL_FREE += TOTAL))
    done <<< "$GPU_USAGE"
    (( TOTAL_FREE -= TOTAL_USED ))
}

########### END FUNCTIONS #############

init

# Check which models are already loaded
LOADED_MODELS=$(docker exec -it ollama ollama ps | awk '{print $1}' | tail -n +2)
for LOADED_MODEL in ${LOADED_MODELS}; do
    for MODEL in "${MODELS[@]}"; do
        if [[ "$LOADED_MODEL" == *"$MODEL"* ]]; then
            MODEL_STATUS[$MODEL]="loaded"
        fi
    done
done

# Determine how many models need loading
LOAD_COUNT=0
for MODEL in "${MODELS[@]}"; do
    if [ "${MODEL_STATUS[$MODEL]}" == "not_loaded" ]; then
        (( LOAD_COUNT++)) || true
    fi
done

if [ "$LOAD_COUNT" -gt 0 ]; then
    
    check_gpu_ram_usage
    REQUIRED_VRAM=0

    # Check which models are not loaded and load the model if there is enough free VRAM. 
    # the required amount of VRAM is in MODELRAMDB file.
    for MODEL in "${MODELS[@]}"; do
        if [ "${MODEL_STATUS[$MODEL]}" == "not_loaded" ]; then
        # check if RAMDB has the model in it. If not, skip loading this model.
            if ! grep -q "${MODEL}" $MODELRAMDB; then
                echo "$(date): Skipping model $MODEL because it is not listed in MODELRAMDB" >> "$LOGFILE"
                continue
            fi
            REQUIRED_VRAM=$(grep "${MODEL}" $MODELRAMDB |awk '{print $2}')

            if [ "$REQUIRED_VRAM" -le "$TOTAL_FREE" ]; then
                curl http://localhost:11434/api/generate -d "{\"model\": \"${MODEL}\", \"keep_alive\": -1}"
                curl http://localhost:11434/api/chat -d "{\"model\": \"${MODEL}\", \"keep_alive\": -1}"
                echo "$(date): Loaded model $MODEL, required RAM: ${REQUIRED_VRAM} MB" >> "$LOGFILE"
                check_gpu_ram_usage
            else
                echo "$(date): Not loading model $MODEL, required RAM: ${REQUIRED_VRAM} MB, free RAM: ${TOTAL_FREE} MB" >> "$LOGFILE"
            fi
        fi
    done
    
fi
