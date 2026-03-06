# Logging Configuration for sync_ollama_litellm

This directory contains configuration files for logging the sync_ollama_litellm script events via syslog.

## Setup Instructions

1. Copy the rsyslog configuration:
   ```bash
   sudo cp rsyslog.conf /etc/rsyslog.d/sync_ollama_litellm.conf
   ```

2. Copy the logrotate configuration:
   ```bash
   sudo cp logrotate.conf /etc/logrotate.d/sync_ollama_litellm
   ```

3. Restart rsyslog service:
   ```bash
   sudo systemctl restart rsyslog
   ```

4. Ensure the log file has proper permissions:
   ```bash
   sudo touch /var/log/sync_ollama_litellm.log
   sudo chown root:root /var/log/sync_ollama_litellm.log
   sudo chmod 0644 /var/log/sync_ollama_litellm.log
   ```

## Logged Events

The script logs the following events to syslog:
- Script execution start
- Models added to the configuration
- Models removed from the configuration

All logs are written to `/var/log/sync_ollama_litellm.log` with daily rotation and compression.