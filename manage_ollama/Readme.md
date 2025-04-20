# Ollama Model Update Script
=======
# Scripts to manage Ollama

- [Scripts to manage Ollama](#scripts-to-manage-ollama)
- [Ollama Model Update](#ollama-model-update)
  - [Description](#description)
- [Load Daily Driver Models](#load-daily-driver-models)
  - [Description](#description-1)

# Ollama Model Update

## Description

This Bash script updates models in the `ollama` container, excluding those listed in an exclusion file.

[Documentation](docs/update_models.md)


# Load Daily Driver Models

## Description

This bash script loads models in to Ollama if GPU have enough free VRAM. Models are kept in GPU memory indefinitely until some other model requires the space.

[Documentation](docs/daily_drivers.md)

# Printout Proxy Server

Simple debugging tool to see the messages being passed to Ollama.

This Python `printout_proxy.py` script sets up a simple HTTP proxy server that forwards requests to another server running on `localhost:11434`. It supports various HTTP methods (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS) and prints the response headers and body from the target server.

## Usage

To run the proxy server:
```bash
./printout_proxy.py
```
The proxy will listen on port 8888. Redirect your requests to http://localhost:8888 to use this proxy.

## Dependencies

- Python 3.x
- requests library (pip install requests)

## Notes

- The script excludes certain headers like 'Host', 'Content-Length', and 'Transfer-Encoding' when forwarding the request.
- The response from the target server is printed, including its status code, reason phrase, headers, and body (if any).
- Error handling is implemented to send a 500 Internal Server Error in case of exceptions.
