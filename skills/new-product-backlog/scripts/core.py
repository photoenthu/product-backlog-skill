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


def _is_valid_date(value: str) -> bool:
    if not DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _validate_item(item: object, index: int) -> list[str]:
    prefix = f"item[{index}]"
    if not isinstance(item, dict):
        return [f"{prefix}: must be an object"]
    problems: list[str] = []

    missing = [k for k in ITEM_KEYS if k not in item]
    if missing:
        problems.append(f"{prefix}: missing required field(s): {', '.join(missing)}")
    extra = [k for k in item if k not in ITEM_KEYS]
    if extra:
        problems.append(f"{prefix}: unknown field(s): {', '.join(extra)}")

    def is_str(k):
        return isinstance(item.get(k), str)

    if "id" in item and not (is_str("id") and ID_RE.match(item["id"])):
        problems.append(f"{prefix}.id: must match BL-NNN (>=3 digits)")
    if "name" in item and not (is_str("name") and item["name"].strip() != ""):
        problems.append(f"{prefix}.name: must be a non-empty string")
    for k in ("description", "notes", "createdAt", "updatedAt"):
        if k in item and not is_str(k):
            problems.append(f"{prefix}.{k}: must be a string")
    if "status" in item and item.get("status") not in STATUSES:
        problems.append(f"{prefix}.status: must be one of {', '.join(STATUSES)}")
    if "priority" in item and item.get("priority") not in PRIORITIES:
        problems.append(f"{prefix}.priority: must be one of {', '.join(PRIORITIES)}")

    if "dependencies" in item:
        deps = item["dependencies"]
        if not isinstance(deps, list) or not all(
            isinstance(d, str) and ID_RE.match(d) for d in deps
        ):
            problems.append(f"{prefix}.dependencies: must be a list of BL-NNN ids")

    if "doNotBuildBefore" in item:
        dnbb = item["doNotBuildBefore"]
        if dnbb is not None and not (isinstance(dnbb, str) and _is_valid_date(dnbb)):
            problems.append(f"{prefix}.doNotBuildBefore: must be null or a YYYY-MM-DD date")

    if "artifacts" in item:
        arts = item["artifacts"]
        ok = isinstance(arts, list) and all(
            isinstance(a, dict)
            and set(a.keys()) == {"label", "url"}
            and isinstance(a.get("label"), str) and a["label"] != ""
            and isinstance(a.get("url"), str) and a["url"] != ""
            for a in arts
        )
        if not ok:
            problems.append(f"{prefix}.artifacts: must be a list of {{label, url}} non-empty strings")

    return problems


def validate(data: object) -> list[str]:
    """Return a list of human-readable problems. Empty list == valid.

    Covers structural shape, enums, id/date patterns, AND referential
    integrity (unique ids, deps exist, no self-deps, no cycles — added in
    Task 4)."""
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["top level: must be an object"]
    if data.get("schemaVersion") != SCHEMA_VERSION:
        problems.append(f"schemaVersion: must equal {SCHEMA_VERSION}")
    items = data.get("items")
    if not isinstance(items, list):
        return problems + ["items: must be an array"]
    for i, item in enumerate(items):
        problems.extend(_validate_item(item, i))
    problems.extend(_validate_integrity(items))
    return problems


def _validate_integrity(items: list) -> list[str]:
    problems: list[str] = []
    ids = [it.get("id") for it in items if isinstance(it, dict)]
    valid_ids = [i for i in ids if isinstance(i, str) and ID_RE.match(i)]

    seen: set[str] = set()
    for i in valid_ids:
        if i in seen:
            problems.append(f"duplicate id: {i}")
        seen.add(i)

    id_set = set(valid_ids)
    graph: dict[str, list[str]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        iid = it.get("id")
        deps = it.get("dependencies")
        if not (isinstance(iid, str) and ID_RE.match(iid)) or not isinstance(deps, list):
            continue
        clean: list[str] = []
        for d in deps:
            if not (isinstance(d, str) and ID_RE.match(d)):
                continue  # shape error already reported by _validate_item
            if d == iid:
                problems.append(f"{iid} cannot depend on itself")
            elif d not in id_set:
                problems.append(f"{iid} depends on {d}, which does not exist")
            else:
                clean.append(d)
        graph[iid] = clean

    # Cycle detection via DFS coloring.
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}
    cyclic: set[str] = set()

    def visit(node: str, stack: list[str]) -> None:
        color[node] = GRAY
        stack.append(node)
        for nxt in graph.get(node, []):
            if color.get(nxt) == GRAY:
                # Found a back-edge; mark the members of the cycle.
                if nxt in stack:
                    cyclic.update(stack[stack.index(nxt):])
            elif color.get(nxt) == WHITE:
                visit(nxt, stack)
        stack.pop()
        color[node] = BLACK

    for n in graph:
        if color[n] == WHITE:
            visit(n, [])
    if cyclic:
        problems.append(f"dependency cycle involving: {', '.join(sorted(cyclic))}")

    return problems


def _find_index(data: dict, item_id: str) -> int:
    for i, item in enumerate(data.get("items", [])):
        if item.get("id") == item_id:
            return i
    raise BacklogError(f"no item with id {item_id}")


def _ordered(item: dict) -> dict:
    """Return the item with keys in canonical ITEM_KEYS order."""
    return {k: item[k] for k in ITEM_KEYS}


def add_item(
    data: dict,
    *,
    name: str,
    description: str = "",
    status: str = DEFAULT_STATUS,
    priority: str = DEFAULT_PRIORITY,
    dependencies: list | None = None,
    do_not_build_before: str | None = None,
    notes: str = "",
    artifacts: list | None = None,
    _now: str | None = None,
) -> dict:
    """Build, validate, and append a new item. Raises BacklogError (leaving
    `data` untouched) if the result would be invalid. Returns the new item."""
    stamp = _now or now_iso()
    item = {
        "id": next_id(data),
        "name": name,
        "description": description,
        "status": status,
        "priority": priority,
        "dependencies": list(dependencies or []),
        "doNotBuildBefore": do_not_build_before,
        "artifacts": list(artifacts or []),
        "notes": notes,
        "createdAt": stamp,
        "updatedAt": stamp,
    }
    candidate = {"schemaVersion": data.get("schemaVersion", SCHEMA_VERSION),
                 "items": list(data.get("items", [])) + [item]}
    problems = validate(candidate)
    if problems:
        raise BacklogError("cannot add item:\n  - " + "\n  - ".join(problems))
    data["items"].append(_ordered(item))
    return data["items"][-1]


_EDITABLE = {
    "name": "name", "description": "description", "status": "status",
    "priority": "priority", "dependencies": "dependencies",
    "do_not_build_before": "doNotBuildBefore", "notes": "notes",
    "artifacts": "artifacts",
}
_UNSET = object()


def edit_item(
    data: dict,
    item_id: str,
    *,
    name=_UNSET, description=_UNSET, status=_UNSET, priority=_UNSET,
    dependencies=_UNSET, do_not_build_before=_UNSET, notes=_UNSET, artifacts=_UNSET,
    _updated_at: str | None = None,
) -> dict:
    """Apply only the passed fields to an existing item, bump updatedAt,
    validate the whole file, and commit the change in memory. Raises on unknown
    id or if the edit would make the file invalid (item left unchanged)."""
    idx = _find_index(data, item_id)
    current = dict(data["items"][idx])
    changes = {
        "name": name, "description": description, "status": status,
        "priority": priority, "dependencies": dependencies,
        "do_not_build_before": do_not_build_before, "notes": notes,
        "artifacts": artifacts,
    }
    for kwarg, value in changes.items():
        if value is not _UNSET:
            current[_EDITABLE[kwarg]] = value
    current["updatedAt"] = _updated_at or now_iso()

    candidate_items = list(data["items"])
    candidate_items[idx] = current
    problems = validate({"schemaVersion": data.get("schemaVersion", SCHEMA_VERSION), "items": candidate_items})
    if problems:
        raise BacklogError("cannot edit item:\n  - " + "\n  - ".join(problems))
    data["items"][idx] = _ordered(current)
    return data["items"][idx]


def discard_item(data: dict, item_id: str, notes: str | None = None, _now: str | None = None) -> dict:
    kwargs = {"status": "discarded", "_updated_at": _now}
    if notes is not None:
        kwargs["notes"] = notes
    return edit_item(data, item_id, **kwargs)


def remove_item(data: dict, item_id: str, force: bool = False) -> None:
    """Hard-delete an item. Refuses if other items depend on it unless force."""
    idx = _find_index(data, item_id)
    dependents = [
        it["id"] for it in data["items"]
        if it["id"] != item_id and item_id in it.get("dependencies", [])
    ]
    if dependents and not force:
        raise BacklogError(
            f"cannot remove {item_id}: depended on by {', '.join(dependents)} "
            f"(use force to override)"
        )
    if force:
        # Strip the id from every other item's dependencies so the result
        # stays savable (no dangling references).
        for it in data["items"]:
            deps = it.get("dependencies")
            if isinstance(deps, list) and item_id in deps:
                it["dependencies"] = [d for d in deps if d != item_id]
    del data["items"][idx]


def get_item(data: dict, item_id: str) -> dict:
    return data["items"][_find_index(data, item_id)]


def list_items(data: dict, status: str | None = None, priority: str | None = None) -> list:
    out = data.get("items", [])
    if status is not None:
        out = [i for i in out if i.get("status") == status]
    if priority is not None:
        out = [i for i in out if i.get("priority") == priority]
    return list(out)
