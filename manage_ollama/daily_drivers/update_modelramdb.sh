#!/bin/bash
#
# Author: Juha Leivo
# Version: 2
# Date: 2025-04-19
#
# History
#   1 - 2025-04-19, Initial write
#   2 - 2025-04-20, Added file checks and creation of .ramdb if it doesn't exist
#                   corrected DB build logic, added logging

MODELFILE='models.txt'
MODELRAMDB='.ramdb' # Format is 'modelname ramusage', where RAM is in MB

log_message() {
    local message=$1
    if [ -t 1 ]; then
        echo "$message"
    else
        logger -t update_modelramdb.sh "$message"
    fi
}

if [ ! -f "$MODELFILE" ]; then
    log_message "Input file '$MODELFILE' does not exist."
    exit 1
fi

if [ ! -f "$MODELRAMDB" ]; then
    touch "$MODELRAMDB"
    log_message "Created new database file: $MODELRAMDB"
fi

while IFS= read -r model; do

    RAMNEED=0

    if grep -q "^$model" "$MODELRAMDB"; then
        log_message "Model '$model' already exists in the database."
        continue
    fi

    RAMNEED=$(curl -s http://ollama.intra.leivo:11434/api/chat -d "{\"model\": \"${model}\"}" > /dev/null \
                && docker exec ollama ollama ps \
                | grep "$model" | awk '{print $3*1000+500}')  # get the RAM usage of the model in MB
                                                              # add 500 MB for safety margin

    if [ -z "$RAMNEED" ]; then
        log_message "failed to load model $model"
    else
        echo "$model $RAMNEED" >> "$MODELRAMDB"
    fi

done < "$MODELFILE"
