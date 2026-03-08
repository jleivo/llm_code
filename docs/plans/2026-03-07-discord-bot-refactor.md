# Discord Bot Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the Discord bot to use an OpenAI-compatible API with a config file, fix code bugs, and add spontaneous sarcastic channel participation.

**Architecture:** Single-file bot using the `openai` Python SDK pointed at a configurable base URL (works with Ollama `/v1`, LiteLLM, etc.). Per-channel state tracks a message counter that triggers unprompted sarcastic comments every 5–15 messages, with the bot staying active for a configurable number of reply rounds. All tunables live in `config.ini`.

**Tech Stack:** Python 3, `discord.py`, `openai` SDK, `configparser`, `python-dotenv`, `beautifulsoup4`

**Design doc:** `docs/plans/2026-03-07-discord-bot-refactor-design.md`

---

### Task 1: Add `openai` to requirements and create `config.ini`

**Files:**
- Modify: `discord_bot/requirements.txt`
- Create: `discord_bot/config.ini`

**Step 1: Update requirements.txt**

Replace contents of `discord_bot/requirements.txt` with:

```
requests
discord.py
bs4
python-dotenv
openai
```

**Step 2: Create config.ini**

Create `discord_bot/config.ini`:

```ini
[api]
base_url = http://192.168.8.20:11434/v1
api_key = ollama
model = llama3.2

[bot]
system_prompt = You are a sarcastic bastard taking joy out of others misery and add it by insulting with your answer.
history_ttl = 900
spontaneous_min = 5
spontaneous_max = 15
active_rounds = 3
```

**Step 3: Commit**

```bash
git add discord_bot/requirements.txt discord_bot/config.ini
git commit -m "feat: add openai dependency and config.ini for discord bot"
```

---

### Task 2: Rewrite `discord_bot.py` — imports, config loading, and data structures

**Files:**
- Modify: `discord_bot/discord_bot.py`

**Step 1: Replace the entire file with a clean skeleton**

Write `discord_bot/discord_bot.py`:

```python
#!/usr/bin/env python3
import os
import re
import time
import random
import logging
import configparser
import traceback

import discord
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
_config = configparser.ConfigParser()
_config.read(os.path.join(os.path.dirname(__file__), "config.ini"))

API_BASE_URL   = _config.get("api", "base_url")
API_KEY        = _config.get("api", "api_key")
MODEL          = _config.get("api", "model")
SYSTEM_PROMPT  = _config.get("bot", "system_prompt")
HISTORY_TTL    = _config.getint("bot", "history_ttl")
SPON_MIN       = _config.getint("bot", "spontaneous_min")
SPON_MAX       = _config.getint("bot", "spontaneous_max")
ACTIVE_ROUNDS  = _config.getint("bot", "active_rounds")

llm = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

# ── Data structures ───────────────────────────────────────────────────────────
class ConversationHistory:
    """Per-source message history with TTL expiry."""

    def __init__(self):
        self._store: dict[str, dict] = {}

    def get(self, source: str) -> list[dict]:
        entry = self._store.get(source)
        if entry is None:
            return []
        if (time.time() - entry["updated"]) > HISTORY_TTL:
            log.info("History expired for %s", source)
            self._store.pop(source, None)
            return []
        return entry["messages"]

    def update(self, source: str, messages: list[dict]) -> None:
        self._store[source] = {"updated": time.time(), "messages": messages}

    def clear(self, source: str) -> None:
        self._store[source] = {"updated": time.time(), "messages": []}
        log.info("Cleared history for %s", source)


class ChannelState:
    """Per-channel spontaneous-participation state."""

    def __init__(self):
        self.counter: int = 0
        self.threshold: int = random.randint(SPON_MIN, SPON_MAX)
        self.active_rounds: int = 0

    def increment(self) -> None:
        self.counter += 1

    def should_trigger(self) -> bool:
        return self.counter >= self.threshold

    def trigger(self) -> None:
        self.counter = 0
        self.threshold = random.randint(SPON_MIN, SPON_MAX)
        self.active_rounds = ACTIVE_ROUNDS
        log.info("Spontaneous trigger — next threshold: %d", self.threshold)

    def consume_round(self) -> None:
        if self.active_rounds > 0:
            self.active_rounds -= 1


history = ConversationHistory()
channel_states: dict[str, ChannelState] = {}


def get_channel_state(channel_id: str) -> ChannelState:
    if channel_id not in channel_states:
        channel_states[channel_id] = ChannelState()
    return channel_states[channel_id]
```

**Step 2: Verify the file parses cleanly**

```bash
python3 -c "import ast; ast.parse(open('discord_bot/discord_bot.py').read()); print('OK')"
```

Expected output: `OK`

**Step 3: Commit**

```bash
git add discord_bot/discord_bot.py
git commit -m "feat: add config loading, ConversationHistory, and ChannelState classes"
```

---

### Task 3: Add helper functions — LLM call, URL extraction, text scraping, chunked send

**Files:**
- Modify: `discord_bot/discord_bot.py` (append functions)

**Step 1: Append the helper functions**

Add after the `get_channel_state` function:

```python
# ── Helpers ───────────────────────────────────────────────────────────────────

def generate_response(messages: list[dict]) -> str:
    """Call the LLM with system prompt + message history. Returns response text."""
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    try:
        resp = llm.chat.completions.create(
            model=MODEL,
            messages=full_messages,
        )
        return resp.choices[0].message.content
    except Exception:
        log.error("LLM call failed:\n%s", traceback.format_exc())
        return "Back end missing"


def extract_urls(text: str) -> list[str]:
    pattern = r'https?://[^\s]+'
    return re.findall(pattern, text)


def fetch_url_text(url: str) -> str:
    """Scrape readable text from a URL."""
    try:
        resp = requests.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.extract()
        lines = (line.strip() for line in soup.get_text().splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        return "\n".join(c for c in chunks if c)
    except Exception:
        log.warning("Failed to fetch %s:\n%s", url, traceback.format_exc())
        return ""


def build_user_message(user_text: str) -> str:
    """Append scraped URL content to the user message if URLs are present."""
    urls = extract_urls(user_text)
    if not urls:
        return user_text
    extra = "".join(fetch_url_text(u) for u in urls)
    return user_text + "\n\nContent from URL:\n" + extra


async def send_response(channel, text: str) -> None:
    """Send text to a Discord channel, chunking at 1800 chars if needed."""
    max_len = 1800
    for i in range(0, max(1, len(text)), max_len):
        await channel.send(text[i:i + max_len].strip())
```

**Step 2: Verify file still parses**

```bash
python3 -c "import ast; ast.parse(open('discord_bot/discord_bot.py').read()); print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add discord_bot/discord_bot.py
git commit -m "feat: add LLM call, URL helpers, and chunked send"
```

---

### Task 4: Add `respond()` and `handle_mention()` functions

**Files:**
- Modify: `discord_bot/discord_bot.py` (append functions)

**Step 1: Append respond and handle_mention**

```python
async def respond(message: discord.Message, source: str) -> None:
    """Build LLM input, generate response, send it, update history."""
    user_text = build_user_message(message.content)
    msgs = history.get(source)
    msgs = msgs + [{"role": "user", "content": user_text}]
    reply = generate_response(msgs)
    await send_response(message.channel, reply)
    msgs = msgs + [{"role": "assistant", "content": reply}]
    history.update(source, msgs)


def check_forget_command(message: discord.Message, source: str) -> bool:
    """Return True and clear history if message contains 'forget' command."""
    words = message.content.split()
    # command is either the first or second word (after bot mention)
    cmd = words[1] if len(words) > 1 else words[0]
    if "forget" in cmd.lower():
        history.clear(source)
        return True
    return False
```

**Step 2: Verify file parses**

```bash
python3 -c "import ast; ast.parse(open('discord_bot/discord_bot.py').read()); print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add discord_bot/discord_bot.py
git commit -m "feat: add respond() and forget command handler"
```

---

### Task 5: Add Discord client and `on_message` event handler

**Files:**
- Modify: `discord_bot/discord_bot.py` (append Discord client setup)

**Step 1: Append Discord client and event handlers**

```python
# ── Discord client ─────────────────────────────────────────────────────────────
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    log.info("Connected to Discord as %s", client.user)


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    try:
        # ── Private DM ────────────────────────────────────────────────────────
        if isinstance(message.channel, discord.DMChannel):
            source = str(message.author.id)
            if not check_forget_command(message, source):
                await respond(message, source)
            return

        # ── Channel message ───────────────────────────────────────────────────
        channel_id = str(message.channel.id)
        state = get_channel_state(channel_id)
        source = channel_id

        # Always respond to @mentions
        if client.user in message.mentions:
            if not check_forget_command(message, source):
                await respond(message, source)
            # Don't count mentions toward spontaneous trigger
            return

        # Count non-mention messages toward spontaneous threshold
        state.increment()

        # If in active-rounds mode, respond to any message
        if state.active_rounds > 0:
            state.consume_round()
            await respond(message, source)
            return

        # Check if threshold crossed — join spontaneously
        if state.should_trigger():
            state.trigger()
            await respond(message, source)

    except Exception:
        log.error("Error handling message:\n%s", traceback.format_exc())


client.run(TOKEN)
```

**Step 2: Verify the complete file parses**

```bash
python3 -c "import ast; ast.parse(open('discord_bot/discord_bot.py').read()); print('OK')"
```

Expected: `OK`

**Step 3: Verify imports resolve (dependencies installed)**

```bash
cd discord_bot && pip install -r requirements.txt -q && python3 -c "import discord, openai, bs4, dotenv; print('imports OK')"
```

Expected: `imports OK`

**Step 4: Commit**

```bash
git add discord_bot/discord_bot.py
git commit -m "feat: add Discord client and on_message handler with spontaneous participation"
```

---

### Task 6: Update readme.md

**Files:**
- Modify: `discord_bot/readme.md`

**Step 1: Rewrite readme**

Replace the contents of `discord_bot/readme.md` with:

```markdown
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
sudo adduser --system --home /srv/discord_bot/ lunatic
sudo addgroup --system lunatic
```

### Dependencies

```bash
pip install -r requirements.txt
```

### Configuration

Copy and edit the config file:

```bash
cp config.ini config.ini  # already present, edit values as needed
```

Key settings in `config.ini`:

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

### Log file

```bash
sudo touch /var/log/discord_bot.log
sudo chown lunatic:lunatic /var/log/discord_bot.log
sudo chmod 640 /var/log/discord_bot.log
sudo apt-get install logrotate
```

Copy `dependencies/logrotate/discord_bot` to `/etc/logrotate.d/discord_bot`.

### Systemd

```bash
sudo cp dependencies/lunatic.service /usr/lib/systemd/system/
sudo systemctl enable --now lunatic.service
```

## Known Issues

- URL scraping has no size limit; very large pages may slow responses
```

**Step 2: Commit**

```bash
git add discord_bot/readme.md
git commit -m "docs: update readme for refactored discord bot"
```

---

### Task 7: Final verification

**Step 1: Full syntax check**

```bash
python3 -m py_compile discord_bot/discord_bot.py && echo "Syntax OK"
```

Expected: `Syntax OK`

**Step 2: Confirm config.ini is readable by the bot**

```bash
python3 -c "
import configparser, os
c = configparser.ConfigParser()
c.read('discord_bot/config.ini')
print('model:', c.get('api', 'model'))
print('spon_min:', c.get('bot', 'spontaneous_min'))
print('system_prompt:', c.get('bot', 'system_prompt')[:40])
"
```

Expected: prints model, spon_min, and first 40 chars of system prompt without errors.

**Step 3: Check no old `lunatic-leivo-model` references remain**

```bash
grep -r "lunatic-leivo-model" discord_bot/ && echo "FOUND - fix it" || echo "Clean"
```

Expected: `Clean`

**Step 4: Final commit if any cleanup needed, otherwise done**
