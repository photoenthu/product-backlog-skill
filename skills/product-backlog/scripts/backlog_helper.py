#!/usr/bin/env python3
"""Deterministic helpers for the product-backlog skill.

The skill itself does the heavy lifting (parsing, classifying, deciding what to
write) — this script only handles the few primitives that are easy to get
subtly wrong in prose:

  * `now-et`                          — current timestamp in `YYYY-MM-DD HH:MM ET`
  * `next-id <md-path>`               — next free `BL-NNN` id by scanning the file
  * `init <md-path>`                  — create the empty markdown file if missing
  * `list-ids <md-path>`              — print every existing id, one per line
  * `html-template-version`           — print the bundled template version
  * `regenerate-html-if-stale <html-path>`
        — write the bundled HTML template to the path if the file is missing
          or its embedded version is older than the template's. No-ops
          otherwise. Prints `created` / `regenerated` / `unchanged`.

Pure stdlib. Python 3.9+ (zoneinfo).

Invoke as `python3 backlog_helper.py <subcommand> [args]`.
"""

from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ID_RE = re.compile(r"\bBL-(\d{3,})\b")
HTML_VERSION_RE = re.compile(r"<!--\s*product-backlog-dashboard-version:\s*(\d+)\s*-->")
TEMPLATE_HTML_PATH = Path(__file__).resolve().parent.parent / "templates" / "product-backlog.html"

TEMPLATE = """# Product Backlog

_Maintained by the [`product-backlog`](https://github.com/photoenthu/product-backlog-skill) skill. Each row is one shippable unit. Rows flip status over time but are not deleted from the file._

## In-Progress

| ID | Feature | Summary | Created (ET) | Last updated (ET) | Artifacts | Notes |
|---|---|---|---|---|---|---|

## Pending

| ID | Feature | Summary | Created (ET) | Last updated (ET) | Artifacts | Notes |
|---|---|---|---|---|---|---|

## Shipped

| ID | Feature | Summary | Created (ET) | Last updated (ET) | Artifacts | Notes |
|---|---|---|---|---|---|---|
"""


def now_et() -> str:
    return datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")


def list_ids(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    seen: set[str] = set()
    out: list[str] = []
    for match in ID_RE.finditer(text):
        ident = f"BL-{int(match.group(1)):03d}"
        if ident not in seen:
            seen.add(ident)
            out.append(ident)
    return out


def next_id(path: Path) -> str:
    ids = list_ids(path)
    highest = 0
    for ident in ids:
        try:
            n = int(ident.split("-", 1)[1])
            if n > highest:
                highest = n
        except (ValueError, IndexError):
            continue
    return f"BL-{highest + 1:03d}"


def init(path: Path) -> bool:
    """Create the file if missing. Returns True if it created it."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE, encoding="utf-8")
    return True


def _read_version(text: str) -> int | None:
    match = HTML_VERSION_RE.search(text)
    return int(match.group(1)) if match else None


def html_template_version() -> int:
    """Read the dashboard-version comment out of the bundled template."""
    if not TEMPLATE_HTML_PATH.exists():
        raise FileNotFoundError(
            f"bundled HTML template missing at {TEMPLATE_HTML_PATH}"
        )
    version = _read_version(TEMPLATE_HTML_PATH.read_text(encoding="utf-8"))
    if version is None:
        raise ValueError(
            f"template at {TEMPLATE_HTML_PATH} has no "
            f"<!-- product-backlog-dashboard-version: N --> marker"
        )
    return version


def regenerate_html_if_stale(html_path: Path) -> str:
    """Write the bundled HTML to `html_path` when missing or out of date.

    Returns one of:
      * `created`     — the file did not exist; we wrote it.
      * `regenerated` — the file existed but was older than the template.
      * `unchanged`   — the file exists and is at the current version.
    """
    template_version = html_template_version()
    html_path.parent.mkdir(parents=True, exist_ok=True)

    if not html_path.exists():
        shutil.copyfile(TEMPLATE_HTML_PATH, html_path)
        return "created"

    existing_version = _read_version(html_path.read_text(encoding="utf-8"))
    if existing_version is None or existing_version < template_version:
        shutil.copyfile(TEMPLATE_HTML_PATH, html_path)
        return "regenerated"

    return "unchanged"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    cmd = argv[1]

    if cmd == "now-et":
        print(now_et())
        return 0

    if cmd == "next-id":
        if len(argv) != 3:
            print("usage: backlog_helper.py next-id <path>", file=sys.stderr)
            return 2
        print(next_id(Path(argv[2])))
        return 0

    if cmd == "init":
        if len(argv) != 3:
            print("usage: backlog_helper.py init <path>", file=sys.stderr)
            return 2
        target = Path(argv[2])
        created = init(target)
        print(f"{'created' if created else 'exists'}: {target}")
        return 0

    if cmd == "list-ids":
        if len(argv) != 3:
            print("usage: backlog_helper.py list-ids <path>", file=sys.stderr)
            return 2
        for ident in list_ids(Path(argv[2])):
            print(ident)
        return 0

    if cmd == "html-template-version":
        print(html_template_version())
        return 0

    if cmd == "regenerate-html-if-stale":
        if len(argv) != 3:
            print(
                "usage: backlog_helper.py regenerate-html-if-stale <html-path>",
                file=sys.stderr,
            )
            return 2
        result = regenerate_html_if_stale(Path(argv[2]))
        print(f"{result}: {argv[2]}")
        return 0

    print(f"unknown subcommand: {cmd}", file=sys.stderr)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
