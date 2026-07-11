#!/usr/bin/env python3
"""Local HTTP server for the new-product-backlog editor. Binds to 127.0.0.1
only. Every mutating route calls the same `core` functions the CLI uses, so
Python remains the sole writer. Pure stdlib.

Routes:
  GET    /                      -> editor.html
  GET    /api/backlog           -> full backlog JSON
  GET    /api/schema            -> JSON schema
  POST   /api/items             -> add item        (body: item fields)
  PATCH  /api/items/<id>        -> edit item        (body: changed fields)
  DELETE /api/items/<id>?mode=discard|hard -> discard (default) or hard-delete

All mutating routes return the full, updated backlog (200) or {"error": msg}
(400) on a BacklogError.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import core

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
EDITOR_HTML = TEMPLATE_DIR / "editor.html"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "product-backlog.schema.json"

# camelCase (wire) -> snake_case (core kwarg) for POST/PATCH bodies.
FIELD_MAP = {
    "name": "name", "description": "description", "status": "status",
    "priority": "priority", "dependencies": "dependencies",
    "doNotBuildBefore": "do_not_build_before", "notes": "notes",
    "artifacts": "artifacts",
}


def make_handler(path: Path):
    lock = threading.Lock()
    path = Path(path)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass  # keep the console quiet

        def _send_json(self, status, obj):
            payload = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _send_file(self, status, body: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length == 0:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                raise core.BacklogError("request body is not valid JSON")

        def _kwargs_from_body(self, body: dict) -> dict:
            return {FIELD_MAP[k]: v for k, v in body.items() if k in FIELD_MAP}

        # ---- GET ----
        def do_GET(self):
            route = urlparse(self.path).path
            if route == "/":
                self._send_file(200, EDITOR_HTML.read_bytes(), "text/html; charset=utf-8")
            elif route == "/api/backlog":
                self._send_json(200, core.load(path))
            elif route == "/api/schema":
                self._send_file(200, SCHEMA_PATH.read_bytes(), "application/json")
            else:
                self._send_json(404, {"error": "not found"})

        # ---- POST ----
        def do_POST(self):
            if urlparse(self.path).path != "/api/items":
                return self._send_json(404, {"error": "not found"})
            try:
                with lock:
                    body = self._read_body()
                    data = core.load(path)
                    core.add_item(data, **self._add_kwargs(body))
                    core.save(path, data)
                    self._send_json(200, data)
            except core.BacklogError as e:
                self._send_json(400, {"error": str(e)})

        def _add_kwargs(self, body: dict) -> dict:
            kwargs = self._kwargs_from_body(body)
            if "name" not in kwargs:
                raise core.BacklogError("name is required")
            return kwargs

        # ---- PATCH ----
        def do_PATCH(self):
            route = urlparse(self.path).path
            if not route.startswith("/api/items/"):
                return self._send_json(404, {"error": "not found"})
            item_id = route[len("/api/items/"):]
            try:
                with lock:
                    body = self._read_body()
                    data = core.load(path)
                    core.edit_item(data, item_id, **self._kwargs_from_body(body))
                    core.save(path, data)
                    self._send_json(200, data)
            except core.BacklogError as e:
                self._send_json(400, {"error": str(e)})

        # ---- DELETE ----
        def do_DELETE(self):
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/items/"):
                return self._send_json(404, {"error": "not found"})
            item_id = parsed.path[len("/api/items/"):]
            mode = (parse_qs(parsed.query).get("mode", ["discard"]))[0]
            try:
                with lock:
                    data = core.load(path)
                    if mode == "hard":
                        core.remove_item(data, item_id, force=True)
                    else:
                        core.discard_item(data, item_id)
                    core.save(path, data)
                    self._send_json(200, data)
            except core.BacklogError as e:
                self._send_json(400, {"error": str(e)})

    return Handler


def run_server(path: Path, port: int = 8765) -> None:
    core.init(Path(path))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(path))
    url = f"http://127.0.0.1:{port}/"
    print(f"new-product-backlog editor serving {path}")
    print(f"open {url} (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
        httpd.shutdown()
