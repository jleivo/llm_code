# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.1] - 2026-05-11

### Added

- `start_llama.ps1` PowerShell script for managing both llama-server processes

### Changed

- `start_llama.bat` now delegates to PowerShell script for process management

### Fixed

- Ctrl+C only killed the chat server, leaving the embedding server running.
  Both servers are now stopped together on interrupt.

## [1.0.0] - 2026-05-11

### Added

- `start_llama.bat` to launch llama-server for embedding (port 8081) and
  chat router with model swapping (port 8080)

[Unreleased]: https://github.com/juha/llm_code/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/juha/llm_code/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/juha/llm_code/releases/tag/v1.0.0
