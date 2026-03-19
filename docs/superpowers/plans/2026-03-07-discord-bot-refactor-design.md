# Discord Bot Refactor Design

**Date:** 2026-03-07

## Summary

Refactor `discord_bot/discord_bot.py` to:
1. Replace the hardcoded Ollama API with an OpenAI-compatible API client
2. Move model and system prompt configuration to a `config.ini` file
3. Add spontaneous sarcastic participation (bot joins channel conversations unprompted every 5–15 messages)
4. Clean up code bugs and the JSON string hack

## Configuration

A `config.ini` file lives next to `discord_bot.py`. The Discord token stays in `.env`.

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

## Spontaneous Participation

Per-channel state:
- `message_counter` — increments on every non-bot message, resets after triggering
- `trigger_threshold` — random int in `[spontaneous_min, spontaneous_max]`, re-rolled each trigger
- `active_rounds_remaining` — when > 0, bot responds to any message in that channel

Flow per incoming message:
1. Increment per-channel `message_counter`
2. If `active_rounds_remaining > 0` → respond, decrement `active_rounds_remaining`
3. Else if `counter >= trigger_threshold` → post snarky unprompted comment, set `active_rounds_remaining = active_rounds`, reset counter, re-roll threshold
4. If @mentioned → always respond (independent of spontaneous state)

## Code Structure

Single file `discord_bot.py`:

- **`ConversationHistory`** class: wraps per-source message history as `list[dict]`, with TTL expiry logic
- **`ChannelState`** dataclass: `message_counter`, `trigger_threshold`, `active_rounds_remaining`
- **`generate_response(messages: list[dict]) -> str`**: calls OpenAI-compatible API; injects system prompt as first message
- **`prepare_llm_message(user_message, source) -> list[dict]`**: fetches history, appends user message, handles URL extraction
- **`on_message`**: dispatches based on mention / active mode / spontaneous threshold
- URL fetching + BeautifulSoup: kept as-is
- `forget` command: kept

## Bugs Fixed

- Remove unused `from email.mime import message` import
- Replace JSON string list hack with proper `list[dict]` throughout
- Proper exception logging with traceback instead of `print("Unknown thing?")`
- Config loaded once at startup, nothing hardcoded in code

## Files Changed

- `discord_bot/discord_bot.py` — full rewrite
- `discord_bot/config.ini` — new file (created from template)
- `discord_bot/requirements.txt` — add `openai` package
- `discord_bot/readme.md` — update installation instructions

## Files Retired

- `modelfiles/lunatic_leivo_model.modelfile` — no longer needed (system prompt now in config)
- `discord_bot/dependencies/Lunatic_leivo.modelfile` — no longer needed
