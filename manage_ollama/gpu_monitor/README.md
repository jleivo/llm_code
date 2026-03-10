# gpu_monitor

Cross-platform GPU utilization monitor for the Ollama proxy. Exposes a single
HTTP endpoint so the proxy can make load-aware routing decisions.

## Platforms

| Platform | GPU vendor | Library |
|---|---|---|
| Linux | NVIDIA | `pynvml` |
| Windows | AMD | `amdsmi` (system package, installed with AMD drivers) |

## Endpoint

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

`gpu_utilization_pct` is the **max** across all GPUs. Returns HTTP 503 when the
GPU library cannot be read.

## Installation

### Linux

```bash
sudo bash manage_ollama/dependencies/gpu_monitor/install_linux.sh
```

Installs to `/opt/gpu_monitor/` by default. Pass a different path as first argument.

### Windows

Run PowerShell as Administrator:

```powershell
.\manage_ollama\dependencies\gpu_monitor\install_windows.ps1
```

Requires [NSSM](https://nssm.cc/) on PATH. Pass `-NssmPath` to override.
AMD `amdsmi` is a system package installed alongside AMD drivers — it is not in
`requirements.txt`.

## Proxy Configuration

Add `load_monitor_url` and optionally `gpu_load_threshold_pct` (default 80) to
each host entry in the proxy's `config.json`:

```json
{
  "hosts": [
    {
      "url": "http://gpu-host:11434",
      "total_vram_mb": 16384,
      "priority": 1,
      "load_monitor_url": "http://gpu-host:9091",
      "gpu_load_threshold_pct": 80
    }
  ]
}
```

Hosts without `load_monitor_url` are unaffected and route as before.
