# GPU Monitor

A lightweight, cross-platform GPU utilization poller for Ollama proxy load monitoring.

## Features

- **Cross-Platform:** Supports NVIDIA GPUs on Linux and AMD GPUs on Windows.
- **HTTP Metrics:** Provides a `/metrics` endpoint that returns GPU utilization data in JSON format.
- **Periodic Polling:** Continuously monitors GPU activity at a configurable interval.

## Usage

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run the Monitor

```bash
python gpu_monitor.py --port 9091
```

## API Endpoints

### `GET /metrics`

Returns the current GPU utilization metrics.

**Response Body:**

```json
{
  "gpu_utilization_pct": 52,
  "gpus": [
    {
      "index": 0,
      "name": "NVIDIA GeForce RTX 3080",
      "utilization_pct": 45
    },
    {
      "index": 1,
      "name": "NVIDIA GeForce RTX 3080",
      "utilization_pct": 52
    }
  ]
}
```
