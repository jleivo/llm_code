#!/usr/bin/env bash
#
# Author: Juha Leivo
# Version: 2.0.0
# Date: 2026-03-17
#
# History
#   2.0.0 - 2026-03-17,     Refactored to use container_utils shared library
#
set -euo pipefail

# shellcheck source=lib/container_utils.sh
source "$(dirname "$0")/lib/container_utils.sh"

OPEN_TERMINAL_API_KEY=$(get_secret "open_terminal_apikey")

NETWORK_NAME="open-webui-network"
WEBUI_IMG="ghcr.io/open-webui/open-webui:main"
TERMINAL_IMG="ghcr.io/open-webui/open-terminal"

if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    echo "[INFO] Creating docker network $NETWORK_NAME ..." >&2
    docker network create "$NETWORK_NAME" >/dev/null
fi

register_container "open-webui" "$WEBUI_IMG" \
    -p 127.0.0.1:4000:8080 \
    -v open-webui:/app/backend/data \
    --network="$NETWORK_NAME" \
    --restart always

register_container "open-terminal" "$TERMINAL_IMG" \
    -v open-terminal:/home/user \
    -e "OPEN_TERMINAL_API_KEY=${OPEN_TERMINAL_API_KEY}" \
    --network="$NETWORK_NAME" \
    --memory=2g \
    --cpus=2.0 \
    --restart always

run_updates
