# GPU Load Monitoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a cross-platform GPU utilization poller (`gpu_monitor.py`) that exposes a `/metrics` HTTP endpoint, and integrate it into the Ollama proxy as a pre-filter in host routing.

**Architecture:** A single Python script auto-detects Linux/NVIDIA (`pynvml`) or Windows/AMD (`amdsmi`) at startup and serves a FastAPI `/metrics` endpoint. The proxy polls each host's monitor every 60 s alongside its existing Ollama API checks. Hosts above the GPU threshold are deprioritised in `get_best_host()`; if all hosts exceed the threshold the proxy falls back to VRAM-only routing so requests never fail solely due to load.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, pynvml (Linux), amdsmi (Windows), pytest, requests (existing), systemd (Linux deployment), NSSM (Windows deployment).

---

## Task 1: Merge ollama-proxy into feat/ollama_load

**Files:**
- No files to create; git operation only.

**Step 1: Merge the branch**

```bash
cd /home/juha/git/llm_code/.worktrees/feat/ollama_load
git merge origin/ollama-proxy --no-edit
```

Expected: merge commit created, `manage_ollama/ollama_proxy/` now contains `main.py`, `host_manager.py`, `lru_tracker.py`, `model_cache.py`, `requirements.txt`, `tests/`.

**Step 2: Verify tests still pass**

```bash
cd manage_ollama/ollama_proxy
source /home/juha/git/llm_code/.venv/bin/activate
python -m pytest tests/ -q
```

Expected: all existing tests pass (68 tests, 0 failures).

**Step 3: Commit**

```bash
git commit --author="lunatic <lunatic@discord-bot>" -m "chore: merge ollama-proxy into feat/ollama_load"
```

---

## Task 2: Create gpu_monitor directory skeleton

**Files:**
- Create: `manage_ollama/gpu_monitor/__init__.py`
- Create: `manage_ollama/gpu_monitor/requirements.txt`
- Create: `manage_ollama/gpu_monitor/tests/__init__.py`

**Step 1: Create the directory and files**

```bash
mkdir -p manage_ollama/gpu_monitor/tests
touch manage_ollama/gpu_monitor/__init__.py
touch manage_ollama/gpu_monitor/tests/__init__.py
```

`manage_ollama/gpu_monitor/requirements.txt`:
```
fastapi>=0.110.0
uvicorn>=0.29.0
pynvml>=11.5.0
```

Note: `amdsmi` is installed as a system package on Windows alongside AMD drivers — do not add it to requirements.txt. `pynvml` is Linux-only but harmless to list; the script guards imports with platform checks.

**Step 2: Commit**

```bash
git add manage_ollama/gpu_monitor/
git commit --author="lunatic <lunatic@discord-bot>" -m "chore: add gpu_monitor directory skeleton"
```

---

## Task 3: gpu_monitor — /metrics endpoint, NVIDIA path (TDD)

**Files:**
- Create: `manage_ollama/gpu_monitor/tests/test_gpu_monitor.py`
- Create: `manage_ollama/gpu_monitor/gpu_monitor.py`

**Step 1: Write failing tests**

`manage_ollama/gpu_monitor/tests/test_gpu_monitor.py`:

```python
import sys
import pytest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers to build a fake pynvml module
# ---------------------------------------------------------------------------

def _make_pynvml_mock(gpu_utils):
    """Build a pynvml mock returning given per-GPU utilization percentages."""
    mock = MagicMock()
    mock.nvmlDeviceGetCount.return_value = len(gpu_utils)
    handles = [MagicMock() for _ in gpu_utils]
    mock.nvmlDeviceGetHandleByIndex.side_effect = lambda i: handles[i]
    mock.nvmlDeviceGetName.side_effect = lambda h: f"NVIDIA GPU {handles.index(h)}"
    util_rates = [MagicMock(gpu=u) for u in gpu_utils]
    mock.nvmlDeviceGetUtilizationRates.side_effect = lambda h: util_rates[handles.index(h)]
    return mock


@pytest.fixture()
def nvidia_client(monkeypatch):
    """TestClient with NVIDIA platform mocked."""
    fake_nvml = _make_pynvml_mock([45, 52])
    monkeypatch.setattr("sys.platform", "linux")
    with patch.dict(sys.modules, {"pynvml": fake_nvml}):
        # Re-import to pick up patched modules
        import importlib
        import manage_ollama.gpu_monitor.gpu_monitor as gm
        importlib.reload(gm)
        from fastapi.testclient import TestClient
        yield TestClient(gm.app), gm


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_metrics_returns_200(nvidia_client):
    client, _ = nvidia_client
    resp = client.get("/metrics")
    assert resp.status_code == 200


def test_metrics_has_required_fields(nvidia_client):
    client, _ = nvidia_client
    data = client.get("/metrics").json()
    assert "gpu_utilization_pct" in data
    assert "gpus" in data
    assert isinstance(data["gpu_utilization_pct"], (int, float))
    assert isinstance(data["gpus"], list)


def test_metrics_gpu_utilization_is_max_across_gpus(nvidia_client):
    """Top-level value must be the MAX across all GPUs (45 and 52 → 52)."""
    client, _ = nvidia_client
    data = client.get("/metrics").json()
    assert data["gpu_utilization_pct"] == 52


def test_metrics_gpus_list_has_correct_shape(nvidia_client):
    client, _ = nvidia_client
    data = client.get("/metrics").json()
    assert len(data["gpus"]) == 2
    for gpu in data["gpus"]:
        assert "index" in gpu
        assert "name" in gpu
        assert "utilization_pct" in gpu


def test_metrics_single_gpu(monkeypatch):
    fake_nvml = _make_pynvml_mock([73])
    monkeypatch.setattr("sys.platform", "linux")
    with patch.dict(sys.modules, {"pynvml": fake_nvml}):
        import importlib
        import manage_ollama.gpu_monitor.gpu_monitor as gm
        importlib.reload(gm)
        from fastapi.testclient import TestClient
        resp = TestClient(gm.app).get("/metrics")
        data = resp.json()
        assert data["gpu_utilization_pct"] == 73
        assert len(data["gpus"]) == 1


def test_metrics_gpu_library_error_returns_503(monkeypatch):
    """If pynvml raises during read, /metrics must return 503."""
    fake_nvml = MagicMock()
    fake_nvml.nvmlDeviceGetCount.side_effect = RuntimeError("nvml error")
    monkeypatch.setattr("sys.platform", "linux")
    with patch.dict(sys.modules, {"pynvml": fake_nvml}):
        import importlib
        import manage_ollama.gpu_monitor.gpu_monitor as gm
        importlib.reload(gm)
        from fastapi.testclient import TestClient
        resp = TestClient(gm.app).get("/metrics")
        assert resp.status_code == 503
```

**Step 2: Run tests — verify they fail**

```bash
cd manage_ollama/gpu_monitor
python -m pytest tests/test_gpu_monitor.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `gpu_monitor.py` does not exist yet.

**Step 3: Implement gpu_monitor.py (NVIDIA path)**

`manage_ollama/gpu_monitor/gpu_monitor.py`:

```python
#!/usr/bin/env python3
"""Cross-platform GPU utilization poller for Ollama proxy load monitoring."""
import sys
import logging
import logging.handlers
import threading
import time
import argparse

from fastapi import FastAPI, HTTPException
import uvicorn

PLATFORM_LINUX = sys.platform.startswith("linux")
PLATFORM_WINDOWS = sys.platform == "win32"

logger = logging.getLogger(__name__)
app = FastAPI()

_lock = threading.Lock()
_metrics: dict = {}          # last successful reading
_healthy: bool = False       # set True after first successful poll
_poll_interval: int = 5


def _read_nvidia() -> dict:
    import pynvml
    count = pynvml.nvmlDeviceGetCount()
    gpus = []
    for i in range(count):
        handle = pynvml.nvmlDeviceGetHandleByIndex(i)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode()
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        gpus.append({"index": i, "name": name, "utilization_pct": util.gpu})
    max_util = max((g["utilization_pct"] for g in gpus), default=0)
    return {"gpu_utilization_pct": max_util, "gpus": gpus}


def _read_amd() -> dict:
    import amdsmi  # noqa: F401 — Windows only, installed as system package
    devices = amdsmi.amdsmi_get_processor_handles()
    gpus = []
    for i, device in enumerate(devices):
        activity = amdsmi.amdsmi_get_gpu_activity(device)
        asic = amdsmi.amdsmi_get_gpu_asic_info(device)
        name = asic.get("market_name", f"AMD GPU {i}")
        util = activity.get("gfx_activity", 0)
        gpus.append({"index": i, "name": name, "utilization_pct": util})
    max_util = max((g["utilization_pct"] for g in gpus), default=0)
    return {"gpu_utilization_pct": max_util, "gpus": gpus}


def _poll_loop(interval: int) -> None:
    global _metrics, _healthy
    while True:
        try:
            data = _read_nvidia() if PLATFORM_LINUX else _read_amd()
            with _lock:
                _metrics = data
                _healthy = True
            logger.info("GPU utilization: %d%%", data["gpu_utilization_pct"])
        except Exception as exc:
            logger.warning("Failed to read GPU metrics: %s", exc)
            with _lock:
                _healthy = False
        time.sleep(interval)


@app.get("/metrics")
def get_metrics():
    with _lock:
        if not _healthy:
            raise HTTPException(status_code=503, detail="GPU metrics unavailable")
        return dict(_metrics)


def setup_logging() -> None:
    if PLATFORM_LINUX:
        handler = logging.handlers.SysLogHandler(address="/dev/log")
        fmt = "gpu_monitor: %(levelname)s %(message)s"
    else:
        import os
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gpu_monitor.log")
        handler = logging.handlers.TimedRotatingFileHandler(
            log_path, when="midnight", backupCount=7
        )
        fmt = "%(asctime)s %(levelname)s %(message)s"
    logging.basicConfig(level=logging.INFO, handlers=[handler], format=fmt)


def start_poll_thread(interval: int) -> None:
    t = threading.Thread(target=_poll_loop, args=(interval,), daemon=True)
    t.start()


def main() -> None:
    parser = argparse.ArgumentParser(description="GPU utilization HTTP monitor")
    parser.add_argument("--port", type=int, default=9091)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--poll-interval", type=int, default=5, dest="poll_interval")
    args = parser.parse_args()

    setup_logging()

    if PLATFORM_LINUX:
        import pynvml
        pynvml.nvmlInit()
        logger.info("Initialised NVIDIA GPU monitoring via pynvml.")
    elif PLATFORM_WINDOWS:
        import amdsmi
        amdsmi.amdsmi_init()
        logger.info("Initialised AMD GPU monitoring via amdsmi.")
    else:
        logger.error("Unsupported platform: %s", sys.platform)
        sys.exit(1)

    start_poll_thread(args.poll_interval)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
```

**Step 4: Run tests — verify they pass**

```bash
python -m pytest tests/test_gpu_monitor.py -v
```

Expected: 6 tests pass.

**Step 5: Commit**

```bash
git add manage_ollama/gpu_monitor/
git commit --author="lunatic <lunatic@discord-bot>" -m "feat: add gpu_monitor with NVIDIA path and /metrics endpoint"
```

---

## Task 4: gpu_monitor — AMD/Windows path (TDD)

**Files:**
- Modify: `manage_ollama/gpu_monitor/tests/test_gpu_monitor.py`

**Step 1: Add failing AMD tests**

Append to `test_gpu_monitor.py`:

```python
# ---------------------------------------------------------------------------
# AMD / Windows path
# ---------------------------------------------------------------------------

def _make_amdsmi_mock(gpu_utils):
    mock = MagicMock()
    devices = [MagicMock() for _ in gpu_utils]
    mock.amdsmi_get_processor_handles.return_value = devices
    mock.amdsmi_get_gpu_activity.side_effect = lambda d: {
        "gfx_activity": gpu_utils[devices.index(d)]
    }
    mock.amdsmi_get_gpu_asic_info.side_effect = lambda d: {
        "market_name": f"AMD GPU {devices.index(d)}"
    }
    return mock


@pytest.fixture()
def amd_client(monkeypatch):
    fake_amd = _make_amdsmi_mock([30, 60])
    monkeypatch.setattr("sys.platform", "win32")
    with patch.dict(sys.modules, {"amdsmi": fake_amd}):
        import importlib
        import manage_ollama.gpu_monitor.gpu_monitor as gm
        importlib.reload(gm)
        from fastapi.testclient import TestClient
        yield TestClient(gm.app), gm


def test_amd_metrics_utilization_is_max(amd_client):
    """AMD: top-level value is max across GPUs (30 and 60 → 60)."""
    client, _ = amd_client
    data = client.get("/metrics").json()
    assert data["gpu_utilization_pct"] == 60


def test_amd_metrics_gpu_count(amd_client):
    client, _ = amd_client
    data = client.get("/metrics").json()
    assert len(data["gpus"]) == 2


def test_amd_gpu_library_error_returns_503(monkeypatch):
    fake_amd = MagicMock()
    fake_amd.amdsmi_get_processor_handles.side_effect = RuntimeError("amdsmi error")
    monkeypatch.setattr("sys.platform", "win32")
    with patch.dict(sys.modules, {"amdsmi": fake_amd}):
        import importlib
        import manage_ollama.gpu_monitor.gpu_monitor as gm
        importlib.reload(gm)
        from fastapi.testclient import TestClient
        resp = TestClient(gm.app).get("/metrics")
        assert resp.status_code == 503
```

**Step 2: Run tests — verify new ones fail**

```bash
python -m pytest tests/test_gpu_monitor.py::test_amd_metrics_utilization_is_max -v
```

Expected: FAIL — `_read_amd` not exercised via monkeypatched `sys.platform`.

**Step 3: Verify the PLATFORM_LINUX/PLATFORM_WINDOWS flags are re-evaluated on reload**

The `_read_nvidia` / `_read_amd` branch in `_poll_loop` is driven by the module-level `PLATFORM_LINUX` constant. Because tests `reload()` the module after patching `sys.platform`, the flags are re-evaluated correctly on each reload. No code change needed — confirm AMD tests now pass:

```bash
python -m pytest tests/test_gpu_monitor.py -v
```

Expected: all 9 tests pass.

**Step 4: Commit**

```bash
git add manage_ollama/gpu_monitor/tests/test_gpu_monitor.py
git commit --author="lunatic <lunatic@discord-bot>" -m "test: add AMD/Windows path tests for gpu_monitor"
```

---

## Task 5: Proxy config — new OllamaHost fields (TDD)

**Files:**
- Modify: `manage_ollama/ollama_proxy/tests/test_host_manager.py`
- Modify: `manage_ollama/ollama_proxy/host_manager.py`

**Step 1: Write failing tests**

Add to the bottom of `test_host_manager.py`:

```python
# ---------------------------------------------------------------------------
# GPU load monitor config loading
# ---------------------------------------------------------------------------

def test_ollamahost_defaults_for_load_monitor():
    """OllamaHost has sensible defaults when load_monitor fields are absent from config."""
    host = OllamaHost({"url": "http://host:11434", "total_vram_mb": 8000})
    assert host.load_monitor_url is None
    assert host.gpu_load_threshold_pct == 80
    assert host.gpu_utilization_pct == 0.0


def test_ollamahost_load_monitor_config_loaded():
    """OllamaHost reads load_monitor_url and gpu_load_threshold_pct from config."""
    host = OllamaHost({
        "url": "http://host:11434",
        "total_vram_mb": 8000,
        "load_monitor_url": "http://host:9091",
        "gpu_load_threshold_pct": 75,
    })
    assert host.load_monitor_url == "http://host:9091"
    assert host.gpu_load_threshold_pct == 75
```

**Step 2: Run — verify tests fail**

```bash
cd manage_ollama/ollama_proxy
python -m pytest tests/test_host_manager.py::test_ollamahost_defaults_for_load_monitor tests/test_host_manager.py::test_ollamahost_load_monitor_config_loaded -v
```

Expected: FAIL — `OllamaHost` has no `load_monitor_url` attribute.

**Step 3: Add fields to OllamaHost.__init__**

In `host_manager.py`, in `OllamaHost.__init__` after the existing field assignments:

```python
        self.load_monitor_url = config.get('load_monitor_url', None)
        self.gpu_load_threshold_pct = config.get('gpu_load_threshold_pct', 80)
        self.gpu_utilization_pct: float = 0.0
```

**Step 4: Run — verify tests pass**

```bash
python -m pytest tests/test_host_manager.py -v
```

Expected: all tests pass including the two new ones.

**Step 5: Commit**

```bash
git add manage_ollama/ollama_proxy/host_manager.py manage_ollama/ollama_proxy/tests/test_host_manager.py
git commit --author="lunatic <lunatic@discord-bot>" -m "feat: add load_monitor_url and gpu_utilization_pct fields to OllamaHost"
```

---

## Task 6: Proxy — load monitor polling in update_status() (TDD)

**Files:**
- Modify: `manage_ollama/ollama_proxy/tests/test_host_manager.py`
- Modify: `manage_ollama/ollama_proxy/host_manager.py`

**Step 1: Write failing tests**

Add to `test_host_manager.py`:

```python
# ---------------------------------------------------------------------------
# GPU load monitor polling in update_status()
# ---------------------------------------------------------------------------

@pytest.fixture
def host_with_monitor():
    """An OllamaHost configured with a load monitor URL."""
    return OllamaHost({
        "url": "http://host:11434",
        "total_vram_mb": 8000,
        "load_monitor_url": "http://host:9091",
        "gpu_load_threshold_pct": 80,
    })


def _mock_ollama_responses(mocker, host):
    """Helper: mock Ollama /api/ps and /api/tags to report host as available."""
    mocker.patch.object(host, 'check_availability', return_value=True)
    mocker.patch.object(host, 'update_models_and_vram_from_api')


def test_update_status_sets_gpu_utilization(mocker, host_with_monitor):
    """update_status() reads gpu_utilization_pct from load monitor."""
    _mock_ollama_responses(mocker, host_with_monitor)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"gpu_utilization_pct": 45, "gpus": []}
    mocker.patch("requests.get", return_value=mock_resp)

    host_with_monitor.update_status()
    assert host_with_monitor.gpu_utilization_pct == 45


def test_update_status_clamps_over_100(mocker, host_with_monitor):
    """Values > 100 are clamped to 100."""
    _mock_ollama_responses(mocker, host_with_monitor)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"gpu_utilization_pct": 150, "gpus": []}
    mocker.patch("requests.get", return_value=mock_resp)

    host_with_monitor.update_status()
    assert host_with_monitor.gpu_utilization_pct == 100


def test_update_status_load_monitor_unreachable_fails_open(mocker, host_with_monitor):
    """If load monitor is unreachable, gpu_utilization_pct stays 0 (fail open)."""
    _mock_ollama_responses(mocker, host_with_monitor)
    mocker.patch("requests.get", side_effect=requests.RequestException("refused"))

    host_with_monitor.update_status()
    assert host_with_monitor.gpu_utilization_pct == 0
    assert host_with_monitor.available  # Ollama availability unaffected


def test_update_status_load_monitor_http_error_fails_open(mocker, host_with_monitor):
    """HTTP 500 from load monitor → fail open."""
    _mock_ollama_responses(mocker, host_with_monitor)
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mocker.patch("requests.get", return_value=mock_resp)

    host_with_monitor.update_status()
    assert host_with_monitor.gpu_utilization_pct == 0


def test_update_status_malformed_json_fails_open(mocker, host_with_monitor):
    """Malformed JSON from load monitor → fail open."""
    _mock_ollama_responses(mocker, host_with_monitor)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError("bad json")
    mocker.patch("requests.get", return_value=mock_resp)

    host_with_monitor.update_status()
    assert host_with_monitor.gpu_utilization_pct == 0


def test_update_status_missing_field_fails_open(mocker, host_with_monitor):
    """Response missing gpu_utilization_pct field → fail open."""
    _mock_ollama_responses(mocker, host_with_monitor)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"gpus": []}
    mocker.patch("requests.get", return_value=mock_resp)

    host_with_monitor.update_status()
    assert host_with_monitor.gpu_utilization_pct == 0


def test_update_status_wrong_type_fails_open(mocker, host_with_monitor):
    """gpu_utilization_pct with wrong type (string) → fail open."""
    _mock_ollama_responses(mocker, host_with_monitor)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"gpu_utilization_pct": "high", "gpus": []}
    mocker.patch("requests.get", return_value=mock_resp)

    host_with_monitor.update_status()
    assert host_with_monitor.gpu_utilization_pct == 0


def test_update_status_no_load_monitor_url_no_regression(mocker):
    """Host without load_monitor_url behaves exactly as before (no requests to monitor)."""
    host = OllamaHost({"url": "http://host:11434", "total_vram_mb": 8000})
    mocker.patch.object(host, 'check_availability', return_value=True)
    mocker.patch.object(host, 'update_models_and_vram_from_api')
    get_spy = mocker.patch("requests.get")

    host.update_status()
    # requests.get called only for check_availability (which we stubbed above),
    # not for any load monitor URL
    assert host.gpu_utilization_pct == 0
```

**Step 2: Run — verify tests fail**

```bash
python -m pytest tests/test_host_manager.py -k "load_monitor" -v
```

Expected: FAIL — `update_status()` does not poll the load monitor yet.

**Step 3: Implement load monitor polling in update_status()**

In `host_manager.py`, in `OllamaHost.update_status()`, after the call to `self.update_models_and_vram_from_api()`, add:

```python
        self._update_gpu_utilization()
```

Add the new method to `OllamaHost`:

```python
    def _update_gpu_utilization(self) -> None:
        """Poll the load monitor endpoint and update gpu_utilization_pct. Fails open."""
        if not self.load_monitor_url:
            return
        try:
            response = requests.get(f"{self.load_monitor_url}/metrics", timeout=3)
            if response.status_code != 200:
                logger.warning("Load monitor %s returned HTTP %d — using 0%%",
                               self.load_monitor_url, response.status_code)
                return
            data = response.json()
            raw = data.get("gpu_utilization_pct")
            if not isinstance(raw, (int, float)):
                logger.warning("Load monitor %s returned non-numeric gpu_utilization_pct: %r",
                               self.load_monitor_url, raw)
                return
            self.gpu_utilization_pct = min(float(raw), 100.0)
            logger.info("Host %s GPU utilization: %.1f%%", self.url, self.gpu_utilization_pct)
        except Exception as exc:
            logger.warning("Could not reach load monitor %s: %s — failing open",
                           self.load_monitor_url, exc)
```

**Step 4: Run — verify all tests pass**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass.

**Step 5: Commit**

```bash
git add manage_ollama/ollama_proxy/host_manager.py manage_ollama/ollama_proxy/tests/test_host_manager.py
git commit --author="lunatic <lunatic@discord-bot>" -m "feat: poll GPU load monitor in update_status() with fail-open error handling"
```

---

## Task 7: Proxy — GPU-aware routing in get_best_host() (TDD)

**Files:**
- Modify: `manage_ollama/ollama_proxy/tests/test_host_manager.py`
- Modify: `manage_ollama/ollama_proxy/host_manager.py`

**Step 1: Write failing tests**

Add to `test_host_manager.py`:

```python
# ---------------------------------------------------------------------------
# GPU-aware routing in get_best_host()
# ---------------------------------------------------------------------------

@pytest.fixture
def two_host_manager(mocker):
    """HostManager with two hosts, both available, model on disk on both."""
    mocker.patch.object(HostManager, 'load_config', return_value=None)
    hm = HostManager('dummy.json')
    h1 = OllamaHost({"url": "http://h1:11434", "total_vram_mb": 16000,
                     "load_monitor_url": "http://h1:9091", "gpu_load_threshold_pct": 80})
    h2 = OllamaHost({"url": "http://h2:11434", "total_vram_mb": 16000,
                     "load_monitor_url": "http://h2:9091", "gpu_load_threshold_pct": 80})
    for h in (h1, h2):
        h.available = True
        h.free_vram_mb = 8000
        h.local_models = ["llama3"]
        h.loaded_models = []
    hm.hosts = [h1, h2]
    return hm, h1, h2


def test_routing_excludes_overloaded_host_when_alternative_exists(two_host_manager):
    """Host above GPU threshold is skipped when an alternative is available."""
    hm, h1, h2 = two_host_manager
    h1.gpu_utilization_pct = 90   # above threshold
    h2.gpu_utilization_pct = 30   # below threshold

    result = hm.get_best_host("llama3")
    assert result.url == "http://h2:11434"


def test_routing_fallback_when_all_hosts_above_threshold(two_host_manager):
    """If all hosts exceed threshold, falls back to VRAM routing (does not fail)."""
    hm, h1, h2 = two_host_manager
    h1.gpu_utilization_pct = 90
    h2.gpu_utilization_pct = 95
    h1.free_vram_mb = 8000
    h2.free_vram_mb = 4000

    result = hm.get_best_host("llama3")
    # Falls back → picks h1 (most free VRAM)
    assert result is not None
    assert result.url == "http://h1:11434"


def test_routing_no_load_monitor_behaves_as_before(mocker):
    """Hosts without load_monitor_url are never filtered by GPU threshold."""
    mocker.patch.object(HostManager, 'load_config', return_value=None)
    hm = HostManager('dummy.json')
    h1 = OllamaHost({"url": "http://h1:11434", "total_vram_mb": 8000})
    h1.available = True
    h1.free_vram_mb = 4000
    h1.local_models = ["llama3"]
    h1.loaded_models = []
    hm.hosts = [h1]

    result = hm.get_best_host("llama3")
    assert result.url == "http://h1:11434"
```

**Step 2: Run — verify tests fail**

```bash
python -m pytest tests/test_host_manager.py -k "routing_excludes or routing_fallback or routing_no_load" -v
```

Expected: `test_routing_excludes_overloaded_host_when_alternative_exists` FAILS (overloaded host still returned), others may pass by coincidence.

**Step 3: Modify get_best_host() to build preferred_pool**

In `host_manager.py`, inside `get_best_host()`, replace the line:

```python
            available_hosts = sorted(
                [h for h in self.hosts if h.is_available() and h.url not in excluded_urls],
                key=lambda h: h.priority or float('inf')
            )
```

with:

```python
            available_hosts = sorted(
                [h for h in self.hosts if h.is_available() and h.url not in excluded_urls],
                key=lambda h: h.priority or float('inf')
            )
            # Build preferred pool: hosts below GPU threshold.
            # Hosts with no load_monitor_url are always included (fail open).
            preferred_hosts = [
                h for h in available_hosts
                if h.load_monitor_url is None
                or h.gpu_utilization_pct < h.gpu_load_threshold_pct
            ]
            # Fall back to all available hosts if every host is above threshold.
            routing_hosts = preferred_hosts if preferred_hosts else available_hosts
            logger.info(
                "GPU routing: %d preferred hosts (below threshold), %d total available.",
                len(preferred_hosts), len(available_hosts)
            )
```

Then replace every subsequent reference to `available_hosts` within the method body **after this block** with `routing_hosts`. There are four places: the `loaded_hosts`, `local_hosts`, `available_hosts` (best-by-VRAM loop), and `available_hosts` (eviction loop). Change each to `routing_hosts`.

**Step 4: Run — verify all tests pass**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass.

**Step 5: Commit**

```bash
git add manage_ollama/ollama_proxy/host_manager.py manage_ollama/ollama_proxy/tests/test_host_manager.py
git commit --author="lunatic <lunatic@discord-bot>" -m "feat: GPU-threshold pre-filter in get_best_host() with VRAM fallback"
```

---

## Task 8: Deployment files

**Files:**
- Create: `manage_ollama/dependencies/gpu_monitor/gpu_monitor.service`
- Create: `manage_ollama/dependencies/gpu_monitor/rsyslog_gpu_monitor.conf`
- Create: `manage_ollama/dependencies/gpu_monitor/logrotate_gpu_monitor.conf`
- Create: `manage_ollama/dependencies/gpu_monitor/install_linux.sh`
- Create: `manage_ollama/dependencies/gpu_monitor/install_windows.ps1`

**Step 1: Create the files**

`manage_ollama/dependencies/gpu_monitor/gpu_monitor.service`:
```ini
[Unit]
Description=GPU utilization monitor for Ollama proxy
After=network.target

[Service]
Type=simple
User=gpu_monitor
WorkingDirectory=/opt/gpu_monitor
ExecStart=/opt/gpu_monitor/.venv/bin/python /opt/gpu_monitor/gpu_monitor.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`manage_ollama/dependencies/gpu_monitor/rsyslog_gpu_monitor.conf`:
```
if $programname == 'gpu_monitor' then /var/log/gpu_monitor.log
& stop
```

`manage_ollama/dependencies/gpu_monitor/logrotate_gpu_monitor.conf`:
```
/var/log/gpu_monitor.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    postrotate
        systemctl restart rsyslog > /dev/null 2>&1 || true
    endscript
}
```

`manage_ollama/dependencies/gpu_monitor/install_linux.sh`:
```bash
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
```

`manage_ollama/dependencies/gpu_monitor/install_windows.ps1`:
```powershell
#Requires -RunAsAdministrator
param(
    [string]$InstallDir = "C:\opt\gpu_monitor",
    [string]$NssmPath = "nssm.exe"
)

Write-Host "Installing gpu_monitor to $InstallDir..."

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item "$PSScriptRoot\..\..\gpu_monitor\gpu_monitor.py" $InstallDir
Copy-Item "$PSScriptRoot\..\..\gpu_monitor\requirements.txt" $InstallDir

# Create venv and install deps
python -m venv "$InstallDir\.venv"
& "$InstallDir\.venv\Scripts\pip.exe" install --upgrade pip -q
& "$InstallDir\.venv\Scripts\pip.exe" install -r "$InstallDir\requirements.txt" -q

# Register Windows service via NSSM
& $NssmPath install gpu_monitor "$InstallDir\.venv\Scripts\python.exe"
& $NssmPath set gpu_monitor AppParameters "$InstallDir\gpu_monitor.py"
& $NssmPath set gpu_monitor AppDirectory $InstallDir
& $NssmPath set gpu_monitor Start SERVICE_AUTO_START
& $NssmPath start gpu_monitor

Write-Host "gpu_monitor service installed and started."
```

**Step 2: Make install script executable**

```bash
chmod +x manage_ollama/dependencies/gpu_monitor/install_linux.sh
```

**Step 3: Commit**

```bash
git add manage_ollama/dependencies/gpu_monitor/
git commit --author="lunatic <lunatic@discord-bot>" -m "feat: add deployment files for gpu_monitor (systemd, rsyslog, logrotate, install scripts)"
```

---

## Task 9: README for gpu_monitor

**Files:**
- Create: `manage_ollama/gpu_monitor/README.md`

**Step 1: Write README**

`manage_ollama/gpu_monitor/README.md`:
```markdown
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
```

**Step 2: Commit**

```bash
git add manage_ollama/gpu_monitor/README.md
git commit --author="lunatic <lunatic@discord-bot>" -m "docs: add gpu_monitor README"
```

---

## Final Verification

Run the full test suite one last time from the proxy directory:

```bash
cd manage_ollama/ollama_proxy
python -m pytest tests/ -v
```

And from the gpu_monitor directory:

```bash
cd manage_ollama/gpu_monitor
python -m pytest tests/ -v
```

Expected: all tests pass, 0 failures.
