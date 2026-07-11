# new-product-backlog Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new `new-product-backlog` skill that stores a per-project product backlog in a strict, schema-validated JSON file, mutated only through a pure-stdlib Python CLI, with a local server that powers a polished HTML editor.

**Architecture:** A `core.py` module owns the data model, atomic load/save, validation, and referential integrity, exposing pure functions over an in-memory `{schemaVersion, items}` dict. `backlog.py` is the argparse CLI over `core`. `server.py` is a stdlib `http.server` whose mutating routes call the same `core` functions, so Python is the only writer. `editor.html` is a self-contained page that talks to the server's JSON API. `SKILL.md` carries the ported session-analysis workflow and always writes through the CLI.

**Tech Stack:** Python 3.9+ (pure stdlib: `json`, `re`, `os`, `datetime`, `zoneinfo`, `argparse`, `http.server`, `urllib`, `threading`). Tests: Python `unittest` (no pytest dependency) + Node's built-in runner for client-side JS (matching the repo's existing `.test.mjs` convention). No third-party dependencies anywhere.

**Spec:** `docs/superpowers/specs/2026-07-11-new-product-backlog-design.md`

---

## File Structure

New skill directory `skills/new-product-backlog/`:

- `schema/product-backlog.schema.json` — JSON Schema (draft 2020-12); documentation + editor form source.
- `scripts/core.py` — data model, `load`/`init`/`save` (atomic), `validate` (schema-mirror + referential integrity), mutations (`add_item`/`edit_item`/`discard_item`/`remove_item`/`get_item`/`list_items`), `next_id`, `now_iso`.
- `scripts/server.py` — `http.server` handler + `run_server`; every mutating route goes through `core`.
- `scripts/backlog.py` — argparse CLI over `core`; `serve` subcommand delegates to `server.run_server`.
- `templates/editor.html` — self-contained editor (styled via frontend-design); talks to the local server API. Contains a sentinel-wrapped pure `applyFilters` function for unit testing.
- `SKILL.md` — trigger, session-analysis workflow, CLI reference.

Tests (flat `tests/` dir, matching the existing layout):

- `tests/new_product_backlog_core_test.py`
- `tests/new_product_backlog_server_test.py`
- `tests/editor_filters.test.mjs`

Packaging edits: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `README.md`.

**Conventions used throughout:**

- JSON item keys are camelCase: `id`, `name`, `description`, `status`, `priority`, `dependencies`, `doNotBuildBefore`, `artifacts`, `notes`, `createdAt`, `updatedAt`.
- Python function kwargs are snake_case and map to those keys (e.g. `do_not_build_before` ↔ `doNotBuildBefore`).
- All validation flows through `core.validate(data)`, which returns a list of human-readable problem strings. `core.save(path, data)` calls it and refuses to write if the list is non-empty.
- Run a single Python test file with `python3 tests/<file>.py` (each ends with `unittest.main()`).
- Run a Node test with `node tests/<file>.test.mjs`.

---

## Task 1: JSON Schema file

**Files:**
- Create: `skills/new-product-backlog/schema/product-backlog.schema.json`

- [ ] **Step 1: Write the schema file**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/photoenthu/product-backlog-skill/new-product-backlog.schema.json",
  "title": "Product Backlog",
  "type": "object",
  "additionalProperties": false,
  "required": ["schemaVersion", "items"],
  "properties": {
    "schemaVersion": { "type": "integer", "const": 1 },
    "items": {
      "type": "array",
      "items": { "$ref": "#/$defs/item" }
    }
  },
  "$defs": {
    "item": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "id", "name", "description", "status", "priority",
        "dependencies", "doNotBuildBefore", "artifacts", "notes",
        "createdAt", "updatedAt"
      ],
      "properties": {
        "id": { "type": "string", "pattern": "^BL-\\d{3,}$" },
        "name": { "type": "string", "minLength": 1 },
        "description": { "type": "string" },
        "status": { "type": "string", "enum": ["new", "pending", "shipped", "discarded"] },
        "priority": { "type": "string", "enum": ["critical", "high", "medium", "low"] },
        "dependencies": {
          "type": "array",
          "items": { "type": "string", "pattern": "^BL-\\d{3,}$" }
        },
        "doNotBuildBefore": {
          "type": ["string", "null"],
          "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
        },
        "artifacts": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["label", "url"],
            "properties": {
              "label": { "type": "string", "minLength": 1 },
              "url": { "type": "string", "minLength": 1 }
            }
          }
        },
        "notes": { "type": "string" },
        "createdAt": { "type": "string" },
        "updatedAt": { "type": "string" }
      }
    }
  }
}
```

- [ ] **Step 2: Verify it parses**

Run: `python3 -c "import json; json.load(open('skills/new-product-backlog/schema/product-backlog.schema.json')); print('ok')"`
Expected: prints `ok`

- [ ] **Step 3: Commit**

```bash
git add skills/new-product-backlog/schema/product-backlog.schema.json
git commit -m "feat(new-product-backlog): add JSON schema for backlog items"
```

---

## Task 2: core.py — constants, timestamp, init/load, atomic save, next_id

**Files:**
- Create: `skills/new-product-backlog/scripts/core.py`
- Test: `tests/new_product_backlog_core_test.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/new_product_backlog_core_test.py
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "new-product-backlog" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import core  # noqa: E402


class TempBacklog:
    def __enter__(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "product-backlog.json"
        return self

    def __exit__(self, *a):
        self.dir.cleanup()


class InitLoadSaveTest(unittest.TestCase):
    def test_init_creates_empty_file(self):
        with TempBacklog() as t:
            created = core.init(t.path)
            self.assertTrue(created)
            data = json.loads(t.path.read_text())
            self.assertEqual(data, {"schemaVersion": 1, "items": []})

    def test_init_is_idempotent(self):
        with TempBacklog() as t:
            core.init(t.path)
            self.assertFalse(core.init(t.path))

    def test_now_iso_has_offset(self):
        stamp = core.now_iso()
        # e.g. 2026-07-11T14:03:00-04:00
        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")

    def test_next_id_starts_at_001_and_never_reuses(self):
        data = {"schemaVersion": 1, "items": []}
        self.assertEqual(core.next_id(data), "BL-001")
        data["items"].append({"id": "BL-001"})
        data["items"].append({"id": "BL-005"})
        self.assertEqual(core.next_id(data), "BL-006")

    def test_atomic_save_roundtrip(self):
        with TempBacklog() as t:
            core.init(t.path)
            data = core.load(t.path)
            data["items"].append(_valid_item("BL-001"))
            core.save(t.path, data)
            self.assertEqual(core.load(t.path)["items"][0]["id"], "BL-001")


def _valid_item(item_id):
    return {
        "id": item_id, "name": "x", "description": "", "status": "new",
        "priority": "medium", "dependencies": [], "doNotBuildBefore": None,
        "artifacts": [], "notes": "", "createdAt": "t", "updatedAt": "t",
    }


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/new_product_backlog_core_test.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'core'` (file doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/new_product_backlog_core_test.py`
Expected: PASS (5 tests OK).

- [ ] **Step 5: Commit**

```bash
git add skills/new-product-backlog/scripts/core.py tests/new_product_backlog_core_test.py
git commit -m "feat(new-product-backlog): core init/load/atomic-save/next-id"
```

---

## Task 3: core.py — schema-mirror validation

**Files:**
- Modify: `skills/new-product-backlog/scripts/core.py` (replace the `validate` placeholder)
- Test: `tests/new_product_backlog_core_test.py` (add a test class)

- [ ] **Step 1: Write the failing test**

Add to `tests/new_product_backlog_core_test.py` (above the `if __name__` block):

```python
class ValidateShapeTest(unittest.TestCase):
    def _data(self, *items):
        return {"schemaVersion": 1, "items": list(items)}

    def test_valid_item_has_no_problems(self):
        self.assertEqual(core.validate(self._data(_valid_item("BL-001"))), [])

    def test_bad_schema_version(self):
        problems = core.validate({"schemaVersion": 2, "items": []})
        self.assertTrue(any("schemaVersion" in p for p in problems))

    def test_missing_required_field(self):
        item = _valid_item("BL-001")
        del item["priority"]
        problems = core.validate(self._data(item))
        self.assertTrue(any("priority" in p for p in problems))

    def test_bad_status_enum(self):
        item = _valid_item("BL-001")
        item["status"] = "done"
        problems = core.validate(self._data(item))
        self.assertTrue(any("status" in p for p in problems))

    def test_bad_priority_enum(self):
        item = _valid_item("BL-001")
        item["priority"] = "urgent"
        problems = core.validate(self._data(item))
        self.assertTrue(any("priority" in p for p in problems))

    def test_bad_id_pattern(self):
        item = _valid_item("XX-1")
        problems = core.validate(self._data(item))
        self.assertTrue(any("id" in p for p in problems))

    def test_empty_name(self):
        item = _valid_item("BL-001")
        item["name"] = ""
        problems = core.validate(self._data(item))
        self.assertTrue(any("name" in p for p in problems))

    def test_bad_dnbb_not_a_date(self):
        item = _valid_item("BL-001")
        item["doNotBuildBefore"] = "2026-13-40"
        problems = core.validate(self._data(item))
        self.assertTrue(any("doNotBuildBefore" in p for p in problems))

    def test_valid_dnbb_and_null_ok(self):
        good = _valid_item("BL-001")
        good["doNotBuildBefore"] = "2026-07-01"
        self.assertEqual(core.validate(self._data(good)), [])

    def test_bad_artifact_shape(self):
        item = _valid_item("BL-001")
        item["artifacts"] = [{"label": "x"}]  # missing url
        problems = core.validate(self._data(item))
        self.assertTrue(any("artifact" in p.lower() for p in problems))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/new_product_backlog_core_test.py`
Expected: FAIL — several assertions fail because `validate` returns `[]` for everything.

- [ ] **Step 3: Replace the `validate` placeholder in core.py**

```python
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
    """Placeholder — implemented in Task 4."""
    return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/new_product_backlog_core_test.py`
Expected: PASS (all Task 2 + Task 3 tests OK).

- [ ] **Step 5: Commit**

```bash
git add skills/new-product-backlog/scripts/core.py tests/new_product_backlog_core_test.py
git commit -m "feat(new-product-backlog): schema-mirror validation"
```

---

## Task 4: core.py — referential integrity (unique ids, deps exist, no self-dep, no cycles)

**Files:**
- Modify: `skills/new-product-backlog/scripts/core.py` (replace `_validate_integrity`)
- Test: `tests/new_product_backlog_core_test.py` (add a test class)

- [ ] **Step 1: Write the failing test**

Add to `tests/new_product_backlog_core_test.py`:

```python
class IntegrityTest(unittest.TestCase):
    def _data(self, *items):
        return {"schemaVersion": 1, "items": list(items)}

    def _with(self, item_id, deps):
        item = _valid_item(item_id)
        item["dependencies"] = deps
        return item

    def test_duplicate_ids(self):
        problems = core.validate(self._data(_valid_item("BL-001"), _valid_item("BL-001")))
        self.assertTrue(any("duplicate" in p.lower() for p in problems))

    def test_dependency_must_exist(self):
        problems = core.validate(self._data(self._with("BL-001", ["BL-099"])))
        self.assertTrue(any("BL-099" in p for p in problems))

    def test_no_self_dependency(self):
        problems = core.validate(self._data(self._with("BL-001", ["BL-001"])))
        self.assertTrue(any("itself" in p.lower() for p in problems))

    def test_cycle_detected(self):
        problems = core.validate(self._data(
            self._with("BL-001", ["BL-002"]),
            self._with("BL-002", ["BL-001"]),
        ))
        self.assertTrue(any("cycle" in p.lower() for p in problems))

    def test_valid_dag_ok(self):
        problems = core.validate(self._data(
            self._with("BL-001", []),
            self._with("BL-002", ["BL-001"]),
            self._with("BL-003", ["BL-001", "BL-002"]),
        ))
        self.assertEqual(problems, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/new_product_backlog_core_test.py`
Expected: FAIL — integrity checks not implemented (`_validate_integrity` returns `[]`).

- [ ] **Step 3: Replace `_validate_integrity` in core.py**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/new_product_backlog_core_test.py`
Expected: PASS (Task 2 + 3 + 4 tests OK).

- [ ] **Step 5: Commit**

```bash
git add skills/new-product-backlog/scripts/core.py tests/new_product_backlog_core_test.py
git commit -m "feat(new-product-backlog): referential integrity (deps, self-dep, cycles)"
```

---

## Task 5: core.py — mutations (add/edit/discard/remove/get/list)

**Files:**
- Modify: `skills/new-product-backlog/scripts/core.py` (append mutation functions)
- Test: `tests/new_product_backlog_core_test.py` (add a test class)

- [ ] **Step 1: Write the failing test**

Add to `tests/new_product_backlog_core_test.py`:

```python
class MutationTest(unittest.TestCase):
    def _empty(self):
        return {"schemaVersion": 1, "items": []}

    def test_add_assigns_id_and_defaults_and_timestamps(self):
        data = self._empty()
        item = core.add_item(data, name="First feature")
        self.assertEqual(item["id"], "BL-001")
        self.assertEqual(item["status"], "new")
        self.assertEqual(item["priority"], "medium")
        self.assertEqual(item["dependencies"], [])
        self.assertIsNone(item["doNotBuildBefore"])
        self.assertEqual(item["createdAt"], item["updatedAt"])
        self.assertEqual(core.validate(data), [])

    def test_add_with_all_fields(self):
        data = self._empty()
        core.add_item(data, name="A")
        item = core.add_item(
            data, name="B", description="d", status="pending", priority="high",
            dependencies=["BL-001"], do_not_build_before="2026-08-01",
            notes="soak", artifacts=[{"label": "plan", "url": "docs/p.md"}],
        )
        self.assertEqual(item["id"], "BL-002")
        self.assertEqual(item["dependencies"], ["BL-001"])
        self.assertEqual(item["artifacts"], [{"label": "plan", "url": "docs/p.md"}])
        self.assertEqual(core.validate(data), [])

    def test_add_rejects_invalid_immediately(self):
        data = self._empty()
        with self.assertRaises(core.BacklogError):
            core.add_item(data, name="B", dependencies=["BL-999"])
        self.assertEqual(data["items"], [])  # not appended on failure

    def test_edit_changes_only_passed_fields_and_bumps_updated(self):
        data = self._empty()
        core.add_item(data, name="A")
        before = data["items"][0]["updatedAt"]
        item = core.edit_item(data, "BL-001", status="shipped", _updated_at="LATER")
        self.assertEqual(item["status"], "shipped")
        self.assertEqual(item["name"], "A")
        self.assertEqual(item["updatedAt"], "LATER")
        self.assertNotEqual(item["updatedAt"], before)

    def test_edit_unknown_id_raises(self):
        data = self._empty()
        with self.assertRaises(core.BacklogError):
            core.edit_item(data, "BL-404", status="shipped")

    def test_edit_clear_dnbb(self):
        data = self._empty()
        core.add_item(data, name="A", do_not_build_before="2026-08-01")
        item = core.edit_item(data, "BL-001", do_not_build_before=None)
        self.assertIsNone(item["doNotBuildBefore"])

    def test_discard_sets_status(self):
        data = self._empty()
        core.add_item(data, name="A")
        item = core.discard_item(data, "BL-001", notes="not worth it")
        self.assertEqual(item["status"], "discarded")
        self.assertEqual(item["notes"], "not worth it")

    def test_remove_deletes(self):
        data = self._empty()
        core.add_item(data, name="A")
        core.remove_item(data, "BL-001")
        self.assertEqual(data["items"], [])

    def test_remove_blocked_by_dependents(self):
        data = self._empty()
        core.add_item(data, name="A")
        core.add_item(data, name="B", dependencies=["BL-001"])
        with self.assertRaises(core.BacklogError):
            core.remove_item(data, "BL-001")
        core.remove_item(data, "BL-001", force=True)  # force succeeds
        self.assertEqual(len(data["items"]), 1)

    def test_get_and_list(self):
        data = self._empty()
        core.add_item(data, name="A", status="pending", priority="high")
        core.add_item(data, name="B", status="shipped", priority="low")
        self.assertEqual(core.get_item(data, "BL-001")["name"], "A")
        pend = core.list_items(data, status="pending")
        self.assertEqual([i["id"] for i in pend], ["BL-001"])
        high = core.list_items(data, priority="high")
        self.assertEqual([i["id"] for i in high], ["BL-001"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/new_product_backlog_core_test.py`
Expected: FAIL — `AttributeError: module 'core' has no attribute 'add_item'`.

- [ ] **Step 3: Append mutation functions to core.py**

```python
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
    problems = validate({"schemaVersion": data["schemaVersion"], "items": candidate_items})
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
    if not force:
        dependents = [
            it["id"] for it in data["items"]
            if it["id"] != item_id and item_id in it.get("dependencies", [])
        ]
        if dependents:
            raise BacklogError(
                f"cannot remove {item_id}: depended on by {', '.join(dependents)} "
                f"(use force to override)"
            )
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/new_product_backlog_core_test.py`
Expected: PASS (all core tests OK).

- [ ] **Step 5: Commit**

```bash
git add skills/new-product-backlog/scripts/core.py tests/new_product_backlog_core_test.py
git commit -m "feat(new-product-backlog): add/edit/discard/remove/get/list mutations"
```

---

## Task 6: backlog.py — argparse CLI over core

**Files:**
- Create: `skills/new-product-backlog/scripts/backlog.py`
- Test: `tests/new_product_backlog_core_test.py` (add a subprocess-based CLI test class)

- [ ] **Step 1: Write the failing test**

Add to `tests/new_product_backlog_core_test.py`:

```python
import subprocess

CLI = SCRIPTS / "backlog.py"


def _run(*args):
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True, text=True,
    )


class CliTest(unittest.TestCase):
    def test_init_add_list_edit_discard_roundtrip(self):
        with TempBacklog() as t:
            p = str(t.path)
            self.assertEqual(_run("init", p).returncode, 0)

            r = _run("add", p, "--name", "First", "--priority", "high")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("BL-001", r.stdout)

            r = _run("list", p)
            self.assertIn("First", r.stdout)

            r = _run("edit", p, "BL-001", "--status", "shipped")
            self.assertEqual(r.returncode, 0, r.stderr)

            r = _run("get", p, "BL-001")
            self.assertIn("shipped", r.stdout)

            r = _run("validate", p)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_add_with_deps_and_artifact(self):
        with TempBacklog() as t:
            p = str(t.path)
            _run("init", p)
            _run("add", p, "--name", "Base")
            r = _run("add", p, "--name", "Dep", "--depends", "BL-001",
                     "--artifact", "plan=docs/p.md", "--dnbb", "2026-09-01")
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads(t.path.read_text())
            self.assertEqual(data["items"][1]["dependencies"], ["BL-001"])
            self.assertEqual(data["items"][1]["doNotBuildBefore"], "2026-09-01")

    def test_bad_dep_exits_nonzero_and_no_write(self):
        with TempBacklog() as t:
            p = str(t.path)
            _run("init", p)
            r = _run("add", p, "--name", "X", "--depends", "BL-777")
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(json.loads(t.path.read_text())["items"], [])

    def test_next_id_and_now(self):
        with TempBacklog() as t:
            p = str(t.path)
            _run("init", p)
            self.assertIn("BL-001", _run("next-id", p).stdout)
        self.assertRegex(_run("now").stdout.strip(), r"^\d{4}-\d{2}-\d{2}T")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/new_product_backlog_core_test.py`
Expected: FAIL — CLI file doesn't exist; subprocesses exit non-zero.

- [ ] **Step 3: Write backlog.py**

```python
#!/usr/bin/env python3
"""Command-line interface for the new-product-backlog skill. The ONLY supported
way to mutate the backlog JSON file (the local editor server calls the same
`core` functions). Pure stdlib.

Subcommands:
  init <path>
  add <path> --name N [--description D --status S --priority P
       --depends BL-001,BL-002 --dnbb YYYY-MM-DD --notes T
       --artifact label=url (repeatable)]
  edit <path> <id> [same flags as add, plus --clear-dnbb]
  discard <path> <id> [--notes T]
  rm <path> <id> [--force]
  get <path> <id>
  list <path> [--status S --priority P]
  validate <path>
  next-id <path>
  now
  serve <path> [--port N]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402


def _parse_depends(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [d.strip() for d in value.split(",") if d.strip()]


def _parse_artifacts(pairs: list[str] | None) -> list[dict] | None:
    if not pairs:
        return None
    out = []
    for pair in pairs:
        if "=" not in pair:
            raise core.BacklogError(f"--artifact must be label=url, got: {pair}")
        label, url = pair.split("=", 1)
        out.append({"label": label.strip(), "url": url.strip()})
    return out


def _add_common_flags(sp, require_name):
    sp.add_argument("--name", required=require_name)
    sp.add_argument("--description")
    sp.add_argument("--status", choices=core.STATUSES)
    sp.add_argument("--priority", choices=core.PRIORITIES)
    sp.add_argument("--depends", help="comma-separated BL-NNN ids")
    sp.add_argument("--dnbb", help="doNotBuildBefore date YYYY-MM-DD")
    sp.add_argument("--notes")
    sp.add_argument("--artifact", action="append", help="label=url (repeatable)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="backlog.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init"); sp.add_argument("path")
    sp = sub.add_parser("add"); sp.add_argument("path"); _add_common_flags(sp, True)
    sp = sub.add_parser("edit"); sp.add_argument("path"); sp.add_argument("id")
    _add_common_flags(sp, False); sp.add_argument("--clear-dnbb", action="store_true")
    sp = sub.add_parser("discard"); sp.add_argument("path"); sp.add_argument("id"); sp.add_argument("--notes")
    sp = sub.add_parser("rm"); sp.add_argument("path"); sp.add_argument("id"); sp.add_argument("--force", action="store_true")
    sp = sub.add_parser("get"); sp.add_argument("path"); sp.add_argument("id")
    sp = sub.add_parser("list"); sp.add_argument("path")
    sp.add_argument("--status", choices=core.STATUSES); sp.add_argument("--priority", choices=core.PRIORITIES)
    sp = sub.add_parser("validate"); sp.add_argument("path")
    sp = sub.add_parser("next-id"); sp.add_argument("path")
    sub.add_parser("now")
    sp = sub.add_parser("serve"); sp.add_argument("path"); sp.add_argument("--port", type=int, default=8765)
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    cmd = args.cmd

    try:
        if cmd == "now":
            print(core.now_iso()); return 0

        if cmd == "init":
            created = core.init(Path(args.path))
            print(f"{'created' if created else 'exists'}: {args.path}"); return 0

        if cmd == "serve":
            import server
            server.run_server(Path(args.path), args.port)
            return 0

        path = Path(args.path)

        if cmd == "next-id":
            print(core.next_id(core.load(path))); return 0

        if cmd == "add":
            data = core.load(path)
            item = core.add_item(
                data, name=args.name, description=args.description or "",
                status=args.status or core.DEFAULT_STATUS,
                priority=args.priority or core.DEFAULT_PRIORITY,
                dependencies=_parse_depends(args.depends),
                do_not_build_before=args.dnbb, notes=args.notes or "",
                artifacts=_parse_artifacts(args.artifact),
            )
            core.save(path, data)
            print(item["id"]); return 0

        if cmd == "edit":
            data = core.load(path)
            changes = {}
            if args.name is not None: changes["name"] = args.name
            if args.description is not None: changes["description"] = args.description
            if args.status is not None: changes["status"] = args.status
            if args.priority is not None: changes["priority"] = args.priority
            if args.depends is not None: changes["dependencies"] = _parse_depends(args.depends)
            if args.notes is not None: changes["notes"] = args.notes
            if args.artifact is not None: changes["artifacts"] = _parse_artifacts(args.artifact)
            if args.clear_dnbb: changes["do_not_build_before"] = None
            elif args.dnbb is not None: changes["do_not_build_before"] = args.dnbb
            core.edit_item(data, args.id, **changes)
            core.save(path, data)
            print(f"edited {args.id}"); return 0

        if cmd == "discard":
            data = core.load(path)
            core.discard_item(data, args.id, notes=args.notes)
            core.save(path, data)
            print(f"discarded {args.id}"); return 0

        if cmd == "rm":
            data = core.load(path)
            core.remove_item(data, args.id, force=args.force)
            core.save(path, data)
            print(f"removed {args.id}"); return 0

        if cmd == "get":
            print(json.dumps(core.get_item(core.load(path), args.id), indent=2)); return 0

        if cmd == "list":
            items = core.list_items(core.load(path), status=args.status, priority=args.priority)
            print(json.dumps(items, indent=2)); return 0

        if cmd == "validate":
            problems = core.validate(core.load(path))
            if not problems:
                print(f"ok: {args.path}"); return 0
            for p in problems:
                print(p, file=sys.stderr)
            return 1

    except core.BacklogError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/new_product_backlog_core_test.py`
Expected: PASS (all core + CLI tests OK).

- [ ] **Step 5: Commit**

```bash
git add skills/new-product-backlog/scripts/backlog.py tests/new_product_backlog_core_test.py
git commit -m "feat(new-product-backlog): argparse CLI over core"
```

---

## Task 7: server.py — HTTP API routing through core

**Files:**
- Create: `skills/new-product-backlog/scripts/server.py`
- Test: `tests/new_product_backlog_server_test.py`

The server serializes all writes behind a lock and, after every mutation, returns the full backlog so the editor re-renders from authoritative server state.

- [ ] **Step 1: Write the failing test**

```python
# tests/new_product_backlog_server_test.py
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

    def test_serves_editor_html_at_root(self):
        # Root returns HTML, not JSON, so fetch raw instead of using _req.
        with urllib.request.urlopen(f"{self.base}/") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn(b"<html", resp.read()[:2000].lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/new_product_backlog_server_test.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'server'`.

- [ ] **Step 3: Write server.py**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/new_product_backlog_server_test.py`
Expected: PASS (server tests OK). The root-HTML test needs `templates/editor.html` to exist — if Task 9 hasn't run yet, create a one-line stub `<html></html>` at `skills/new-product-backlog/templates/editor.html` so this test passes; Task 9 replaces it with the real editor.

- [ ] **Step 5: Create the editor stub (so the root route resolves)**

```bash
mkdir -p skills/new-product-backlog/templates
printf '<!DOCTYPE html><html><head><title>stub</title></head><body>stub</body></html>' > skills/new-product-backlog/templates/editor.html
```

Re-run: `python3 tests/new_product_backlog_server_test.py` → PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/new-product-backlog/scripts/server.py skills/new-product-backlog/templates/editor.html tests/new_product_backlog_server_test.py
git commit -m "feat(new-product-backlog): local HTTP server routing through core"
```

---

## Task 8: Client-side filter/sort logic (pure function, TDD via Node)

This is the trickiest client logic (search + multi-select filters + sort), so it lives as a pure, testable function in a sentinel block inside `editor.html` — mirroring the repo's existing `parseFeatureCell` pattern. Task 9 builds the rest of the editor around it.

**Files:**
- Modify: `skills/new-product-backlog/templates/editor.html` (replace the stub with a real file that contains the sentinel-wrapped function)
- Test: `tests/editor_filters.test.mjs`

- [ ] **Step 1: Write the failing test**

```javascript
// tests/editor_filters.test.mjs
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const html = readFileSync(
  new URL("../skills/new-product-backlog/templates/editor.html", import.meta.url),
  "utf8",
);
const m = html.match(/\/\/ <applyFilters>([\s\S]*?)\/\/ <\/applyFilters>/);
assert.ok(m, "applyFilters sentinel block not found in editor.html");
const applyFilters = eval(`(${m[1].trim().replace(/^function applyFilters/, "function")})`);

const items = [
  { id: "BL-001", name: "Login page", description: "auth", notes: "", status: "new", priority: "high" },
  { id: "BL-002", name: "Billing", description: "stripe", notes: "soak", status: "pending", priority: "low" },
  { id: "BL-003", name: "Logout", description: "", notes: "", status: "shipped", priority: "high" },
];

// No filters -> all, default sort by id ascending.
let out = applyFilters(items, { search: "", statuses: [], priorities: [], sortKey: "id", sortDir: "asc" });
assert.deepEqual(out.map((i) => i.id), ["BL-001", "BL-002", "BL-003"]);

// Text search matches name/description/notes/id, case-insensitive.
out = applyFilters(items, { search: "log", statuses: [], priorities: [], sortKey: "id", sortDir: "asc" });
assert.deepEqual(out.map((i) => i.id), ["BL-001", "BL-003"]);

out = applyFilters(items, { search: "soak", statuses: [], priorities: [], sortKey: "id", sortDir: "asc" });
assert.deepEqual(out.map((i) => i.id), ["BL-002"]);

// Status filter (multi-select): empty means "all".
out = applyFilters(items, { search: "", statuses: ["new", "pending"], priorities: [], sortKey: "id", sortDir: "asc" });
assert.deepEqual(out.map((i) => i.id), ["BL-001", "BL-002"]);

// Priority filter composes with status filter.
out = applyFilters(items, { search: "", statuses: ["new", "shipped"], priorities: ["high"], sortKey: "id", sortDir: "asc" });
assert.deepEqual(out.map((i) => i.id), ["BL-001", "BL-003"]);

// Sort by name descending.
out = applyFilters(items, { search: "", statuses: [], priorities: [], sortKey: "name", sortDir: "desc" });
assert.deepEqual(out.map((i) => i.name), ["Logout", "Login page", "Billing"]);

// Sort by priority uses rank (critical<high<medium<low), not alphabetical.
out = applyFilters(items, { search: "", statuses: [], priorities: [], sortKey: "priority", sortDir: "asc" });
assert.deepEqual(out.map((i) => i.priority), ["high", "high", "low"]);

console.log("editor_filters.test.mjs: all assertions passed");
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node tests/editor_filters.test.mjs`
Expected: FAIL — sentinel block not found (stub has no `applyFilters`).

- [ ] **Step 3: Write editor.html with the sentinel-wrapped function**

Replace the stub file with a real editor whose `<script>` contains this exact block (the surrounding UI is fleshed out in Task 9; this step establishes the tested function and a minimal working page):

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Product Backlog Editor</title>
</head>
<body>
<div id="app"></div>
<script>
// <applyFilters>
function applyFilters(items, opts) {
  const search = (opts.search || "").trim().toLowerCase();
  const statuses = opts.statuses || [];
  const priorities = opts.priorities || [];
  const sortKey = opts.sortKey || "id";
  const sortDir = opts.sortDir === "desc" ? "desc" : "asc";
  const PRIORITY_RANK = { critical: 0, high: 1, medium: 2, low: 3 };

  let out = items.filter(function (it) {
    if (statuses.length && statuses.indexOf(it.status) === -1) return false;
    if (priorities.length && priorities.indexOf(it.priority) === -1) return false;
    if (search) {
      const hay = [it.id, it.name, it.description, it.notes]
        .map(function (x) { return (x || "").toLowerCase(); })
        .join(" ");
      if (hay.indexOf(search) === -1) return false;
    }
    return true;
  });

  out.sort(function (a, b) {
    let av, bv;
    if (sortKey === "priority") {
      av = PRIORITY_RANK[a.priority]; bv = PRIORITY_RANK[b.priority];
    } else {
      av = (a[sortKey] == null ? "" : a[sortKey]);
      bv = (b[sortKey] == null ? "" : b[sortKey]);
      av = typeof av === "string" ? av.toLowerCase() : av;
      bv = typeof bv === "string" ? bv.toLowerCase() : bv;
    }
    if (av < bv) return sortDir === "asc" ? -1 : 1;
    if (av > bv) return sortDir === "asc" ? 1 : -1;
    return 0;
  });
  return out;
}
// </applyFilters>
</script>
</body>
</html>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node tests/editor_filters.test.mjs`
Expected: prints `editor_filters.test.mjs: all assertions passed`.

- [ ] **Step 5: Commit**

```bash
git add skills/new-product-backlog/templates/editor.html tests/editor_filters.test.mjs
git commit -m "feat(new-product-backlog): tested client-side filter/sort logic"
```

---

## Task 9: Flesh out the HTML editor UI (frontend-design)

**Files:**
- Modify: `skills/new-product-backlog/templates/editor.html`

**REQUIRED SUB-SKILL:** Invoke `frontend-design:frontend-design` before writing the UI. The goal is a distinctive, highly usable, self-contained editor — not a templated default. Keep the `// <applyFilters> … // </applyFilters>` block from Task 8 byte-for-byte intact (the Node test guards it).

- [ ] **Step 1: Invoke the frontend-design skill**

Announce: "Using frontend-design to style the backlog editor." Follow its guidance for typography, color, and layout. Constraints: self-contained (inline CSS + JS, no CDN/external fonts/images), theme-aware via `prefers-color-scheme`, and a `:root[data-theme]` override hook.

- [ ] **Step 2: Build the UI against this exact API contract**

The page is served by `server.py`. It must:

1. On load, `GET /api/schema` and `GET /api/backlog`; render from server state.
2. Render a **table** of items with columns: id, name, status (pill), priority (pill), doNotBuildBefore, dependencies, updatedAt, and a row actions menu (Edit / Discard / Delete).
3. **Toolbar:** a text `search` input; a multi-select group of **status** chips (new/pending/shipped/discarded); a multi-select group of **priority** chips (critical/high/medium/low); clicking a column header toggles sort on `sortKey`/`sortDir`. Feed all of these into `applyFilters(items, {...})` and re-render the table body only.
4. **Add / Edit modal**, a form built from the fetched schema:
   - `name` (text, required), `description` (textarea), `notes` (textarea)
   - `status` and `priority` as `<select>` populated from the schema enums
   - `dependencies` as a multi-select of existing item ids (excluding the item being edited)
   - `doNotBuildBefore` as `<input type="date">` with a clear button
   - `artifacts` as a small repeatable list of `{label, url}` rows
5. **Save** issues `POST /api/items` (add) or `PATCH /api/items/<id>` (edit) with a camelCase JSON body; on 200, replace local state with the returned backlog and re-render; on 400, show `body.error` inline in the modal (do not close it).
6. **Discard** → `DELETE /api/items/<id>?mode=discard`; **Delete** → `?mode=hard` after a confirm.
7. **Warnings:** render a small badge on a row when (a) `doNotBuildBefore` is in the future, or (b) any dependency's status is not `shipped`. Compute these client-side from the fetched items.

Wire mutations through small helpers, e.g.:

```javascript
async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
  return data; // full backlog on success
}
```

- [ ] **Step 3: Manual verification against a live server**

```bash
python3 skills/new-product-backlog/scripts/backlog.py init /tmp/pb-demo.json
python3 skills/new-product-backlog/scripts/backlog.py serve /tmp/pb-demo.json --port 8765
```

Open `http://127.0.0.1:8765/`. Verify: add an item, edit it, set a `doNotBuildBefore` and a dependency, filter by status and priority, search by text, sort by clicking headers, discard, hard-delete. Confirm each change is reflected in `/tmp/pb-demo.json` on disk (open the file). Confirm an invalid edit (self-dependency) shows the server error inline and does not write.

- [ ] **Step 4: Re-run the guard test**

Run: `node tests/editor_filters.test.mjs`
Expected: still passes (the sentinel block was preserved).

- [ ] **Step 5: Commit**

```bash
git add skills/new-product-backlog/templates/editor.html
git commit -m "feat(new-product-backlog): polished HTML editor UI (frontend-design)"
```

---

## Task 10: SKILL.md — trigger, session-analysis workflow, CLI reference

**Files:**
- Create: `skills/new-product-backlog/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

Frontmatter `name: new-product-backlog` and a `description` that (a) fires on `/new-product-backlog`, "add to the new backlog", "log this to the JSON backlog", and the same session-summary signals as the old skill, and (b) disambiguates from the old skill: JSON-backed, strict schema, live editor, Python-only writes. Body sections:

1. **File location** — `<git-root-or-cwd>/docs/backlog/product-backlog.json`. `init` via the CLI if missing.
2. **The one rule** — the JSON file is mutated **only** through `scripts/backlog.py`. Never edit it with the Read/Edit/Write tools, never hand-write JSON. This is what keeps the file always-valid.
3. **Schema summary** — the field table from the spec (id, name, description, status∈{new,pending,shipped,discarded}, priority∈{critical,high,medium,low}, dependencies[], doNotBuildBefore, artifacts[], notes, createdAt, updatedAt) and status semantics.
4. **CLI reference** — every subcommand with a one-line example (mirror Task 6's docstring).
5. **Session-analysis workflow** (ported from the old skill's "When the skill is invoked"): resolve path & `init`; gather candidates (git commits since each item's `createdAt`, plans in `docs/superpowers/plans/`, PRDs, conversational signals); match by explicit id → artifact url → fuzzy title; decide status (commit→shipped, plan-only→pending, conversation→new/pending; never demote shipped; prefer lower-confidence when unsure); ask one clarifying question at a time; show a brief proposed diff; on confirm, **apply via `backlog.py add`/`edit`/`discard`** (one invocation per change); run `backlog.py validate`; report.
6. **The editor** — `python3 <skill-dir>/scripts/backlog.py serve <path>` opens the local editor for manual add/edit/filter/search; note it writes through the same validating core.
7. **Commit prompt** — offer to stage `docs/backlog/product-backlog.json` by explicit path and commit/push (ask once; no AI-attribution footer for routine backlog updates), mirroring the old skill.
8. **Anti-patterns** — don't hand-edit the JSON; don't bypass the CLI; don't invent dependencies (ids must exist); don't demote shipped; don't `git add -A`.

Write these sections out in full prose (the old `product-backlog/SKILL.md` is the reference for tone and depth). Keep the CLI examples copy-pasteable.

- [ ] **Step 2: Sanity-check the frontmatter parses**

Run: `python3 -c "import re,sys; t=open('skills/new-product-backlog/SKILL.md').read(); assert t.startswith('---'); assert re.search(r'name:\s*new-product-backlog', t); print('ok')"`
Expected: prints `ok`

- [ ] **Step 3: Commit**

```bash
git add skills/new-product-backlog/SKILL.md
git commit -m "feat(new-product-backlog): SKILL.md workflow and CLI reference"
```

---

## Task 11: Packaging — version bump, plugin/marketplace/README updates

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `README.md`

- [ ] **Step 1: Bump versions and mention both skills**

In `.claude-plugin/plugin.json`: bump `version` `0.2.0` → `0.3.0`; update `description` to note the plugin now bundles two skills (markdown backlog + JSON backlog with live editor); add keywords `json`, `editor` if desired.

In `.claude-plugin/marketplace.json`: bump both `metadata.version` and the plugin entry `version` to `0.3.0`; extend the plugin `description` to mention the new JSON-backed skill and editor.

- [ ] **Step 2: Update README**

Add a section documenting `new-product-backlog`: what it is, the JSON schema, the CLI (`init/add/edit/discard/rm/list/validate/serve`), how to launch the editor, and how it differs from the original markdown skill. Keep the existing skill's docs intact.

- [ ] **Step 3: Verify JSON files still parse**

Run: `python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); json.load(open('.claude-plugin/marketplace.json')); print('ok')"`
Expected: prints `ok`

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json README.md
git commit -m "chore: package new-product-backlog skill, bump to 0.3.0"
```

---

## Task 12: Full test sweep

**Files:** none (verification only)

- [ ] **Step 1: Run every test**

```bash
python3 tests/new_product_backlog_core_test.py
python3 tests/new_product_backlog_server_test.py
node tests/editor_filters.test.mjs
node tests/parse_feature_cell.test.mjs   # existing test still green
```

Expected: all four report success; no failures.

- [ ] **Step 2: End-to-end smoke via CLI + validate**

```bash
python3 skills/new-product-backlog/scripts/backlog.py init /tmp/pb-e2e.json
python3 skills/new-product-backlog/scripts/backlog.py add /tmp/pb-e2e.json --name "Base feature" --priority high
python3 skills/new-product-backlog/scripts/backlog.py add /tmp/pb-e2e.json --name "Dependent" --depends BL-001 --dnbb 2026-09-01 --notes "soak window"
python3 skills/new-product-backlog/scripts/backlog.py edit /tmp/pb-e2e.json BL-001 --status shipped
python3 skills/new-product-backlog/scripts/backlog.py list /tmp/pb-e2e.json
python3 skills/new-product-backlog/scripts/backlog.py validate /tmp/pb-e2e.json
```

Expected: `validate` prints `ok`; the list shows BL-001 shipped and BL-002 depending on it.

- [ ] **Step 3: Confirm the invalid-write guard**

```bash
python3 skills/new-product-backlog/scripts/backlog.py add /tmp/pb-e2e.json --name "Cycle" --depends BL-404
echo "exit: $?"
```

Expected: prints an `error:` about BL-404 not existing and `exit: 1`; the file is unchanged.

- [ ] **Step 4: Final commit (if any cleanup needed)**

```bash
git status
# commit any stray fixes discovered during the sweep
```

---

## Self-Review Notes

- **Spec coverage:** JSON storage + schema (Task 1), Python-only writer with atomic writes (Tasks 2–6), referential integrity incl. cycles (Task 4), local server routing through core (Task 7), editor with add/edit/delete/sort/filter/search (Tasks 8–9), session-analysis workflow (Task 10), packaging (Task 11), verification (Task 12). All spec sections map to a task.
- **`notes` field** is present in the schema (Task 1), mutations (Task 5), CLI (Task 6), and editor form (Task 9) — the confirmed keep.
- **No third-party deps:** validation is hand-rolled in `core.validate` mirroring the schema; a note in Task 10 / spec keeps them in sync. Tests use stdlib `unittest` + Node's built-in runner.
- **Type/name consistency:** `add_item`/`edit_item`/`discard_item`/`remove_item`/`get_item`/`list_items`, `validate`, `save`, `load`, `next_id`, `now_iso`, `make_handler`, `run_server`, and the `applyFilters` signature are used identically across tasks. Wire keys are camelCase; core kwargs snake_case via `FIELD_MAP`/`_EDITABLE`.
```
