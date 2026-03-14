# Changelog

All notable changes to update scripts will be documented in this file.

## [1.2.0] - 2026-03-14

### Changed
- Replaced `.env` file secret loading with HashiCorp Vault AppRole authentication
- API key now fetched live from `secret/hosts/<hostname>/open_terminal_apikey` on each run

## [1.0.0] - 2026-03-07

### Added
- Initial version of update_open-webui.sh with docker container update and restart logic
- Docker image verification before container restart
- Proper error handling with `set -euo pipefail`
- Container cleanup and removal on update

### Changed
- Added version header to update_open-webui.sh for alignment with repository standards

