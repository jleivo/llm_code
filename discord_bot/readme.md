# Discord Bot

LLM-powered Discord bot with a sarcastic personality. Responds when @mentioned or in DMs,
and spontaneously joins channel conversations every 5–15 messages for a few rounds.

## Features

- Responds to @mentions and private DMs
- Spontaneously joins channel discussions (configurable frequency and active rounds)
- 15-minute conversation history per source (configurable)
- `forget` command to reset history
- URL parsing — paste a link and the bot will read and comment on it
- Works with any OpenAI-compatible API (Ollama, LiteLLM, etc.)

## Installation

Run the installation script as a user with `sudo` privileges:

```bash
bash discord_bot/install.sh
```

The script will:

1. Ask for the install directory (default `/srv/LunaticLeivoModel`)
2. Create the `lunatic` system user if needed
3. Copy bot files and set up the Python virtual environment
4. Walk through all `config.ini` settings and the Discord token
5. Configure rsyslog, logrotate, and the systemd service

On subsequent runs it re-confirms all configuration and upgrades Python packages.

## Known Issues

- URL scraping has no size limit; very large pages may slow responses
