#!/bin/bash
# List of drivers we want to maintain
DRIVERS=('day-qwen2.5:32b' 'day-deepseek-r1:32b')
# Array to track model statuses
declare -A MODEL_STATUS

# Initialize model status array
for DRIVER in "${DRIVERS[@]}"; do
    MODEL_STATUS[$DRIVER]="not_loaded"
done

# Check which drivers are already loaded
LOADED_DRIVERS=$(docker exec -it ollama ollama ps | awk '{print $1}' | tail -n +2)
for LOADED_MODEL in ${LOADED_DRIVERS}; do
    for DRIVER in "${DRIVERS[@]}"; do
        if [[ "$LOADED_MODEL" == *"$DRIVER"* ]]; then
            MODEL_STATUS[$DRIVER]="loaded"
        fi
    done
done

# Determine how many models need loading
LOAD_COUNT=0
for DRIVER in "${DRIVERS[@]}"; do
    if [ "${MODEL_STATUS[$DRIVER]}" == "not_loaded" ]; then
        let LOAD_COUNT+=1
    fi
done

if [ "$LOAD_COUNT" -gt 0 ]; then
    # Check total GPU memory usage across all GPUs, excluding 3060
    GPU_USAGE=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits|grep -v 12288)
    
    # Calculate total used and free memory (in MiB)
    TOTAL_USED=0
    TOTAL_FREE=0
    while IFS=',' read -r USED TOTAL; do
        let TOTAL_USED+=$((USED))
        let TOTAL_FREE+=$((TOTAL))
    done <<< "$GPU_USAGE"
    
    # Calculate required VRAM based on how many models need loading (24 GB per model)
    REQUIRED_VRAM=$((LOAD_COUNT * 23500))  # ~24 GB
    
    # Check if we have enough free VRAM to load the models
    if [ "$REQUIRED_VRAM" -le "$TOTAL_FREE" ]; then
        # Load each model that's not already loaded
        for DRIVER in "${DRIVERS[@]}"; do
            if [ "${MODEL_STATUS[$DRIVER]}" == "not_loaded" ]; then
                curl http://localhost:11434/api/generate -d "{\"model\": \"${DRIVER}\", \"keep_alive\": -1}"
                curl http://localhost:11434/api/chat -d "{\"model\": \"${DRIVER}\", \"keep_alive\": -1}"
            fi
        done
    else
        echo "Not enough VRAM available to load models."
    fi
fi
