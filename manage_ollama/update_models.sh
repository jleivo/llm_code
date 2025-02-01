#!/bin/bash

# Log file location
LOGFILE="/var/log/ollama_model_update.log"

# Exclude file location (list models to exclude, one per line)
EXCLUDE_FILE="/srv/ollama/ollama_update_exclude.conf"

{
  echo "=========="
  echo "Update started at $(date)"

  # Create temporary files securely
  ALL_MODELS_TMP=$(mktemp /tmp/all_models.XXXXXX)
  MODELS_TO_UPDATE_TMP=$(mktemp /tmp/models_to_update.XXXXXX)

  # Get the list of models, excluding the header 'NAME'
  docker exec ollama ollama list | tail -n +2 | awk '{print $1}' > "$ALL_MODELS_TMP"

  # Exclude models listed in the exclude file
  if [ -f "$EXCLUDE_FILE" ]; then
    # Remove comments and empty lines from exclude file
    grep -vE '^\s*#|^\s*$' "$EXCLUDE_FILE" > /tmp/exclude_cleaned.$$
    # Filter out the models in the exclude list
    grep -vFxf /tmp/exclude_cleaned.$$ "$ALL_MODELS_TMP" > "$MODELS_TO_UPDATE_TMP"
    rm -f /tmp/exclude_cleaned.$$
  else
    cp "$ALL_MODELS_TMP" "$MODELS_TO_UPDATE_TMP"
  fi

  # Update each model
  while IFS= read -r model; do
    echo "Updating model: $model"
    docker exec ollama ollama pull "$model"
  done < "$MODELS_TO_UPDATE_TMP"

  # Clean up temporary files
  rm -f "$ALL_MODELS_TMP" "$MODELS_TO_UPDATE_TMP"

  echo "Update finished at $(date)"
} >> "$LOGFILE" 2>&1
