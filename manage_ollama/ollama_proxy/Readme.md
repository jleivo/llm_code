# Ollama Proxy

A lightweight, intelligent proxy for Ollama that monitors multiple Ollama hosts and routes requests based on model availability and host resources.

## Features

- **Host Monitoring:** Continuously monitors the availability, free VRAM, and loaded models of each configured Ollama host.
- **Smart Routing:** For new conversations, it selects the most suitable host that has the requested model loaded and sufficient VRAM.
- **Transparent Session Stickiness:** Automatically maintains chat context without any changes to your client code.
    - **Session ID:** A unique session is identified by the combination of your IP address, the requested model, and the content of the first user message in a conversation.
    - **Timeout:** Sessions are automatically forgotten after 15 minutes of inactivity.
    - **Failover:** If a host assigned to a session becomes unavailable, the proxy automatically re-routes the next request to the new best host.
- **Transparent Proxying:** Streams requests and responses to and from the Ollama API without modification, ensuring full compatibility.
- **Configuration via JSON:** Easily manage your Ollama hosts through a `config.json` file.
- **Logging:** Logs host status changes, routing decisions, and session lifecycle events to both the console and a `proxy.log` file.

## Setup

### Automatic

1. run install.sh. This will configure the host, including adding the systemd integration.

```bash
./install.sh
```

### Manual

1.  **Configuration:**
    - Rename `config.json.example` to `config.json`.
    - Edit `config.json` to define your Ollama hosts. Each host configuration requires:
        - `url`: The base URL of the Ollama API (e.g., `http://192.168.1.100:11434`).
        - `total_vram_mb`: This is the amount of VRAM available on the host in MiB.
        - priority (optional), defines which host to use in case of multiple options.

    **Example `config.json`:**
    ```json
    {
      "hosts": [
        {
          "url": "http://ollama-host-1:11434",
          "total_vram_mb": 16384,
          "piority": 1
        },
        {
          "url": "http://host2:11434",
          "total_vram_mb": 8192
        }
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

## Testing

This project uses `pytest` for automated testing. The tests mock all external network calls and verify the proxy's routing and session logic in a controlled environment.

1.  **Install Development Dependencies:**
    ```bash
    pip install -r requirements-dev.txt
    ```

2.  **Run Tests:**
    To run the full test suite, execute the following command from the project root (`ollama-proxy` directory):
    ```bash
    pytest
    ```

## Deployment

The project includes a deployment script (`mgmt/deploy.sh`) that simplifies deploying the proxy to a target system. The script copies the essential files needed to run the proxy:
- `host_manager.py`
- `main.py`
- `requirements.txt`
- `install.sh`

### Usage

```bash
./mgmt/deploy.sh -d user@target:/path/to/destination
```

Options:
- `-d` : (Required) The SCP-compliant destination path where the files should be copied
- `-v` : Enable verbose/debug output
- `-h` : Display help message

Example:
```bash
./mgmt/deploy.sh -d admin@proxy-server:/opt/ollama-proxy
```

After deployment, follow the setup instructions above on the target system to configure and run the proxy.