# Ollama Proxy

A lightweight, intelligent proxy for Ollama that monitors multiple Ollama hosts and routes requests based on model availability and host resources.

## Features

- **Host Monitoring:** Continuously monitors the availability, free VRAM, and loaded models of each configured Ollama host.
- **Smart Routing:** For new conversations, it selects the most suitable host that has the requested model loaded and sufficient VRAM.
- **Transparent Session Stickiness:** Automatically maintains chat context without any changes to your client code.
    - **Session ID:** A unique session is identified by the combination of your IP address, the requested model, and the content of the first user message in a conversation.
    - **Timeout:** Sessions are automatically forgotten after 15 minutes of inactivity, allowing for dynamic load balancing.
- **Transparent Proxying:** Streams requests and responses to and from the Ollama API without modification, ensuring full compatibility.
- **Configuration via JSON:** Easily manage your Ollama hosts through a `config.json` file.
- **Logging:** Logs host status changes, routing decisions, and session lifecycle events for easy monitoring and debugging.

## Setup

1.  **Configuration:**
    - Rename `config.json.example` to `config.json`.
    - Edit `config.json` to define your Ollama hosts. Each host configuration requires:
        - `url`: The base URL of the Ollama API (e.g., `http://192.168.1.100:11434`).
        - `ssh_host`, `ssh_user`, `ssh_pass`: (Optional) SSH credentials for the host. These are required for the proxy to monitor the host's VRAM using `nvidia-smi`. If not provided, VRAM will not be a factor in routing decisions for this host.

    **Example `config.json`:**
    ```json
    {
      "hosts": [
        {
          "url": "http://ollama-host-1:11434",
          "ssh_host": "ollama-host-1",
          "ssh_user": "your_user",
          "ssh_pass": "your_password"
        },
        {
          "url": "http://ollama-host-2:11434"
        }
      ]
    }
    ```

2.  **Install Dependencies:**
    - Install the required Python packages using pip:
      ```bash
      pip install -r requirements.txt
      ```

## Running the Proxy

To start the proxy server, run the `main.py` script:

```bash
python main.py
```

The proxy will start listening on `http://0.0.0.0:8080` by default.

## Usage

Send your Ollama API requests to the proxy server's address (e.g., `http://localhost:8080`) instead of directly to an Ollama host. The proxy handles the rest. Session management is completely transparent.

**Example `curl` request:**

```bash
curl http://localhost:8080/api/chat -d '{
  "model": "llama3",
  "messages": [
    {
      "role": "user",
      "content": "Why is the sky blue?"
    }
  ],
  "stream": false
}'
```

The proxy will automatically create a session for this conversation. Subsequent requests from the same IP, for the same model, and starting with the same initial prompt will be routed to the same Ollama host until the session expires.

## Testing

This project uses `pytest` for automated testing. The tests mock all external network calls (to Ollama hosts) and allow for verification of the proxy's routing and session logic in a controlled environment.

1.  **Install Development Dependencies:**
    ```bash
    pip install -r requirements-dev.txt
    ```

2.  **Run Tests:**
    To run the full test suite, execute the following command from the root of the `ollama_proxy` directory:
    ```bash
    pytest
    ```