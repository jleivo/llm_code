#!/bin/bash

cd /srv/gpt-researcher && { echo "[ERROR] Failed to change directory to /srv/gpt-researcher"; exit 1; }
# Fetch changes from remote
git fetch origin
# Merge changes into local branch
git merge origin/master
# Rebuild containers
docker compose down
docker compose up --build -d
