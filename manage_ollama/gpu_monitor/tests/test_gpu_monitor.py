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
        gm._test_mode = True
        gm.start_poll_thread(5)
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
        gm._test_mode = True
        gm.start_poll_thread(5)
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
        gm._test_mode = True
        gm.start_poll_thread(5)
        from fastapi.testclient import TestClient
        resp = TestClient(gm.app).get("/metrics")
        assert resp.status_code == 503
