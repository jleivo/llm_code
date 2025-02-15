#!/bin/bash

cd /srv/gpt-researcher
# Fetch changes from remote
git fetch origin
# Merge changes into local branch
git merge origin/master
# Rebuild containers
docker compose down
docker compose up --build -d
