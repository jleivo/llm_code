#!/bin/bash
set -euo pipefail

INSTALL_DIR="${1:-/opt/gpu_monitor}"

echo "Installing gpu_monitor to $INSTALL_DIR..."

# Create system user if not exists
id -u gpu_monitor &>/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin gpu_monitor

# Create install directory
mkdir -p "$INSTALL_DIR"
cp "$(dirname "$0")/../../gpu_monitor/gpu_monitor.py" "$INSTALL_DIR/"
cp "$(dirname "$0")/../../gpu_monitor/requirements.txt" "$INSTALL_DIR/"

# Create venv and install deps
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q

chown -R gpu_monitor:gpu_monitor "$INSTALL_DIR"

# rsyslog
cp "$(dirname "$0")/rsyslog_gpu_monitor.conf" /etc/rsyslog.d/gpu_monitor.conf
systemctl restart rsyslog

# logrotate
cp "$(dirname "$0")/logrotate_gpu_monitor.conf" /etc/logrotate.d/gpu_monitor

# systemd service (substitute install dir)
sed "s|/opt/gpu_monitor|$INSTALL_DIR|g" "$(dirname "$0")/gpu_monitor.service" \
    > /etc/systemd/system/gpu_monitor.service
systemctl daemon-reload
systemctl enable --now gpu_monitor

echo "gpu_monitor installed and started. Check: systemctl status gpu_monitor"
