#!/bin/bash

# Function to handle output
handle_output() {
  if [ -t 1 ]; then
    # Interactive: echo the message
    echo "$1"
  else
    # Non-interactive: use logger
    logger -t nvidia_monitor "$1"
  fi
}

TEST_COMMAND="/usr/bin/nvidia-smi --query-compute-apps=pid,process_name --format=csv"

output=$($TEST_COMMAND)
if echo "$output" | grep -q "ollama"; then
  handle_output "ollama process found."
  exit 0
else
  handle_output "ollama process not found."
  exit 1
fi
