# llama.cpp Server Scripts

Scripts for running local LLM inference using llama.cpp with model swapping and
embedding support.

## Overview

Starts two llama-server instances:

| Server | Port | Purpose |
|---|---|---|
| Embedding | 8081 | Snowflake Arctic Embed (vector embeddings) |
| Chat Router | 8080 | Model-swapping chat server with preset config |

The chat router supports hot-swapping between multiple models defined in
`llama-models.ini` without restarting the server.

## Usage

### Windows (double-click)

Double-click `start_llama.bat`. Both servers run in the same console window.
Press Ctrl+C to stop both servers gracefully.

### Windows (PowerShell)

```powershell
.\start_llama.ps1
```

### Configuration

Edit `llama-models.ini` to configure chat models. See the file for format
details, including global settings (`[*]`) and per-model overrides.

## Requirements

- llama-server.exe (Vulkan build recommended for AMD/Intel GPUs)
- Windows PowerShell 5.1+ or PowerShell 7+

## Ports

| Port | Service | Protocol |
|---|---|---|
| 8080 | Chat API (OpenAI-compatible) | HTTP |
| 8081 | Embedding API | HTTP |
