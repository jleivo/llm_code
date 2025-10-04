import json
import logging
import os
import time
import hashlib
import threading
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
import httpx
from host_manager import HostManager

# --- Basic Setup ---
# Final attempt: Manually configure the root logger to avoid conflicts.
script_dir = os.path.dirname(__file__)
log_file_path = os.path.join(script_dir, 'proxy.log')

# Get the root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Remove any existing handlers to ensure a clean setup
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Create file handler
file_handler = logging.FileHandler(log_file_path, mode='a')
file_handler.setLevel(logging.INFO)

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add the handlers to the root logger
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)

# --- Configuration ---
SESSION_TIMEOUT_SECONDS = 15 * 60  # 15 minutes
script_dir = os.path.dirname(__file__)
config_path = os.path.join(script_dir, 'config.json')

# --- Global State ---
app = FastAPI()
host_manager = HostManager(config_path)
sessions = {}  # Stores {session_id: (host, last_access_time)}
sessions_lock = threading.Lock()

# --- Helper Functions ---
def get_first_user_message(messages):
    """Finds the first message from a user in a conversation history."""
    if not isinstance(messages, list):
        return None
    for message in messages:
        if isinstance(message, dict) and message.get('role') == 'user':
            return message.get('content')
    return None

def generate_session_id(request, model, first_prompt):
    """Generates a unique session ID."""
    client_host = request.client.host
    session_key = f"{client_host}:{model}:{first_prompt}"
    return hashlib.sha256(session_key.encode()).hexdigest()

def cleanup_expired_sessions():
    """Periodically cleans up expired sessions from the global dictionary."""
    while True:
        time.sleep(SESSION_TIMEOUT_SECONDS)
        with sessions_lock:
            current_time = time.time()
            expired_keys = [
                sid for sid, (_, last_access) in sessions.items()
                if current_time - last_access > SESSION_TIMEOUT_SECONDS
            ]
            if expired_keys:
                logger.info(f"Session cleanup: Removing {len(expired_keys)} expired sessions.")
                for sid in expired_keys:
                    del sessions[sid]

# --- Main Application Logic ---
@app.on_event("startup")
async def startup_event():
    """Starts background tasks."""
    cleanup_thread = threading.Thread(target=cleanup_expired_sessions, daemon=True)
    cleanup_thread.start()
    logger.info("Proxy server started with session cleanup thread.")

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy_request(request: Request, path: str):
    """The main proxy function that handles all incoming requests."""
    body = await request.body()
    host = None

    # --- Session-aware routing for /api/chat ---
    if path == "api/chat" and request.method == "POST":
        try:
            body_json = json.loads(body)
            model_name = body_json.get("model")
            messages = body_json.get("messages")
            first_prompt = get_first_user_message(messages)

            if model_name and first_prompt:
                session_id = generate_session_id(request, model_name, first_prompt)
                current_time = time.time()

                with sessions_lock:
                    if session_id in sessions:
                        # Session exists, check if it's expired
                        h, last_access = sessions[session_id]
                        if current_time - last_access > SESSION_TIMEOUT_SECONDS:
                            logger.info("Session expired. Finding a new host.")
                            del sessions[session_id] # Treat as a miss
                        else:
                            logger.info(f"Session hit. Routing to previous host: {h.url}")
                            host = h
                            sessions[session_id] = (host, current_time) # Update timestamp

                    if not host: # Session miss or expired
                        logger.info(f"Session miss. Finding best host for model '{model_name}'.")
                        host = host_manager.get_best_host(model_name)
                        if host:
                            logger.info(f"Assigned new host {host.url} to session.")
                            sessions[session_id] = (host, current_time)
            else:
                logger.warning("Could not determine session for /api/chat. Missing model or user prompt.")

        except json.JSONDecodeError:
            logger.error("Failed to parse JSON body for /api/chat.")
            # Fall through to default routing

    # --- Default routing for all other requests ---
    if not host:
        logger.info(f"No session. Using default routing for request to '{path}'.")
        # Find the first available host as a fallback
        available_hosts = [h for h in host_manager.hosts if h.is_available()]
        if available_hosts:
            host = available_hosts[0] # Simple fallback
            logger.info(f"Default routing to first available host: {host.url}")
        else:
            logger.error("No Ollama hosts available to handle the request.")
            raise HTTPException(status_code=503, detail="No available Ollama hosts")

    # --- Forward the request to the selected host ---
    async with httpx.AsyncClient() as client:
        url = f"{host.url}/{path}"
        headers = {k: v for k, v in request.headers.items() if k.lower() != 'host'}

        try:
            req = client.build_request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
                timeout=None, # Let the downstream server handle timeouts
            )
            downstream_response = await client.send(req, stream=True)

            return StreamingResponse(
                downstream_response.aiter_raw(),
                status_code=downstream_response.status_code,
                headers=downstream_response.headers,
            )
        except httpx.RequestError as e:
            logger.error(f"Error proxying request to {url}: {e}")
            # Mark host as unavailable if we can't connect
            host.available = False
            raise HTTPException(status_code=502, detail=f"Error connecting to Ollama host: {e}")

if __name__ == "__main__":
    if not os.path.exists(config_path):
        logger.error(f"Configuration file not found at {config_path}. Please create it from the example.")
    else:
        import uvicorn
        logger.info(f"Starting server on http://0.0.0.0:8080")
        # Pass log_config=None to prevent uvicorn from overriding the root logger.
        uvicorn.run(app, host="0.0.0.0", port=8080, log_config=None)