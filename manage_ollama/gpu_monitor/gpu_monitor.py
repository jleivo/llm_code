#!/usr/bin/env python3
# 0.1.0
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
_test_mode: bool = False


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
    if _test_mode:
        # In test mode, we want to poll once synchronously to populate _metrics
        global _metrics, _healthy
        try:
            data = _read_nvidia() if PLATFORM_LINUX else _read_amd()
            _metrics = data
            _healthy = True
        except Exception as exc:
            logger.warning("Failed to read GPU metrics in test mode: %s", exc)
            _healthy = False
        return

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
