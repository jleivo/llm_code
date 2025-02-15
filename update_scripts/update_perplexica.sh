#!/bin/bash

cd /srv/Perplexica
# Fetch changes from remote
git fetch origin
# Merge changes into local branch
git merge origin/master
# Handle merge conflicts if any
if [ $? -ne 0 ]; then   echo "Merge conflict detected. Please resolve manually.";  exit 1; fi
# Commit the merge
git commit -m "Merge remote changes" || true
# Rebuild containers
docker compose down
docker compose up --build -d
