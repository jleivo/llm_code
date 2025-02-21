#!/bin/bash
#
# Author: Juha Leivo
# Version: 1
# Date: 2025-02-21
#

VERSION=0.25 # Will be updated by the script
SERVER_DIR='/srv/openhands'

function update_version() {
  # Define the repository owner and name
  OWNER="All-Hands-AI"
  REPO="OpenHands"

  # Fetch the latest release from GitHub API
  RESPONSE=$(curl -s https://api.github.com/repos/$OWNER/$REPO/releases/latest)

  # Extract the version number (tag_name) from the response
  LATEST_RELEASE_VERSION=$(echo "$RESPONSE" | jq -r '.tag_name')

  if [ "$LATEST_RELEASE_VERSION" != "null" ]; then
      echo "Current local version: $VERSION"
      echo "Latest release: $LATEST_RELEASE_VERSION"
      VERSION=$LATEST_RELEASE_VERSION
  else
      echo "Failed to retrieve the latest release information."
  fi
}

function kill_old() {
  echo -n "Stopping and removing Open hands container "
  if docker container remove -f openhands-app; then
    echo "  Success"
    echo "Starting clean up of worker containers"
    for microdoc in $(docker ps -a |grep nikolaik |awk '{print $1}'); do
      echo -n "Removing "; docker container rm -f $microdoc
    done
  else
    echo "FAILED to kill previous container!"
    exit 1
  fi
}

update_version

# Check if previous container is still up

if docker ps |grep openhands-app; then 
  kill_old
else 
  cd "$SERVER_DIR" || { echo "Failed to change to server directory"; exit 1; }
  docker run --pull=always -d \
    -e SANDBOX_RUNTIME_CONTAINER_IMAGE=docker.all-hands.dev/all-hands-ai/runtime:${VERSION}-nikolaik \
    -e LOG_ALL_EVENTS=true -v /var/run/docker.sock:/var/run/docker.sock \
    -v /srv/openhands/:/.openhands-state -p 3100:3000 --add-host host.docker.internal:host-gateway  \
    --restart unless-stopped --name openhands-app docker.all-hands.dev/all-hands-ai/openhands:${VERSION}
fi

