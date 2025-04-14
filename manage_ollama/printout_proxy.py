from http.server import BaseHTTPRequestHandler, HTTPServer
import requests

class ProxyRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.proxy_request('GET')

    def do_POST(self):
        self.proxy_request('POST')

    def do_PUT(self):
        self.proxy_request('PUT')

    def do_PATCH(self):
        self.proxy_request('PATCH')

    def do_DELETE(self):
        self.proxy_request('DELETE')

    def do_HEAD(self):
        self.proxy_request('HEAD')

    def do_OPTIONS(self):
        self.proxy_request('OPTIONS')

    def proxy_request(self, method):
        try:
            # Read the request headers
            headers = self.headers

            # Prepare forward headers (exclude Host)
            forward_headers = {k: v for k, v in headers.items() if k != 'Host'}

            # Read the request body if present
            content_length = headers.get('Content-Length')
            body = b''
            if content_length:
                body = self.rfile.read(int(content_length))

            # Prepare the target URL
            target_url = f'http://localhost:11434{self.path}'

            # Forward the request to the target server
            response = requests.request(
                method=method,
                url=target_url,
                headers=forward_headers,
                data=body,
                allow_redirects=False
            )

            # Print the response from the target server
            print("Response headers:", response.headers)
            print("Response body:", response.text)

            # Send the response back to the client
            self.send_response(response.status_code)

            # Send the response headers
            for header, value in response.headers.items():
                if header not in ('Content-Length', 'Transfer-Encoding', 'Connection'):
                    self.send_header(header, value)
            self.end_headers()

            # Send the response body
            self.wfile.write(response.content)

        except Exception as e:
            self.send_error(500, str(e))

def run_server():
    server_address = ('', 8888)
    httpd = HTTPServer(server_address, ProxyRequestHandler)
    print("Proxy server running on port 8888...")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()
