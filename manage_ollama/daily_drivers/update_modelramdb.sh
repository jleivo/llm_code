#!/bin/bash
#
# Author: Juha Leivo
# Version: 1.1
# Date: 2025-04-19
#
# History
#   1 - 2025-04-19, Initial write
#   1.1 - 2025-04-19, Added file checks and creation of .ramdb if it doesn't exist

MODELFILE='models.txt'
MODELRAMDB='.ramdb' # Format is 'modelname ramusage', where RAM is in MB

if [ ! -f "$MODELFILE" ]; then
    echo "Input file '$MODELFILE' does not exist."
    exit 1
fi

if [ ! -f "$MODELRAMDB" ]; then
    touch "$MODELRAMDB"
    echo "Created new database file: $MODELRAMDB"
fi

while IFS= read -r model; do 

    if grep -q "^$model" "$MODELRAMDB"; then
        echo "Model '$model' already exists in the database."
        continue
    fi

    echo -n "$model " >> "$MODELRAMDB"
    curl -s http://ollama.intra.leivo:11434/api/chat -d "{\"model\": \"${model}\"}" \
    && ssh ollama.intra.leivo docker exec ollama ollama ps \
    | grep "$model" | awk '{print $3*1000+500}' >> "$MODELRAMDB"

done < "$MODELFILE"