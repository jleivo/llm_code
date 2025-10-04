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
# Manually configure the root logger to avoid conflicts.
script_dir = os.path.dirname(__file__)
log_file_path = os.path.join(script_dir, 'proxy.log')
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
if not root_logger.handlers:
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    # File handler
    file_handler = logging.FileHandler(log_file_path, mode='a')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
logger = logging.getLogger(__name__)

# --- Configuration ---
SESSION_TIMEOUT_SECONDS = 15 * 60
config_path = os.path.join(script_dir, 'config.json')

# --- Global State ---
app = FastAPI()
# host_manager will be initialized when the app is run, not on import.
host_manager: HostManager = None
sessions = {}
sessions_lock = threading.Lock()

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
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy_request(request: Request, path: str):
    body = await request.body()
    host = None

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
        available_hosts = [h for h in host_manager.hosts if h.is_available()]
        if available_hosts:
            host = available_hosts[0]
        else:
            logger.error("No Ollama hosts available to handle the request.")
            raise HTTPException(status_code=503, detail="No available Ollama hosts")

    async with httpx.AsyncClient() as client:
        url = f"{host.url}/{path}"
        headers = {k: v for k, v in request.headers.items() if k.lower() != 'host'}
        try:
            req = client.build_request(method=request.method, url=url, headers=headers, content=body, timeout=None)
            downstream_response = await client.send(req, stream=True)
            return StreamingResponse(downstream_response.aiter_raw(), status_code=downstream_response.status_code, headers=downstream_response.headers)
        except httpx.RequestError as e:
            logger.error(f"Error proxying request to {url}: {e}")
            host.available = False
            raise HTTPException(status_code=502, detail=f"Error connecting to Ollama host: {e}")

if __name__ == "__main__":
    if not os.path.exists(config_path):
        logger.error(f"Configuration file not found at {config_path}. Please create it from the example.")
    else:
        host_manager = HostManager(config_path)
        cleanup_thread = threading.Thread(target=cleanup_expired_sessions, daemon=True)
        cleanup_thread.start()

        import uvicorn
        logger.info(f"Starting server on http://0.0.0.0:8080")
        uvicorn.run(app, host="0.0.0.0", port=8080)