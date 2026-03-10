# Design: Ollama GPU Load Monitoring

**Date:** 2026-03-10
**Branch:** feat/ollama_load

## Overview

Add GPU compute utilization monitoring to the Ollama proxy service. A lightweight
poller script runs on each GPU host, exposes utilization via HTTP, and the proxy
uses it as a pre-filter in host selection to avoid routing new requests to already
heavily loaded GPUs.

## Platforms

- **Linux host** — NVIDIA GPU(s), `pynvml` library
- **Windows host** — AMD GPU(s), `amdsmi` library

## Architecture

```
┌─────────────────────────────────────┐
│           Ollama Proxy              │
│  monitor_hosts() every 60s          │
│  ┌─────────────────────────────┐    │
│  │ OllamaHost                  │    │
│  │  - free_vram_mb             │    │
│  │  - gpu_utilization_pct      │    │
│  │  - gpu_load_threshold_pct   │    │
│  └─────────────────────────────┘    │
│  get_best_host():                   │
│    filter: Ollama reachable         │
│    filter: gpu_util < threshold     │
│    fallback: all above threshold    │
│    then: existing 4-step VRAM algo  │
└────────────┬────────────────────────┘
             │ polls /metrics (HTTP)
             │
     ┌───────┴──────────┐
     │                  │
┌────▼────┐        ┌────▼────┐
│ Linux   │        │ Windows │
│ host    │        │ host    │
│         │        │         │
│ gpu_    │        │ gpu_    │
│ monitor │        │ monitor │
│ .py     │        │ .py     │
│ :9091   │        │ :9091   │
│ pynvml  │        │ amdsmi  │
└─────────┘        └─────────┘
```

## gpu_monitor.py

A single cross-platform Python script. At startup it detects the platform
(`sys.platform`) and initialises the appropriate GPU library. On each request
to `/metrics` it queries per-device utilization and returns JSON.

### HTTP API

```
GET http://<host>:9091/metrics
```

Response:
```json
{
  "gpu_utilization_pct": 52,
  "gpus": [
    {"index": 0, "name": "NVIDIA GeForce RTX 3090", "utilization_pct": 45},
    {"index": 1, "name": "NVIDIA GeForce RTX 3090", "utilization_pct": 52}
  ]
}
```

`gpu_utilization_pct` is the **max** across all GPUs on the host — the busiest
GPU is the bottleneck for Ollama inference.

If the GPU library fails, the endpoint returns HTTP 503.

### Configuration (CLI args or env vars)

| Option | Default | Description |
|---|---|---|
| `--port` | `9091` | Port to listen on |
| `--host` | `0.0.0.0` | Bind address |
| `--poll-interval` | `5` | Seconds between internal GPU reads |

### Logging

- **Linux** — `SysLogHandler` → `/dev/log` with tag `gpu_monitor`. A rsyslog
  drop-in routes to `/var/log/gpu_monitor.log`. Logrotate handles daily rotation,
  7 days retained.
- **Windows** — `TimedRotatingFileHandler`, `when='midnight'`, `backupCount=7`,
  writing `gpu_monitor.log` to the script's working directory.

Log content: startup messages, per-poll utilization readings, GPU library errors.

## Proxy Integration

### Config schema change

`load_monitor_url` and `gpu_load_threshold_pct` are optional per host. If absent,
the host behaves exactly as before (no regression).

```json
{
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

### OllamaHost changes

New fields:
- `load_monitor_url: str | None` — URL of the poller endpoint, or None
- `gpu_load_threshold_pct: int` — threshold, default 80
- `gpu_utilization_pct: float` — last known utilization, default 0 (fail open)

`update_status()` also polls `load_monitor_url/metrics` if configured, updates
`gpu_utilization_pct`. On any error (unreachable, timeout, bad response) it logs
a warning and leaves `gpu_utilization_pct` at 0.

### Revised routing algorithm in get_best_host()

```
1. candidate_pool  = all hosts where Ollama is reachable
2. preferred_pool  = candidates where gpu_utilization_pct < gpu_load_threshold_pct
3. routing_pool    = preferred_pool if non-empty, else candidate_pool (fallback)
4. run existing 4-step VRAM algorithm on routing_pool
```

This means:
- **Multi-host, one overloaded** — traffic routes to the less-loaded host.
- **Single host overloaded, VRAM available** — routes anyway (better than failing).
- **Single host overloaded, no VRAM** — still fails, for the right reason (VRAM).
- **All hosts overloaded** — falls back to VRAM-only routing, no silent failures.

## File Layout

```
manage_ollama/
  gpu_monitor/
    gpu_monitor.py
    requirements.txt          # pynvml + amdsmi + fastapi + uvicorn
    README.md
    tests/
      test_gpu_monitor.py
  dependencies/
    gpu_monitor/
      gpu_monitor.service           # systemd unit
      rsyslog_gpu_monitor.conf
      logrotate_gpu_monitor.conf
      install_linux.sh
      install_windows.ps1
```

## Deployment

### Linux (install_linux.sh)

1. Copy `gpu_monitor.py` to install dir (e.g. `/opt/gpu_monitor/`)
2. Create venv, `pip install -r requirements.txt`
3. Drop rsyslog + logrotate configs into `/etc/rsyslog.d/` and `/etc/logrotate.d/`
4. Install, enable, and start the systemd service

### Windows (install_windows.ps1)

1. Copy script to install dir
2. Create venv, install deps
3. Use NSSM to register and start a Windows service pointing at the venv Python

## Testing

### gpu_monitor tests

- Mock `pynvml` and `amdsmi` — no GPU hardware required
- `/metrics` response structure and field types
- Multi-GPU max aggregation (GPUs at 45% and 52% → top-level reports 52%)
- GPU library error → HTTP 503

### Proxy integration tests

**Routing logic:**
- Host above threshold excluded when alternatives exist
- All hosts above threshold → routes on VRAM only (fallback)
- `load_monitor_url` absent → host behaves as before (no regression)

**Fault tolerance (fail open on any bad input):**
- Load monitor unreachable / timeout → `gpu_utilization_pct` = 0, host stays in rotation
- Malformed / truncated JSON
- Valid JSON with missing fields (`gpu_utilization_pct` absent, `gpus` null)
- Wrong field types (`gpu_utilization_pct` is a string)
- HTTP error responses (404, 500) from load monitor
- Out-of-range values (`gpu_utilization_pct: 150`) → clamp to 100

Rule: **any unexpected input from the load monitor is treated as unreachable —
fail open, log a warning, continue routing on VRAM alone. The proxy must never
crash or surface an error to the client due to a bad load monitor response.**
