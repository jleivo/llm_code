#!/usr/bin/env bash
# version: 1.1.0
set -euo pipefail

# Load configuration from user's home directory
CONFIG_DIR="${HOME}/.openterminal"
CONFIG_FILE="${CONFIG_DIR}/.env"

if [[ -f "$CONFIG_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$CONFIG_FILE"
fi

OPEN_TERMINAL_API_KEY="${OPEN_TERMINAL_API_KEY:-}"

if [[ -z "$OPEN_TERMINAL_API_KEY" ]]; then
    echo "[ERROR] OPEN_TERMINAL_API_KEY not set."
    echo "[ERROR] Please create $CONFIG_FILE with:"
    echo "  OPEN_TERMINAL_API_KEY=your-secret-key"
    exit 1
fi

# Network configuration
NETWORK_NAME="open-webui-network"

# Open-WebUI configuration
WEBUI_IMG="ghcr.io/open-webui/open-webui:main"
WEBUI_CONTAINER_NAME="open-webui"

# Open-Terminal configuration
TERMINAL_IMG="ghcr.io/open-webui/open-terminal"
TERMINAL_CONTAINER_NAME="open-terminal"

# Ensure the network exists
if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    echo "[INFO] Creating docker network $NETWORK_NAME ..."
    docker network create "$NETWORK_NAME"
fi

# Helper function to update a container
update_container() {
    local img=$1
    local container_name=$2
    shift 2
    local docker_opts=("$@")

    # Remember the current image ID
    local old_id
    old_id=$(docker image inspect "$img" --format '{{.Id}}' 2>/dev/null || echo "")

    # Pull the image
    local pull_out
    pull_out=$(docker pull "$img" 2>&1)
    local pull_rc=$?

    if (( pull_rc != 0 )); then
        echo "[ERROR] docker pull failed for $img (exit $pull_rc)"
        echo "$pull_out"
        return $pull_rc
    fi

    # Check if we got a newer image
    local new_id
    new_id=$(docker image inspect "$img" --format '{{.Id}}')
    local image_updated=false
    
    if [[ "$old_id" == "$new_id" && -n "$old_id" ]]; then
        echo "[OK] Image $img already up-to-date."
    else
        echo "[INFO] New image detected for $container_name (old=$old_id -> new=$new_id)."
        image_updated=true
    fi

    # Check if container is running
    local container_running=false
    if [[ -n "$(docker ps -q -f "name=$container_name" 2>/dev/null)" ]]; then
        container_running=true
    fi

    # Only restart if image was updated OR container is not running
    if [[ "$image_updated" == true ]] || [[ "$container_running" == false ]]; then
        # Stop & remove the running container (if it exists)
        if docker inspect "$container_name" >/dev/null 2>&1; then
            echo "[STOP] Stopping container $container_name ..."
            docker stop "$container_name" 2>/dev/null || true
            docker rm "$container_name" 2>/dev/null || true
        fi

        # Run the container with the new image
        echo "[RUN] Starting new container $container_name ..."
        docker run -d \
            --name "$container_name" \
            "${docker_opts[@]}" \
            "$img"

        echo "[OK] $container_name started."
    else
        echo "[OK] Container $container_name is running and up-to-date."
    fi
}

# Update open-webui
update_container "$WEBUI_IMG" "$WEBUI_CONTAINER_NAME" \
    -p 127.0.0.1:4000:8080 \
    -v open-webui:/app/backend/data \
    --network="$NETWORK_NAME" \
    --restart always

# Update open-terminal
update_container "$TERMINAL_IMG" "$TERMINAL_CONTAINER_NAME" \
    -v open-terminal:/home/user \
    -e OPEN_TERMINAL_API_KEY="$OPEN_TERMINAL_API_KEY" \
    --network="$NETWORK_NAME" \
    --memory=2g \
    --cpus=2.0 \
    --restart always

echo "[OK] Done."
