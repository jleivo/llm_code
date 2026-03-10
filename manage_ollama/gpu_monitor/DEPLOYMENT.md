# gpu_monitor Deployment Guide

GPU utilization monitor for the Ollama proxy. Runs as a service on each GPU host and exposes a single HTTP endpoint the proxy polls when making routing decisions.

---

## Overview

```
Ollama Proxy  ──polls /metrics──►  gpu_monitor (port 9091)
                                        │
                                   pynvml (Linux/NVIDIA)
                                   amdsmi (Windows/AMD)
```

The proxy queries each host's monitor every 60 seconds. If a host's GPU utilization is at or above the configured threshold (default 80%), the proxy routes new requests elsewhere. If **all** hosts are above threshold, it falls back to VRAM-only routing rather than failing requests.

If the monitor is unreachable the proxy treats the host as 0% utilization — it never refuses requests because the monitor is down.

---

## Prerequisites

### Linux (NVIDIA)

- Python 3.12
- NVIDIA drivers installed (`nvidia-smi` works)
- `rsyslog` and `logrotate` installed (standard on most distros)
- Run as root or with `sudo`

### Windows (AMD)

- Python 3.12
- AMD drivers installed (includes `amdsmi` as a system package — no pip install needed)
- [NSSM](https://nssm.cc/download) — Non-Sucking Service Manager — on `PATH` or passed via `-NssmPath`
- Run PowerShell as Administrator

---

## Installation

### Linux

```bash
cd /path/to/llm_code
sudo bash manage_ollama/dependencies/gpu_monitor/install_linux.sh
```

Installs to `/opt/gpu_monitor/` by default. Pass a custom path as the first argument:

```bash
sudo bash manage_ollama/dependencies/gpu_monitor/install_linux.sh /srv/gpu_monitor
```

What the script does:
1. Creates a `gpu_monitor` system user (no login shell, no home directory)
2. Creates the install directory and copies `gpu_monitor.py` + `requirements.txt`
3. Creates a Python venv and installs `fastapi`, `uvicorn`, `pynvml`
4. Drops rsyslog config into `/etc/rsyslog.d/gpu_monitor.conf` and restarts rsyslog
5. Drops logrotate config into `/etc/logrotate.d/gpu_monitor`
6. Installs, enables, and starts the systemd service

Verify the service started:

```bash
systemctl status gpu_monitor
```

### Windows

Open PowerShell as Administrator:

```powershell
cd C:\path\to\llm_code
.\manage_ollama\dependencies\gpu_monitor\install_windows.ps1
```

Custom install directory:

```powershell
.\manage_ollama\dependencies\gpu_monitor\install_windows.ps1 -InstallDir D:\gpu_monitor
```

If `nssm.exe` is not on `PATH`:

```powershell
.\manage_ollama\dependencies\gpu_monitor\install_windows.ps1 -NssmPath C:\tools\nssm.exe
```

What the script does:
1. Creates the install directory and copies the script + requirements
2. Creates a Python venv and installs dependencies
3. Registers and starts a Windows service via NSSM

Verify:

```powershell
nssm status gpu_monitor
```

---

## Verifying the Endpoint

From the GPU host itself, or any machine that can reach it:

```bash
curl http://<host-ip>:9091/metrics
```

Expected response:

```json
{
  "gpu_utilization_pct": 12,
  "gpus": [
    {"index": 0, "name": "NVIDIA GeForce RTX 3090", "utilization_pct": 12}
  ]
}
```

`gpu_utilization_pct` is the **maximum** across all GPUs on the host.

HTTP 503 means the GPU library could not be read (driver issue, permissions). Check service logs.

---

## Logging

### Linux

Logs via syslog to `/var/log/gpu_monitor.log`. Rotated daily, 7 days kept, compressed.

```bash
tail -f /var/log/gpu_monitor.log
journalctl -u gpu_monitor -f
```

### Windows

Logs to `gpu_monitor.log` in the install directory (default `C:\opt\gpu_monitor\gpu_monitor.log`). Rotated at midnight, 7 days kept.

---

## Proxy Configuration

Add `load_monitor_url` to each host entry in the Ollama proxy's `config.json`. Optionally override the threshold (default 80%):

```json
{
  "server": {
    "port": 9090
  },
  "hosts": [
    {
      "url": "http://linux-host:11434",
      "total_vram_mb": 16384,
      "priority": 1,
      "load_monitor_url": "http://linux-host:9091",
      "gpu_load_threshold_pct": 80
    },
    {
      "url": "http://windows-host:11434",
      "total_vram_mb": 8192,
      "priority": 2,
      "load_monitor_url": "http://windows-host:9091",
      "gpu_load_threshold_pct": 80
    }
  ]
}
```

Hosts without `load_monitor_url` are unaffected — routing works exactly as before.

Restart the proxy after editing `config.json`.

---

## Routing Behaviour

| Situation | Result |
|---|---|
| Host below threshold | Eligible for routing (normal VRAM-based selection) |
| Host above threshold, alternative available | Skipped — traffic goes to less-loaded host |
| All hosts above threshold | Falls back to VRAM-only routing — requests still served |
| Monitor unreachable (Ollama up) | Treated as 0% — host stays in rotation |
| Monitor unreachable (Ollama down) | Host excluded as unavailable (existing behaviour) |

---

## CLI Options

The script can be run directly for testing:

```bash
/opt/gpu_monitor/.venv/bin/python /opt/gpu_monitor/gpu_monitor.py \
  --port 9091 \
  --host 0.0.0.0 \
  --poll-interval 5
```

| Option | Default | Description |
|---|---|---|
| `--port` | `9091` | Port to listen on |
| `--host` | `0.0.0.0` | Bind address |
| `--poll-interval` | `5` | Seconds between GPU reads |

---

## Service Management

### Linux (systemd)

```bash
systemctl start gpu_monitor
systemctl stop gpu_monitor
systemctl restart gpu_monitor
systemctl status gpu_monitor
```

### Windows (NSSM)

```powershell
nssm start gpu_monitor
nssm stop gpu_monitor
nssm restart gpu_monitor
nssm status gpu_monitor
```

---

## Firewall

Port 9091 (TCP) must be reachable from the machine running the Ollama proxy to each GPU host.

```bash
# Linux — example with ufw
ufw allow from <proxy-ip> to any port 9091 proto tcp
```

The monitor does not need to be reachable from the internet or from clients — only from the proxy host.

---

## Troubleshooting

**HTTP 503 from /metrics**
The GPU library failed to read. Check:
- NVIDIA: `nvidia-smi` runs without error as the `gpu_monitor` user
- AMD: AMD drivers installed and `amdsmi` importable from the venv

**Monitor shows 0% constantly**
Normal if the GPU is truly idle. Confirm with `nvidia-smi` or AMD's tooling.

**Proxy ignoring the monitor**
Check `load_monitor_url` is set in `config.json` and the proxy was restarted. Proxy logs (LOG_LOCAL7 / `proxy.log`) will show `GPU routing:` lines each 60-second cycle.

**Port 9091 already in use**
Pass `--port <other>` to the service. Update `ExecStart` in the systemd unit or NSSM config, and update `load_monitor_url` in the proxy config.
