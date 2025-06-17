#!/bin/bash
TEST_COMMAND="/usr/bin/nvidia-smi --query-compute-apps=pid,process_name --format=csv"
output=$($TEST_COMMAND)
if echo "$output" | grep -q "ollama"; then
  echo "ollama process found."
  exit 0
else
  echo "ollama process not found."
  exit 1
fi
