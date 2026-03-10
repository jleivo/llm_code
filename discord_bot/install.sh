#!/bin/bash
set -euo pipefail

CONFIG_VERSION=1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Helpers ────────────────────────────────────────────────────────────────────

prompt_value() {
    # Usage: prompt_value "Label" "default"
    # Prints the entered value (or default if empty) to stdout.
    local label="$1"
    local default="$2"
    local value
    if [[ -n "$default" ]]; then
        read -rp "$label [$default]: " value
    else
        read -rp "$label: " value
    fi
    echo "${value:-$default}"
}

get_ini_value() {
    # Usage: get_ini_value "path/to/file.ini" "section" "key"
    local file="$1" section="$2" key="$3"
    awk -F ' *= *' "/^\[$section\]/{found=1; next} /^\[/{found=0} found && /^$key/{print \$2; exit}" "$file" 2>/dev/null || true
}

# ── Install directory ──────────────────────────────────────────────────────────

echo ""
echo "=== Discord Bot Installer ==="
echo ""

INSTALL_DIR="$(prompt_value "Install directory" "/srv/LunaticLeivoModel")"

if [[ -d "$INSTALL_DIR" ]]; then
    echo "Existing installation found at $INSTALL_DIR."
    FRESH_INSTALL=false
else
    echo "No existing installation at $INSTALL_DIR — performing fresh install."
    FRESH_INSTALL=true
fi

# ── System user ────────────────────────────────────────────────────────────────

echo ""
echo "--- System user ---"

if id lunatic &>/dev/null; then
    echo "User 'lunatic' already exists, skipping."
else
    echo "Creating system user 'lunatic'..."
    sudo adduser --system --home "$INSTALL_DIR" --no-create-home lunatic
    sudo addgroup --system lunatic 2>/dev/null || true
    sudo usermod -aG lunatic lunatic
fi

# ── Directory and bot files ────────────────────────────────────────────────────

echo ""
echo "--- Installing bot files ---"

sudo mkdir -p "$INSTALL_DIR"
sudo chown lunatic:lunatic "$INSTALL_DIR"

sudo cp "$SCRIPT_DIR/discord_bot.py" "$INSTALL_DIR/discord_bot.py"
sudo cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"
sudo chown lunatic:lunatic "$INSTALL_DIR/discord_bot.py" "$INSTALL_DIR/requirements.txt"

echo "Bot files copied to $INSTALL_DIR."

# ── Python venv and packages ───────────────────────────────────────────────────

echo ""
echo "--- Python environment ---"

if [[ ! -d "$INSTALL_DIR/.venv" ]]; then
    echo "Creating virtual environment..."
    sudo -u lunatic python3 -m venv "$INSTALL_DIR/.venv"
fi

echo "Installing/upgrading Python packages..."
sudo -u lunatic "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip -q
sudo -u lunatic "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --upgrade
echo "Python packages up to date."

# ── config.ini walkthrough ─────────────────────────────────────────────────────

echo ""
echo "--- Bot configuration ---"

EXISTING_CONFIG="$INSTALL_DIR/config.ini"

existing_version=""
if [[ -f "$EXISTING_CONFIG" ]]; then
    existing_version="$(get_ini_value "$EXISTING_CONFIG" "meta" "version")"
    if [[ "$existing_version" != "$CONFIG_VERSION" ]]; then
        echo "Config version mismatch (found: ${existing_version:-none}, expected: $CONFIG_VERSION). Walking through all settings."
    else
        echo "Config is current (version $CONFIG_VERSION). Confirming all settings."
    fi
fi

# api
api_base_url="$(prompt_value "API base URL" "$(get_ini_value "$EXISTING_CONFIG" "api" "base_url")")"
api_api_key="$(prompt_value "API key" "$(get_ini_value "$EXISTING_CONFIG" "api" "api_key")")"
api_model="$(prompt_value "Model name" "$(get_ini_value "$EXISTING_CONFIG" "api" "model")")"

# bot
bot_system_prompt="$(prompt_value "System prompt" "$(get_ini_value "$EXISTING_CONFIG" "bot" "system_prompt")")"
bot_history_ttl="$(prompt_value "History TTL (seconds)" "$(get_ini_value "$EXISTING_CONFIG" "bot" "history_ttl")")"
bot_spontaneous_min="$(prompt_value "Spontaneous min messages" "$(get_ini_value "$EXISTING_CONFIG" "bot" "spontaneous_min")")"
bot_spontaneous_max="$(prompt_value "Spontaneous max messages" "$(get_ini_value "$EXISTING_CONFIG" "bot" "spontaneous_max")")"
bot_active_rounds="$(prompt_value "Active rounds after spontaneous trigger" "$(get_ini_value "$EXISTING_CONFIG" "bot" "active_rounds")")"

# Write config
sudo tee "$EXISTING_CONFIG" > /dev/null << EOF
[meta]
version = $CONFIG_VERSION

[api]
base_url = $api_base_url
api_key = $api_api_key
model = $api_model

[bot]
system_prompt = $bot_system_prompt
history_ttl = $bot_history_ttl
spontaneous_min = $bot_spontaneous_min
spontaneous_max = $bot_spontaneous_max
active_rounds = $bot_active_rounds
EOF

sudo chown lunatic:lunatic "$EXISTING_CONFIG"
sudo chmod 640 "$EXISTING_CONFIG"
echo "config.ini written."

# ── .env walkthrough ───────────────────────────────────────────────────────────

echo ""
echo "--- Discord token ---"

ENV_FILE="$INSTALL_DIR/.env"
current_token=""
if [[ -f "$ENV_FILE" ]]; then
    current_token="$(grep -m1 '^DISCORD_TOKEN=' "$ENV_FILE" | cut -d'=' -f2-)"
fi

if [[ -n "$current_token" ]]; then
    token_len="${#current_token}"
    if [[ "$token_len" -gt 8 ]]; then
        masked="${current_token:0:4}****${current_token: -4}"
    else
        masked="****"
    fi
    echo "Current token: $masked"
    read -rp "Discord token [keep current]: " new_token
    DISCORD_TOKEN="${new_token:-$current_token}"
else
    read -rp "Discord token: " DISCORD_TOKEN
fi

sudo tee "$ENV_FILE" > /dev/null << EOF
DISCORD_TOKEN=$DISCORD_TOKEN
EOF

sudo chown lunatic:lunatic "$ENV_FILE"
sudo chmod 600 "$ENV_FILE"
echo ".env written."

# ── System infrastructure ──────────────────────────────────────────────────────

echo ""
echo "--- System infrastructure ---"

# rsyslog
if [[ ! -f /etc/rsyslog.d/discord_bot.conf ]]; then
    echo "Installing rsyslog config..."
    sudo cp "$SCRIPT_DIR/dependencies/rsyslog/discord_bot.conf" /etc/rsyslog.d/discord_bot.conf
    sudo systemctl restart rsyslog
    echo "rsyslog configured."
else
    echo "rsyslog config already present, skipping."
fi

# logrotate
if [[ ! -f /etc/logrotate.d/discord_bot ]]; then
    echo "Installing logrotate config..."
    sudo cp "$SCRIPT_DIR/dependencies/logrotate/discord_bot" /etc/logrotate.d/discord_bot
    echo "logrotate configured."
else
    echo "logrotate config already present, skipping."
fi

# systemd service — substitute actual install dir into service file
echo "Installing systemd service..."
sed "s|/srv/discord_bot|$INSTALL_DIR|g" "$SCRIPT_DIR/dependencies/lunatic.service" \
    | sudo tee /usr/lib/systemd/system/lunatic.service > /dev/null
sudo systemctl daemon-reload

if systemctl is-enabled --quiet lunatic.service 2>/dev/null; then
    echo "Restarting lunatic.service..."
    sudo systemctl restart lunatic.service
else
    echo "Enabling and starting lunatic.service..."
    sudo systemctl enable --now lunatic.service
fi

echo ""
echo "=== Installation complete ==="
echo "Bot is running as lunatic.service. Check status with: systemctl status lunatic.service"
