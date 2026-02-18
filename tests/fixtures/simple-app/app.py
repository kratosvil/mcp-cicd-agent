"""
Minimal HTTP server for MCP CI/CD integration testing.
Listens on port 8000, exposes /health endpoint.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b"OK"
        else:
            body = b"Hello from MCP CI/CD Test App!"

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}", flush=True)


if __name__ == "__main__":
    port = 8000
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Server started on 127.0.0.1:{port}", flush=True)
    server.serve_forever()
