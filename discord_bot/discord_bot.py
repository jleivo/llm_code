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
        return list(entry["messages"])

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
