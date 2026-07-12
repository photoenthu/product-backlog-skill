import json
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


if __name__ == "__main__":
    unittest.main()
