#!/usr/bin/env bash
# version: 1.0.0
set -euo pipefail

IMG="ghcr.io/open-webui/open-webui:main"
CONTAINER_NAME="open-webui"   # adjust to the name you use

# [1] Remember the current image ID (or digest)
old_id=$(docker image inspect "$IMG" --format '{{.Id}}' 2>/dev/null || echo "")

# [2] Pull the image, capture the output
pull_out=$(docker pull "$IMG" 2>&1)   # both stdout & stderr
pull_rc=$?

if (( pull_rc != 0 )); then
    echo "[ERROR] docker pull failed (exit $pull_rc)"
    echo "$pull_out"
    exit $pull_rc
fi

# [3] Did we actually get a newer image?
new_id=$(docker image inspect "$IMG" --format '{{.Id}}')
if [[ "$old_id" == "$new_id" && -n "$old_id" ]]; then
    echo "[OK] Image already up-to-date."
    exit 0
fi

echo "[INFO] New image detected (old=$old_id -> new=$new_id)."

# [4] Stop & remove the running container (if any)
if docker ps -q -f "name=$CONTAINER_NAME" >/dev/null; then
    echo "[STOP] Stopping container $CONTAINER_NAME ..."
    docker stop "$CONTAINER_NAME"
    docker rm "$CONTAINER_NAME"
fi

# [5] (Re)run the container with the new image
# Adjust the run options to match your deployment
echo "[RUN] Starting new container ..."
docker run -d \
    --name "$CONTAINER_NAME" \
    -p 127.0.0.1:4000:8080 \
    -v open-webui:/app/backend/data \
    --restart always \
    "$IMG"

echo "[OK] Done."
