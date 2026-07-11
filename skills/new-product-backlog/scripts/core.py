# skills/new-product-backlog/scripts/core.py
"""Core data model, persistence, validation, and mutations for the
new-product-backlog skill. Pure stdlib. This module is the ONLY writer of the
backlog JSON file; the CLI and the local server both go through it.

Python 3.9+ (zoneinfo).
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
SCHEMA_VERSION = 1
STATUSES = ("new", "pending", "shipped", "discarded")
PRIORITIES = ("critical", "high", "medium", "low")
DEFAULT_STATUS = "new"
DEFAULT_PRIORITY = "medium"
ID_RE = re.compile(r"^BL-(\d{3,})$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Order matters: item dicts are written with these keys in this order.
ITEM_KEYS = (
    "id", "name", "description", "status", "priority", "dependencies",
    "doNotBuildBefore", "artifacts", "notes", "createdAt", "updatedAt",
)


class BacklogError(Exception):
    """User-facing validation or integrity failure. The message is safe to
    show verbatim to the user or return over the API."""


def now_iso() -> str:
    """Current time in ISO-8601 with the America/New_York offset."""
    return datetime.now(ET).isoformat(timespec="seconds")


def init(path: Path) -> bool:
    """Create an empty backlog file if missing. Returns True if it created it."""
    path = Path(path)
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_raw(path, {"schemaVersion": SCHEMA_VERSION, "items": []})
    return True


def load(path: Path) -> dict:
    """Read and JSON-parse the backlog file. Raises BacklogError on bad JSON."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BacklogError(f"backlog file not found: {path}")
    except json.JSONDecodeError as e:
        raise BacklogError(f"backlog file is not valid JSON: {e}")


def _write_raw(path: Path, data: dict) -> None:
    """Atomic write: temp file in the same dir, then os.replace."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def save(path: Path, data: dict) -> None:
    """Validate, then atomically write. Refuses to write invalid data."""
    problems = validate(data)
    if problems:
        raise BacklogError("cannot save invalid backlog:\n  - " + "\n  - ".join(problems))
    _write_raw(path, data)


def next_id(data: dict) -> str:
    """Return the next free BL-NNN id (max + 1), never reusing ids."""
    highest = 0
    for item in data.get("items", []):
        m = ID_RE.match(item.get("id", ""))
        if m:
            highest = max(highest, int(m.group(1)))
    return f"BL-{highest + 1:03d}"


def validate(data: dict) -> list[str]:
    """Placeholder — full implementation lands in Task 3 and Task 4."""
    return []
