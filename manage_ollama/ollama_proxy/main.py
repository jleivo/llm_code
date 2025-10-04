import json
import logging
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
import httpx
from host_manager import HostManager

# Construct absolute path to config file
script_dir = os.path.dirname(__file__)
config_path = os.path.join(script_dir, 'config.json')


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
host_manager = HostManager(config_path)
chat_to_host = {}

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy(request: Request, path: str):
    body = await request.body()
    headers = dict(request.headers)

    host = None
    chat_id = None

    if body:
        try:
            body_json = json.loads(body)
            model_name = body_json.get("model")
            chat_id = body_json.get("chat_id") # Assuming a chat_id is sent

            if chat_id and chat_id in chat_to_host:
                host = chat_to_host[chat_id]
                logger.info(f"Routing existing chat {chat_id} to {host.url}")
            elif model_name:
                host = host_manager.get_best_host(model_name)
                if host:
                    logger.info(f"Routing new chat for model {model_name} to {host.url}")
                    if chat_id:
                        chat_to_host[chat_id] = host
                else:
                    raise HTTPException(status_code=503, detail="No available host for the requested model")
        except json.JSONDecodeError:
            pass # Not a JSON request, proxy to any available host

    if not host:
        # Default to the first available host if no specific routing logic applies
        for h in host_manager.hosts:
            if h.is_available():
                host = h
                break
        if not host:
            raise HTTPException(status_code=503, detail="No available Ollama hosts")


    async with httpx.AsyncClient() as client:
        url = f"{host.url}/{path}"
        req = client.build_request(
            method=request.method,
            url=url,
            headers=headers,
            content=body,
            timeout=None,
        )
        try:
            r = await client.send(req, stream=True)
            return StreamingResponse(
                r.aiter_raw(),
                status_code=r.status_code,
                headers=r.headers,
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Error proxying to Ollama host: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)