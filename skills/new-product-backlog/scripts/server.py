#!/usr/bin/env python3
"""Local HTTP server for the new-product-backlog editor. Binds to 127.0.0.1
only. Every mutating route calls the same `core` functions the CLI uses, so
Python remains the sole writer. Pure stdlib.

Routes:
  GET    /                      -> editor.html
  GET    /api/backlog           -> full backlog JSON
  GET    /api/schema            -> JSON schema
  GET    /api/meta              -> {"path": "<abs backlog path>", "root": "<project root>"}
  GET    /file?path=<rel>       -> a project file (relative artifact link),
                                   confined to the project root; active content
                                   types (html/svg/xml) served as inert text
  POST   /api/items             -> add item        (body: item fields)
  PATCH  /api/items/<id>        -> edit item        (body: changed fields)
  DELETE /api/items/<id>?mode=discard|hard -> discard (default) or hard-delete

All mutating routes return the full, updated backlog (200) or {"error": msg}
(400) on a BacklogError.

`run_server` auto-selects a free port: it starts at the requested port and
scans upward to the first one that's available, so a busy port never crashes
the editor.
"""
from __future__ import annotations

import errno
import json
import mimetypes
import subprocess
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

# Content types that could execute script in the editor's own origin (and thus
# reach the mutating /api routes) are served as inert text/plain instead.
_ACTIVE_TYPES = {"text/html", "application/xhtml+xml", "image/svg+xml", "application/xml"}


def project_root(backlog_path: Path) -> Path:
    """Resolve the base directory that relative artifact paths are served from.

    Prefers the git toplevel of the backlog's directory; failing that, if the
    backlog sits at the conventional `<root>/docs/backlog/<file>`, returns that
    `<root>`; otherwise the backlog file's own directory."""
    p = Path(backlog_path).resolve()
    d = p.parent
    try:
        out = subprocess.run(
            ["git", "-C", str(d), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        top = out.stdout.strip()
        if top:
            return Path(top).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass
    if d.name == "backlog" and d.parent.name == "docs":
        return d.parent.parent
    return d


def make_handler(path: Path, root: Path | None = None):
    lock = threading.Lock()
    path = Path(path)
    base_root = Path(root).resolve() if root is not None else project_root(path)
    base_dir = path.resolve().parent  # the backlog file's own directory

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
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                raise core.BacklogError("invalid Content-Length header")
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
                try:
                    self._send_file(200, EDITOR_HTML.read_bytes(), "text/html; charset=utf-8")
                except (core.BacklogError, OSError) as e:
                    self._send_file(500, str(e).encode("utf-8"), "text/plain; charset=utf-8")
            elif route == "/api/backlog":
                try:
                    self._send_json(200, core.load(path))
                except (core.BacklogError, OSError) as e:
                    self._send_json(400, {"error": str(e)})
            elif route == "/api/schema":
                try:
                    self._send_file(200, SCHEMA_PATH.read_bytes(), "application/json")
                except (core.BacklogError, OSError) as e:
                    self._send_json(400, {"error": str(e)})
            elif route == "/api/meta":
                try:
                    self._send_json(200, {"path": str(path.absolute()), "root": str(base_root)})
                except (core.BacklogError, OSError) as e:
                    self._send_json(400, {"error": str(e)})
            elif route == "/file":
                rel = parse_qs(urlparse(self.path).query).get("path", [""])[0]
                self._serve_artifact(rel)
            else:
                self._send_json(404, {"error": "not found"})

        def _within_root(self, candidate: Path) -> Path | None:
            """Resolve `candidate` and return it only if it stays inside the
            project root; otherwise None."""
            try:
                resolved = candidate.resolve()
            except OSError:
                return None
            if resolved == base_root or base_root in resolved.parents:
                return resolved
            return None

        def _artifact_candidates(self, rel: str):
            """The interpretations a relative artifact path may have, in order:
            repo-root-relative, backlog-dir-relative, and (if absolute) the
            literal path. Leading slashes are treated as repo-root-relative too,
            so `/docs/x` and `docs/x` both work."""
            stripped = rel.lstrip("/")
            candidates = [base_root / stripped, base_dir / stripped]
            p = Path(rel)
            if p.is_absolute():
                candidates.insert(0, p)
            return candidates

        def _serve_artifact(self, rel: str):
            """Serve a project file for an artifact path. Tries the sensible
            interpretations and serves whichever lands INSIDE the project root;
            anything that only resolves outside the root is refused. Serves
            potentially-active content types as inert text/plain."""
            if not rel:
                return self._send_json(404, {"error": "no path given"})

            candidates = self._artifact_candidates(rel)
            target = None
            for cand in candidates:
                resolved = self._within_root(cand)
                if resolved is not None and resolved.is_file():
                    target = resolved
                    break

            if target is None:
                # Distinguish "outside the repo" from "just not there" so the
                # message is actionable.
                for cand in candidates:
                    try:
                        if cand.resolve().is_file():
                            return self._send_json(403, {
                                "error": f"artifact path resolves outside the project root: {rel}"
                            })
                    except OSError:
                        pass
                return self._send_json(404, {"error": f"artifact not found under project root: {rel}"})

            # Markdown artifacts are rendered to a safe, self-contained HTML page
            # (read-only; the original file is never modified) instead of served
            # as raw text.
            if target.suffix.lower() in (".md", ".markdown"):
                import mdview
                try:
                    md_text = target.read_text(encoding="utf-8", errors="replace")
                except OSError as e:
                    return self._send_json(500, {"error": str(e)})
                # link_base = the markdown file's directory relative to the
                # project root (posix), so relative links inside it resolve
                # through /file. "" if the file sits at the root.
                try:
                    rel_dir = target.parent.relative_to(base_root).as_posix()
                except ValueError:
                    rel_dir = ""
                page = mdview.render_page(
                    md_text, title=target.name,
                    link_base="" if rel_dir == "." else rel_dir,
                )
                body = page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            ctype, _ = mimetypes.guess_type(str(target))
            if ctype is None or ctype.startswith("text/") or ctype in _ACTIVE_TYPES:
                ctype = "text/plain; charset=utf-8"
            try:
                body = target.read_bytes()
            except OSError as e:
                return self._send_json(500, {"error": str(e)})
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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


HOST = "127.0.0.1"


def bind_server(handler, port: int, host: str = HOST, max_attempts: int = 50) -> ThreadingHTTPServer:
    """Bind a ThreadingHTTPServer to the first free port at or above `port`.

    Tries `port`, then `port + 1`, ... up to `max_attempts` candidates, skipping
    any that are already in use, and returns the bound (not-yet-serving) server.
    Binding in a loop avoids a check-then-bind race: the port we return is one we
    actually hold. Raises OSError if the whole range is busy."""
    last_err: OSError | None = None
    for candidate in range(port, port + max_attempts):
        try:
            return ThreadingHTTPServer((host, candidate), handler)
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                last_err = exc
                continue
            raise
    raise OSError(
        errno.EADDRINUSE,
        f"no free port available in range {port}-{port + max_attempts - 1}",
    ) from last_err


def run_server(path: Path, port: int = 8765, host: str = HOST) -> None:
    core.init(Path(path))
    httpd = bind_server(make_handler(path), port, host)
    actual = httpd.server_address[1]
    url = f"http://{host}:{actual}/"
    if actual != port:
        print(f"port {port} was busy; using free port {actual} instead")
    print(f"new-product-backlog editor serving {path}")
    print(f"open {url} (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
        httpd.shutdown()
