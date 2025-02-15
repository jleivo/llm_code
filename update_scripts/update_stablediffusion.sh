#!/bin/bash

cd /srv/stable-diffusion-webui-forge
# Fetch changes from remote
sudo -H -u stablediffusion git fetch origin || { exit 1; }
# Merge changes into local branch
sudo -H -u stablediffusion git merge origin/main || { exit 1; }
# Restart service
echo "Restarting Stable diffusion"
sudo systemctl restart stablediffusion
