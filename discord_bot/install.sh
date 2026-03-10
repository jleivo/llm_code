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
