# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2024-05-22
### Added
- Initial implementation of `gpu_monitor.py`.
- NVIDIA GPU utilization polling via `pynvml`.
- `/metrics` HTTP endpoint for Prometheus-style monitoring.
- Syslog logging on Linux and rotating file logging on Windows.
