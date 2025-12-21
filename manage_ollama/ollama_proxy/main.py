import json
import logging
import logging.handlers
import os
import time
import hashlib
import threading
import argparse
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, Response
import httpx
from host_manager import HostManager

# --- Basic Setup ---
# Manually configure the root logger to avoid conflicts.
script_dir = os.path.dirname(__file__)
log_file_path = os.path.join(script_dir, 'proxy.log')
root_logger = logging.getLogger()

# Debug: Check initial state
print(f"[LOGGER INIT DEBUG] Initial handlers: {root_logger.handlers}")
print(f"[LOGGER INIT DEBUG] Checking if handlers exist: {bool(root_logger.handlers)}")

# Default to INFO, can be overridden by command-line arg.
root_logger.setLevel(logging.INFO)

# Clear any existing handlers from other modules
if root_logger.handlers:
    print(f"[LOGGER INIT DEBUG] Clearing {len(root_logger.handlers)} existing handlers")
    for handler in root_logger.handlers[:]:  # Copy list to avoid modification during iteration
        root_logger.removeHandler(handler)
        print(f"[LOGGER INIT DEBUG] Removed handler: {type(handler).__name__}")

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
syslog_formatter = logging.Formatter('%(name)s[%(process)d]: %(levelname)s - %(message)s')

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)
print("[LOGGER INIT DEBUG] Added StreamHandler")

# File handler
file_handler = logging.FileHandler(log_file_path, mode='a')
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)
print(f"[LOGGER INIT DEBUG] Added FileHandler to {log_file_path}")

# Syslog handler with LOG_LOCAL7 facility for easy rsyslog filtering
syslog_handler = None
try:
    # Check if /dev/log exists
    if not os.path.exists('/dev/log'):
        print("[SYSLOG DEBUG] /dev/log does not exist. Trying UDP localhost:514")
        address = ('localhost', 514)
    else:
        print(f"[SYSLOG DEBUG] /dev/log found, permissions: {oct(os.stat('/dev/log').st_mode)}")
        address = '/dev/log'
    
    syslog_handler = logging.handlers.SysLogHandler(
        address=address,
        facility=logging.handlers.SysLogHandler.LOG_LOCAL7
    )
    syslog_handler.setFormatter(syslog_formatter)
    root_logger.addHandler(syslog_handler)
    print(f"[SYSLOG DEBUG] Successfully initialized SysLogHandler with address={address}")
    print(f"[SYSLOG DEBUG] Syslog facility: LOG_LOCAL7 (23)")
    print(f"[SYSLOG DEBUG] Current handlers: {[type(h).__name__ for h in root_logger.handlers]}")
except PermissionError as e:
    print(f"[SYSLOG DEBUG ERROR] Permission denied accessing syslog: {e}")
    print("[SYSLOG DEBUG] Trying fallback UDP connection to localhost:514")
    try:
        syslog_handler = logging.handlers.SysLogHandler(
            address=('localhost', 514),
            facility=logging.handlers.SysLogHandler.LOG_LOCAL7
        )
        syslog_handler.setFormatter(syslog_formatter)
        root_logger.addHandler(syslog_handler)
        print("[SYSLOG DEBUG] Successfully initialized fallback UDP SysLogHandler")
    except Exception as fallback_e:
        print(f"[SYSLOG DEBUG ERROR] Fallback also failed: {fallback_e}")
except Exception as e:
    print(f"[SYSLOG DEBUG ERROR] Failed to initialize SysLogHandler: {e}")
    print(f"[SYSLOG DEBUG ERROR] Exception type: {type(e).__name__}")

logger = logging.getLogger(__name__)

# --- Logging Diagnostics ---
def print_logging_diagnostics():
    """Print detailed information about the current logging configuration."""
    print("\n" + "="*70)
    print("LOGGING CONFIGURATION DIAGNOSTICS")
    print("="*70)
    print(f"Root Logger Level: {logging.getLevelName(root_logger.level)}")
    print(f"Total Handlers: {len(root_logger.handlers)}")
    for i, handler in enumerate(root_logger.handlers):
        handler_type = type(handler).__name__
        handler_level = logging.getLevelName(handler.level) if handler.level else "NOTSET"
        print(f"\n  Handler {i+1}: {handler_type}")
        print(f"    Level: {handler_level}")
        if hasattr(handler, 'baseFilename'):
            print(f"    File: {handler.baseFilename}")
        if hasattr(handler, 'address'):
            print(f"    Address: {handler.address}")
        if hasattr(handler, 'facility'):
            facility_num = handler.facility
            facility_names = {
                16: "LOG_LOCAL0", 17: "LOG_LOCAL1", 18: "LOG_LOCAL2", 19: "LOG_LOCAL3",
                20: "LOG_LOCAL4", 21: "LOG_LOCAL5", 22: "LOG_LOCAL6", 23: "LOG_LOCAL7"
            }
            facility_name = facility_names.get(facility_num, f"UNKNOWN({facility_num})")
            print(f"    Facility: {facility_name} ({facility_num})")
        print(f"    Formatter: {handler.formatter._fmt if handler.formatter else 'None'}")
    
    print(f"\nSyslog Socket Check:")
    if os.path.exists('/dev/log'):
        stat_info = os.stat('/dev/log')
        print(f"  /dev/log exists: Yes")
        print(f"  Permissions: {oct(stat_info.st_mode)}")
        print(f"  Can write: {os.access('/dev/log', os.W_OK)}")
    else:
        print(f"  /dev/log exists: No")
    
    print("\n" + "="*70 + "\n")

# --- Configuration ---
SESSION_TIMEOUT_SECONDS = 15 * 60
config_path = os.path.join(script_dir, 'config.json')

# --- Global State ---
app = FastAPI()
# host_manager will be initialized when the app is run, not on import.
host_manager: HostManager = None
sessions = {}
sessions_lock = threading.Lock()
# Will be set from command-line arguments.
DEBUG_MODE = False

# --- Helper Functions ---
def get_first_user_message(messages):
    if not isinstance(messages, list): return None
    for message in messages:
        if isinstance(message, dict) and message.get('role') == 'user':
            return message.get('content')
    return None

def generate_session_id(request, model, first_prompt):
    client_host = request.client.host
    session_key = f"{client_host}:{model}:{first_prompt}"
    return hashlib.sha256(session_key.encode()).hexdigest()

def cleanup_expired_sessions():
    while True:
        time.sleep(SESSION_TIMEOUT_SECONDS)
        with sessions_lock:
            current_time = time.time()
            expired_keys = [sid for sid, (_, last_access) in sessions.items() if current_time - last_access > SESSION_TIMEOUT_SECONDS]
            if expired_keys:
                logger.info(f"Session cleanup: Removing {len(expired_keys)} expired sessions.")
                for sid in expired_keys:
                    del sessions[sid]

# --- Main Application Logic ---
async def forward_request(request: Request, host, path: str, body: bytes, is_streaming: bool):
    """Forwards an HTTP request to a specified host and handles the response."""
    url = f"{host.url}/{path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() != 'host'}

    if DEBUG_MODE:
        log_body = body.decode(errors='ignore')
        logger.debug(f"Forwarding request to {url}: Body: {log_body[:500]}")

    client = httpx.AsyncClient()
    req = client.build_request(method=request.method, url=url, headers=headers, content=body, timeout=None)
    try:
        if is_streaming:
            downstream_response = await client.send(req, stream=True)
            
            if DEBUG_MODE:
                logger.debug(f"Streaming response status: {downstream_response.status_code}")
                logger.debug(f"Response headers: {dict(downstream_response.headers)}")
            
            # For streaming responses, we need to exclude only content-length since it conflicts
            # with chunked encoding. Keep transfer-encoding: chunked so the client knows chunks are coming.
            response_headers = {}
            headers_to_skip = {'content-length', 'content-encoding'}
            for key, value in downstream_response.headers.items():
                if key.lower() not in headers_to_skip:
                    response_headers[key] = value
            
            if DEBUG_MODE:
                logger.debug(f"Filtered headers for streaming: {response_headers}")
            
            # Create a custom generator that keeps the client alive
            async def response_generator():
                try:
                    async for chunk in downstream_response.aiter_raw():
                        yield chunk
                finally:
                    await client.aclose()
            
            return StreamingResponse(
                response_generator(),
                status_code=downstream_response.status_code,
                headers=response_headers
            )
        else:
            downstream_response = await client.send(req, stream=False)
            response_body = await downstream_response.aread()
            await client.aclose()
            return Response(
                content=response_body,
                status_code=downstream_response.status_code,
                headers=downstream_response.headers
            )
    except httpx.RequestError as e:
        await client.aclose()
        logger.error(f"Error proxying request to {url}: {e}")
        host.mark_as_unavailable()
        raise HTTPException(status_code=502, detail=f"Error connecting to Ollama host: {e}")


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy_request(request: Request, path: str):
    body = await request.body()
    host = None
    is_streaming = True
    model_name = None
    session_id = None
    excluded_hosts = []

    if path == "api/chat" and request.method == "POST":
        try:
            body_json = json.loads(body)
            model_name = body_json.get("model")
            messages = body_json.get("messages")
            first_prompt = get_first_user_message(messages)
            is_streaming = body_json.get("stream", True)

            if model_name and first_prompt:
                session_id = generate_session_id(request, model_name, first_prompt)
                current_time = time.time()
                with sessions_lock:
                    if session_id in sessions:
                        h, last_access = sessions[session_id]
                        if not h.is_available():
                            logger.info(f"Session host {h.url} is unavailable. Finding a new host.")
                            del sessions[session_id]
                        elif current_time - last_access > SESSION_TIMEOUT_SECONDS:
                            logger.info("Session expired. Finding a new host.")
                            del sessions[session_id]
                        else:
                            logger.info(f"Session hit. Routing to previous host: {h.url}")
                            host = h
                            sessions[session_id] = (host, current_time)

                    if not host:
                        logger.info(f"Session miss. Finding best host for model '{model_name}'.")
                        host = host_manager.get_best_host(model_name)
                        if host:
                            logger.info(f"Assigned new host {host.url} to session.")
                            sessions[session_id] = (host, current_time)
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON body for /api/chat.")

    if not host:
        host = host_manager.get_first_available_host()
        if not host:
            logger.error("No Ollama hosts available to handle the request.")
            raise HTTPException(status_code=503, detail="No available Ollama hosts")

    # Initial request forwarding
    response = await forward_request(request, host, path, body, is_streaming)

    # --- "Model not found" retry logic ---
    if response.status_code == 404 and model_name:
        response_body = b""
        # StreamingResponse has body_iterator, regular Response has .body
        if hasattr(response, "body_iterator"):
            async for chunk in response.body_iterator:
                response_body += chunk
        else:
            response_body = getattr(response, "body", b"")

        try:
            error_details = json.loads(response_body)
            if "model" in error_details.get("error", "") and "not found" in error_details.get("error", ""):
                logger.warning(f"Model '{model_name}' not found on host {host.url}. Attempting to find another host.")
                excluded_hosts.append(host.url)

                # Force-refresh host statuses to get the latest data
                host_manager.refresh_all_hosts_status()

                # Try to find a new host that has the model
                new_host = host_manager.get_best_host(model_name, excluded_urls=excluded_hosts)

                # A new host was found, but we only retry immediately if it already has the model.
                if new_host and model_name in new_host.get_loaded_models():
                    logger.info(f"Found alternative host {new_host.url} with model '{model_name}'. Retrying request.")
                    if session_id:
                        with sessions_lock:
                            sessions[session_id] = (new_host, time.time())
                    return await forward_request(request, new_host, path, body, is_streaming)

                # If no other host has the model, we proceed to the pull logic.
                logger.warning(f"No other host has model '{model_name}'. Attempting to pull it.")
                # Select the best host to pull the model to (can be any host, even the original one if it's the best option)
                host_to_pull = host_manager.get_best_host(model_name, excluded_urls=[])
                if host_to_pull:
                    pull_success = await host_manager.pull_model_on_host(host_to_pull, model_name)
                    if pull_success:
                        logger.info(f"Successfully pulled '{model_name}' to {host_to_pull.url}. Retrying request.")
                        if session_id:
                            with sessions_lock:
                                sessions[session_id] = (host_to_pull, time.time())
                        return await forward_request(request, host_to_pull, path, body, is_streaming)
                    else:
                        logger.error(f"Failed to pull model '{model_name}' on host {host_to_pull.url}.")
                else:
                    logger.error("No available host to pull the model to.")

                # If all else fails, return the original 404 error.
                logger.error(f"Exhausted all options for model '{model_name}'. Returning 404.")
                return Response(content=response_body, status_code=404, headers=response.headers)
        except (json.JSONDecodeError, AttributeError):
            # Not the JSON error we were looking for, return the original response
            pass

    return response

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ollama Proxy Server")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode for verbose logging.")
    args = parser.parse_args()

    DEBUG_MODE = args.debug
    if DEBUG_MODE:
        # Set all handlers to DEBUG level
        for handler in root_logger.handlers:
            handler.setLevel(logging.DEBUG)
        root_logger.setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
        logging.getLogger("httpx").setLevel(logging.DEBUG)
        logger.info("Debug mode enabled.")

    # Print logging diagnostics at startup
    print_logging_diagnostics()

    if not os.path.exists(config_path):
        logger.error(f"Configuration file not found at {config_path}. Please create it from the example.")
    else:
        host_manager = HostManager(config_path)
        host_manager.start_monitoring()  # Start the host monitor
        cleanup_thread = threading.Thread(target=cleanup_expired_sessions, daemon=True)
        cleanup_thread.start()

        import uvicorn
        server_port = host_manager.get_server_port()
        logger.info(f"Starting server on http://0.0.0.0:{server_port}")
        logger.info("Test log message to verify all handlers are working (check syslog, console, and proxy.log)")
        uvicorn.run(app, host="0.0.0.0", port=server_port)