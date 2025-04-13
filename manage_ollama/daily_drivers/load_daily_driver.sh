#!/bin/bash
#
# Author: Juha Leivo
# Version: 3
# Date: 2025-04-13
#
# History
#   1 - 2024-12, initial write
#   2 - ????-??-??, Much better version
#   3 - 2025-04-13, Complete rewrite to proper functions, external config file
#                   and complete logging

# List of models we want to maintain
MODELS=('day-qwen2.5:32b' 'day-deepseek-r1:32b' 'qwen2.5-coder:32b-base-q4_K_M')
LOGFILE='/var/log/ollama_daily_models.log'
declare -A MODEL_STATUS # Array to track model statuses

# Initialize model status array
for MODEL in "${MODELS[@]}"; do
    MODEL_STATUS[$MODEL]="not_loaded"
done

# Check which drivers are already loaded
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
    # Check total GPU memory usage across all GPUs, excluding 3060
    GPU_USAGE=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits|grep -v 12288)
    
    # Calculate total used and free memory (in MiB)
    TOTAL_USED=0
    TOTAL_FREE=0
    while IFS=',' read -r USED TOTAL; do
        (( TOTAL_USED += USED))
        (( TOTAL_FREE += TOTAL))
    done <<< "$GPU_USAGE"
    
    # Calculate required VRAM based on how many models need loading (24 GB per model)
    REQUIRED_VRAM=$((LOAD_COUNT * 23500))  # ~24 GB
    
    # Check if we have enough free VRAM to load the models
    if [ "$REQUIRED_VRAM" -le "$TOTAL_FREE" ]; then
        # Load each model that's not already loaded
        for MODEL in "${MODELS[@]}"; do
            if [ "${MODEL_STATUS[$MODEL]}" == "not_loaded" ]; then
                curl http://localhost:11434/api/generate -d "{\"model\": \"${MODEL}\", \"keep_alive\": -1}"
                curl http://localhost:11434/api/chat -d "{\"model\": \"${MODEL}\", \"keep_alive\": -1}"
            fi
        done
    else
        echo "Not enough VRAM available to load all models."
    fi
    else
    echo "All models in VRAM" >> "$LOGFILE"
fi
