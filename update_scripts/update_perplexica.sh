#!/usr/bin/env bash
set -euo pipefail

IMG="itzcrazykns1337/perplexica:latest"
CONTAINER_NAME="perplexica"   # adjust to the name you use

# 1️⃣ Remember the current image ID (or digest)
old_id=$(docker image inspect "$IMG" --format '{{.Id}}' 2>/dev/null || echo "")

# 2️⃣ Pull the image, capture the output
pull_out=$(docker pull "$IMG" 2>&1)   # both stdout & stderr
pull_rc=$?

if (( pull_rc != 0 )); then
    echo "❌ docker pull failed (exit $pull_rc)"
    echo "$pull_out"
    exit $pull_rc
fi

# 3️⃣ Did we actually get a newer image?
new_id=$(docker image inspect "$IMG" --format '{{.Id}}')
if [[ "$old_id" == "$new_id" && -n "$old_id" ]]; then
    echo "✅ Image already up‑to‑date."
    exit 0
fi

echo "🚀 New image detected (old=$old_id → new=$new_id)."

# 4️⃣ Stop & remove the running container (if any)
if docker ps -q -f "name=$CONTAINER_NAME" >/dev/null; then
    echo "⏹️ Stopping container $CONTAINER_NAME ..."
    docker stop "$CONTAINER_NAME"
    docker rm "$CONTAINER_NAME"
fi

# 5️⃣ (Re)run the container with the new image
# Adjust the run options to match your deployment
echo "▶️ Starting new container ..."
docker run -d --name "$CONTAINER_NAME" \
    -p 5000:3000\
    -v perplexica-data:/home/perplexica/data \
    --restart unless-stopped \
    "$IMG"

echo "✅ Done."