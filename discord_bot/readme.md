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

### System user

```bash
sudo adduser --system --home /srv/discord_bot lunatic
sudo addgroup --system lunatic
```

### Dependencies

```bash
python3 -m venv /srv/discord_bot/.venv && source /srv/discord_bot/.venv/bin/activate
pip install -r requirements.txt
```

### Configuration

Edit `config.ini` with your settings:

| Key | Description |
|-----|-------------|
| `api.base_url` | OpenAI-compatible API base URL (e.g. `http://host:11434/v1` for Ollama) |
| `api.model` | Model name to use |
| `bot.system_prompt` | System prompt defining bot personality |
| `bot.spontaneous_min/max` | Range for messages between spontaneous interjections |
| `bot.active_rounds` | How many reply exchanges to stay active after interjecting |

### Discord token

Create `.env` next to `discord_bot.py`:

```
DISCORD_TOKEN=your_token_here
```

### Logging

The bot logs to syslog via the `LOCAL0` facility. Configure rsyslog to route those entries to a dedicated file:

```bash
sudo cp dependencies/rsyslog/discord_bot.conf /etc/rsyslog.d/discord_bot.conf
sudo systemctl restart rsyslog
```

Set up log rotation:

```bash
sudo cp dependencies/logrotate/discord_bot /etc/logrotate.d/discord_bot
```

### Systemd

```bash
sudo cp dependencies/lunatic.service /usr/lib/systemd/system/
sudo systemctl enable --now lunatic.service
```

## Known Issues

- URL scraping has no size limit; very large pages may slow responses
