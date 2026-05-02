#!/usr/bin/env python3
"""Deterministic helpers for the product-backlog skill.

The skill itself does the heavy lifting (parsing, classifying, deciding what to
write) — this script only handles the few primitives that are easy to get
subtly wrong in prose:

  * `now-et`            — current timestamp in `YYYY-MM-DD HH:MM ET`
  * `next-id <path>`    — next free `BL-NNN` id by scanning the existing file
  * `init <path>`       — create the empty file if it doesn't exist
  * `list-ids <path>`   — print every existing id, one per line (used for
                          "does a row already exist?" checks)

Pure stdlib. Python 3.9+ (zoneinfo).

Invoke as `python3 backlog_helper.py <subcommand> [args]`.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ID_RE = re.compile(r"\bBL-(\d{3,})\b")

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

    print(f"unknown subcommand: {cmd}", file=sys.stderr)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
