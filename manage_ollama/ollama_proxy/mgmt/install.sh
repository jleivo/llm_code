#!/bin/bash
# Installation script for Ollama Proxy

# Stop on any error
set -e

echo "Ollama Proxy Installer"
echo "======================"
echo "This script will install the Ollama Proxy and its dependencies."
echo "It will create a config.json if it doesn't exist, and can optionally create a systemd service."
echo ""

# --- Config File ---
CONFIG_FILE=${CONFIG_FILE:-"config.json"}

if ! command -v jq &> /dev/null
then
    echo "jq is not installed. Please install jq to validate the configuration."
    exit 0
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Creating default configuration file..."
    
    # Initialize config with empty hosts array
    echo '{"hosts": []}' > "$CONFIG_FILE"
    
    current_priority=1
    while true; do
        read -rp "Enter Ollama server URL (default: http://localhost:11434): " OLLAMA_URL
        OLLAMA_URL=${OLLAMA_URL:-http://localhost:11434}
        read -rp "Enter total VRAM in MB (default: 8192): " TOTAL_VRAM_MB
        TOTAL_VRAM_MB=${TOTAL_VRAM_MB:-8192}
        read -rp "Enter priority for the host (default: $current_priority): " PRIORITY
        PRIORITY=${PRIORITY:-$current_priority}
        
        # Create a new host entry
        NEW_HOST=$(cat << EOF
{
  "url": "$OLLAMA_URL",
  "total_vram_mb": $TOTAL_VRAM_MB,
  "priority": $PRIORITY
}
EOF
)
        # Add the host to the config file using jq to avoid fragile sed operations.
        # Use a temporary file to write the updated JSON atomically.
        tmpfile=$(mktemp)
        # jq accepts a JSON value via --argjson; pass the NEW_HOST string as JSON.
        if ! jq --argjson host "$NEW_HOST" '.hosts += [$host]' "$CONFIG_FILE" > "$tmpfile"; then
            rm -f "$tmpfile"
            echo "ERROR: Failed to update configuration file with jq."
            exit 1
        fi
        if ! mv "$tmpfile" "$CONFIG_FILE"; then
            rm -f "$tmpfile"
            echo "ERROR: Failed to write updated configuration file."
            exit 1
        fi
        
        read -p "Add another host? (y/N) " -n 1 -r
        echo # Move to new line
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            break
        fi
        ((current_priority++))
    done
    
    # Format the config file nicely
    if ! jq . "$CONFIG_FILE" > "$CONFIG_FILE.tmp"; then
        rm -f "$CONFIG_FILE.tmp"
        echo "ERROR: Failed to format configuration file."
        exit 1
    fi
    if ! mv "$CONFIG_FILE.tmp" "$CONFIG_FILE"; then
        rm -f "$CONFIG_FILE.tmp"
        echo "ERROR: Failed to update configuration file."
        exit 1
    fi
    
    echo "'$CONFIG_FILE' created. Please edit it to match your environment."
else
    echo "Configuration file '$CONFIG_FILE' already exists."
fi

# --- Validate Config ---
echo "Validating configuration..."

# 1. Check for valid JSON
if ! jq . "$CONFIG_FILE" > /dev/null; then
    echo "ERROR: '$CONFIG_FILE' is not a valid JSON file."
    exit 1
fi

# 2. Check for 'hosts' array and required keys
if ! jq -e '.hosts and (.hosts | all(.url and .total_vram_mb))' "$CONFIG_FILE" > /dev/null; then
    echo "ERROR: '$CONFIG_FILE' is missing required structure."
    echo "It must contain a 'hosts' array, and each host object must have 'url' and 'total_vram_mb' keys."
    exit 1
fi

echo "Configuration is valid."
echo ""

# --- Dependencies ---
VENV_DIR=".venv"
REQUIREMENTS_FILE="requirements.txt"

echo "Setting up Python virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    if ! python3 -m venv "$VENV_DIR"; then
        echo "ERROR: Failed to create Python virtual environment."
        echo "Please ensure python3 and the 'venv' module are installed."
        exit 1
    fi
    echo "Virtual environment created at '$VENV_DIR'."
else
    echo "Virtual environment already exists."
fi

echo "Installing dependencies..."
if ! "$VENV_DIR/bin/pip" install -q -r "$REQUIREMENTS_FILE"; then
    echo "ERROR: Failed to install dependencies from '$REQUIREMENTS_FILE'."
    exit 1
fi
echo "Dependencies installed successfully."
echo ""

# --- Systemd Service ---
SERVICE_FILE="ollama-proxy.service"
PROXY_DIR=$(pwd)
PYTHON_EXEC="$PROXY_DIR/$VENV_DIR/bin/python"
MAIN_PY="$PROXY_DIR/main.py"
CURRENT_USER=$(whoami)

read -p "Do you want to create a systemd service to run the proxy automatically? (y/N) " -n 1 -r
echo # Move to a new line

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Creating systemd service file..."

    cat > "$SERVICE_FILE" << EOL
[Unit]
Description=Ollama Proxy Service
After=network.target

[Service]
User=$CURRENT_USER
Group=$(id -gn "$CURRENT_USER")
WorkingDirectory=$PROXY_DIR
ExecStart=$PYTHON_EXEC $MAIN_PY
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOL

    echo "Service file '$SERVICE_FILE' created."
    echo "You will be prompted for your password to copy this file to /etc/systemd/system/."

    if sudo cp "$SERVICE_FILE" /etc/systemd/system/; then
        echo "Service file successfully copied."
        echo "To enable and start the service, run the following commands:"
        echo "  sudo systemctl daemon-reload"
        echo "  sudo systemctl enable ollama-proxy.service"
        echo "  sudo systemctl start ollama-proxy.service"
        echo ""
        echo "You can check the service status with:"
        echo "  sudo systemctl status ollama-proxy.service"
    else
        echo "ERROR: Failed to copy service file. Please do it manually:"
        echo "  sudo cp '$SERVICE_FILE' /etc/systemd/system/"
        echo "Then run the commands above to enable and start the service."
    fi
else
    echo "Skipping systemd service creation."
fi

echo ""
echo "Installation complete!"
echo "Please review your '$CONFIG_FILE' and then start the service manually if needed:"
echo "  $PYTHON_EXEC $MAIN_PY"
echo ""