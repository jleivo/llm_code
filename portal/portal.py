from flask import Flask, request, Response
from flask_sockets import Sockets
from gevent.pywsgi import WSGIServer
from geventwebsocket.handler import WebSocketHandler
import requests
import logging
from websocket import create_connection
from gevent import spawn

# Create a logger object
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
sockets = Sockets(app)

# Function to handle the proxied HTTP request
def forward_http_request(path):
    target_url = f'http://localhost:7860{path}'
    query_string = request.query_string.decode()
    if query_string:
        target_url += f'?{query_string}'

    # Log the request being proxied
    logger.info(f"Proxying HTTP request to {target_url}")
        
    # Routing the request method, URL, headers, and data to the target
    try:
        response = requests.request(
            method=request.method,
            url=target_url,
            headers={key: value for key, value in request.headers.items() if key.lower() != 'host'},
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Request to {target_url} failed: {e}")
        return Response("An error occurred while processing the request.", status=502)

    # Constructing the response to return to the client
    excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
    headers = [(name, value) for name, value in response.raw.headers.items() if name.lower() not in excluded_headers]
    
    return Response(response.content, response.status_code, headers)

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
def catch_all(path):
    return forward_http_request(f'/{path}')

# WebSocket route to forward WebSocket requests
@sockets.route('/ws/<path:path>')
def echo_socket(ws, path):
    target_url = f'ws://localhost:7860/{path}'

    # Log the WebSocket connection attempt
    logger.info(f"Proxying WebSocket to {target_url}")

    backend_ws = create_connection(target_url)
    
    def receive_from_client():
        while not ws.closed:
            message = ws.receive()
            if message:
                backend_ws.send(message)
    
    def receive_from_backend():
        while True:
            message = backend_ws.recv()
            if message:
                ws.send(message)

    client_receiver = spawn(receive_from_client)
    backend_receiver = spawn(receive_from_backend)
    
    client_receiver.join()
    backend_receiver.join()

if __name__ == '__main__':
    http_server = WSGIServer(('0.0.0.0', 5080), app, handler_class=WebSocketHandler)
    http_server.serve_forever()