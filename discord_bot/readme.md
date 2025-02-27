# Discord bot

Simple code to run an bot powered by LLM in discord.

## features

- Has 15 minute long chat history. If a discussion starts after 15 minutes of silence, it starts from zero.
- Has the magic word "forget", which resets the chat memmory.
- Can do private & channel discussions. Has per person chat history.
- Parses URLs posted in messages. Can be used to summarize stuff.

## Installation

### application user

```bash
sudo adduser adduser --system --home /srv/discord_bot/ lunatic
sudo addgroup --system lunatic
```
### Discord token

The application needs a Discord token, which should be stored in .env-file, or 
preferably provided on the fly when the process is started

```text
DISCORD_TOKEN=
```
Token you can get by creating a Discord app. Google for guidance on this area.

### log-file

The wrapper function redirects the python output to /var/log/discord_bot.log -file by default.

```bash
sudo touch /var/log/discord_bot.log
sudo chown lunatic:lunatic /var/log/discord_bot.log
sudo chmod 640 /var/log/discord_bot.log
sudo apt-get install logrotate
```
copy the `logrotate/discord_bot` file to `/etc/logrotate.d/discord_bot`

### Ollama model

you need to import the ollama model file `Lunatic_leivo_modelfile'  lunatic-leivo-model

```bash
ollama create lunatic-leivo-model --file Lunatic_leivoZZ.modelfile
```

### Systemd configuration file

copy lunatic.service to `/usr/lib/systemd/system/`

enable systemd service
```bash
sudo systemctl enable lunatic.service
```

## Known issues

- Comprehensive error handling is missing.
- 