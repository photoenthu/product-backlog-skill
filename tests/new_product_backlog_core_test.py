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


if __name__ == "__main__":
    unittest.main()
