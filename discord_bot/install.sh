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
