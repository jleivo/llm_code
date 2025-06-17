#!/bin/bash
#
# Script to monitor output of nvidia-smi command. The idea is to check if
# the drivers have been updated and system needs to be restarted. 
# nvidia-smi -L should fail if the driver has been updated

TEST_COMMAND="/usr/bin/nvidia-smi --query-compute-apps=pid,process_name --format=csv"

# output in failure state
# pid, process_name
# 507934, /app/.venv/bin/python3
# 509520, stablediffusionforge/bin/python
#
# output in success state
# 
#pid, process_name
#3733, /usr/bin/ollama
#3814, /usr/bin/ollama
#967, stablediffusionforge/bin/python
#2570, /app/.venv/bin/python3
#3336, /usr/bin/ollama
#3602, /usr/bin/ollama
#
# TODO:
# - proper logging and printing to screen when interactive
# - exit 1 if ollama not seen in the process list
# - exit 0 if ollama is in the process list
# $TEST_COMMAND > /var/log/nvidia_monitor.log 2>&1 