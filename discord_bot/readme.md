A repository for testing LLM stuff.

## Discord bot

Simple code to run an bot powered by LLM in discord.
Expects mistral model, with large context window (32k)

### features

Has 15 minute long chat history. If a discussion starts after 15 minutes of silence, the chat history is wiped.
Parses URLs posted in messages. Can be used to summarize stuff.
Has the magic word "forget", which resets the chat memmory.