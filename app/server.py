"""Tiny stdlib HTTP server — no frameworks. JSON API + one static page.

Routes:
  GET  /                     -> the UI (app/static/index.html)
  GET  /api/state            -> admin snapshot
  GET  /api/passenger/<tid>  -> passenger view for one train
  POST /api/inject           -> body: {"anomalies": [ {...}, ... ]}
  POST /api/reset            -> back to baseline
Bad input -> HTTP 400 with {"error": ...}; never a crash.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from engine.errors import DispatchError

from .state import AppState

STATIC_DIR = Path(__file__).parent / "static"


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep test output clean
            pass

        def _send_json(self, payload, code=200):
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, text):
            body = text.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send_html((STATIC_DIR / "index.html").read_text(encoding="utf-8"))
            elif self.path == "/api/state":
                self._send_json(state.snapshot())
            elif self.path.startswith("/api/passenger/"):
                tid = self.path.rsplit("/", 1)[-1]
                try:
                    self._send_json(state.passenger(tid))
                except DispatchError as exc:
                    self._send_json({"error": str(exc)}, 400)
            else:
                self._send_json({"error": "not found"}, 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            if self.path == "/api/inject":
                try:
                    payload = json.loads(raw)
                    state.inject(payload.get("anomalies", []))
                    self._send_json(state.snapshot())
                except DispatchError as exc:
                    self._send_json({"error": str(exc)}, 400)
                except (json.JSONDecodeError, AttributeError) as exc:
                    self._send_json({"error": f"bad request: {exc}"}, 400)
            elif self.path == "/api/reset":
                state.reset()
                self._send_json(state.snapshot())
            else:
                self._send_json({"error": "not found"}, 404)

    return Handler


def make_server(state=None, port=0):
    """port=0 -> OS-assigned (tests). Returns the server; caller serves."""
    state = state or AppState()
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))


def serve_in_thread(state=None):
    """For tests: start on an ephemeral port, return (server, base_url)."""
    server = make_server(state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"
