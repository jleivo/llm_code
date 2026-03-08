# Discord Bot Installation Script Design

Date: 2026-03-08

## Overview

A bash installation script (`discord_bot/install.sh`) that handles both fresh installs and updates of the Discord bot. It walks the user through all configuration interactively and sets up all system infrastructure.

## Flow

1. **Ask for install directory** — default `/srv/LunaticLeivoModel`
2. **Detect fresh vs existing install** based on whether the directory exists
3. **Copy bot files** — `discord_bot.py`, `requirements.txt` from repo to install dir
4. **venv + packages** — create venv if missing; always run `pip install -r requirements.txt --upgrade`
5. **Config walkthrough** — always runs:
   - `config.ini`: prompt for every key, showing current value as default if present; write with `version` key in `[meta]` section
   - `.env`: prompt for `DISCORD_TOKEN`, showing masked current value if present
6. **System infrastructure** — only if not already in place:
   - Create `lunatic` system user and group
   - Install rsyslog config and restart rsyslog
   - Install logrotate config
   - Install and enable systemd service

## Config Versioning

- `config.ini` contains a `[meta]` section with `version = <n>`
- Script has a hardcoded `CONFIG_VERSION=1`
- On existing installs: version mismatch is logged; walkthrough always runs regardless
- Future key additions: increment `CONFIG_VERSION` in the script; walkthrough naturally prompts for new keys

## Files

| File | Purpose |
|------|---------|
| `discord_bot/install.sh` | Installation script |
| `discord_bot/config.ini` | Updated to include `[meta] version = 1` |

## Success Criteria

- Fresh install: all infrastructure set up, bot running under systemd
- Existing install: bot files updated, packages upgraded, config re-confirmed
- Config always reflects current values after the script runs
