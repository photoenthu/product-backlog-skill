import json
import socket
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "new-product-backlog" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import core  # noqa: E402
import server  # noqa: E402

import tempfile


def _req(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "product-backlog.json"
        core.init(self.path)
        handler = server.make_handler(self.path)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.dir.cleanup()

    def test_get_backlog_and_schema(self):
        status, body = _req("GET", f"{self.base}/api/backlog")
        self.assertEqual(status, 200)
        self.assertEqual(body["items"], [])
        status, schema = _req("GET", f"{self.base}/api/schema")
        self.assertEqual(status, 200)
        self.assertIn("$defs", schema)

    def test_post_patch_delete_flow(self):
        status, body = _req("POST", f"{self.base}/api/items", {"name": "A", "priority": "high"})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["items"][0]["id"], "BL-001")

        status, body = _req("PATCH", f"{self.base}/api/items/BL-001", {"status": "shipped"})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["items"][0]["status"], "shipped")

        status, body = _req("DELETE", f"{self.base}/api/items/BL-001?mode=discard")
        self.assertEqual(status, 200, body)
        self.assertEqual(body["items"][0]["status"], "discarded")

        status, body = _req("DELETE", f"{self.base}/api/items/BL-001?mode=hard")
        self.assertEqual(status, 200, body)
        self.assertEqual(body["items"], [])

    def test_invalid_post_returns_400_and_no_write(self):
        status, body = _req("POST", f"{self.base}/api/items", {"name": "A", "dependencies": ["BL-999"]})
        self.assertEqual(status, 400)
        self.assertIn("error", body)
        # File unchanged:
        self.assertEqual(json.loads(self.path.read_text())["items"], [])

    def test_get_meta_returns_backlog_path(self):
        status, body = _req("GET", f"{self.base}/api/meta")
        self.assertEqual(status, 200, body)
        self.assertIn("path", body)
        self.assertTrue(body["path"])
        self.assertTrue(body["path"].endswith("product-backlog.json"), body["path"])

    def test_serves_editor_html_at_root(self):
        # Root returns HTML, not JSON, so fetch raw instead of using _req.
        with urllib.request.urlopen(f"{self.base}/") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn(b"<html", resp.read()[:2000].lower())


class BindServerTest(unittest.TestCase):
    """The editor must not crash when its preferred port is busy; bind_server
    scans upward to the first free port."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "product-backlog.json"
        core.init(self.path)
        self.handler = server.make_handler(self.path)

    def tearDown(self):
        self.dir.cleanup()

    @staticmethod
    def _free_port():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def test_binds_requested_port_when_free(self):
        port = self._free_port()
        httpd = server.bind_server(self.handler, port)
        try:
            self.assertEqual(httpd.server_address[1], port)
        finally:
            httpd.server_close()

    def test_falls_forward_when_port_busy(self):
        # Hold a port open (actively listening), then bind_server must pick a
        # different, higher port rather than raising.
        occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        busy = occupied.getsockname()[1]
        try:
            httpd = server.bind_server(self.handler, busy, max_attempts=25)
            try:
                actual = httpd.server_address[1]
                self.assertNotEqual(actual, busy)
                self.assertTrue(busy < actual < busy + 25)
            finally:
                httpd.server_close()
        finally:
            occupied.close()

    def test_raises_when_whole_range_busy(self):
        # A one-wide range on a busy port has nowhere to fall forward to.
        occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        busy = occupied.getsockname()[1]
        try:
            with self.assertRaises(OSError):
                server.bind_server(self.handler, busy, max_attempts=1)
        finally:
            occupied.close()


if __name__ == "__main__":
    unittest.main()
