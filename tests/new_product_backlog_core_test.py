# tests/new_product_backlog_core_test.py
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "new-product-backlog" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import core  # noqa: E402

CLI = SCRIPTS / "backlog.py"


def _run(*args):
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True, text=True,
    )


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

    def test_force_remove_strips_dangling_deps(self):
        data = self._empty()
        core.add_item(data, name="A")
        core.add_item(data, name="B", dependencies=["BL-001"])
        core.remove_item(data, "BL-001", force=True)
        self.assertEqual(core.validate(data), [])
        self.assertEqual(core.get_item(data, "BL-002")["dependencies"], [])

    def test_edit_invalid_leaves_item_unchanged(self):
        data = self._empty()
        core.add_item(data, name="A", status="new")
        with self.assertRaises(core.BacklogError):
            core.edit_item(data, "BL-001", status="done")  # bad enum
        self.assertEqual(core.get_item(data, "BL-001")["status"], "new")

    def test_get_and_list(self):
        data = self._empty()
        core.add_item(data, name="A", status="pending", priority="high")
        core.add_item(data, name="B", status="shipped", priority="low")
        self.assertEqual(core.get_item(data, "BL-001")["name"], "A")
        pend = core.list_items(data, status="pending")
        self.assertEqual([i["id"] for i in pend], ["BL-001"])
        high = core.list_items(data, priority="high")
        self.assertEqual([i["id"] for i in high], ["BL-001"])


class FindTest(unittest.TestCase):
    def _data(self):
        data = {"schemaVersion": 1, "items": []}
        core.add_item(data, name="Alpha login", status="new", priority="high",
                      artifacts=[{"label": "spec", "url": "docs/alpha-spec.md"}])
        core.add_item(data, name="Beta signup", status="pending", priority="low",
                      dependencies=["BL-001"])
        core.add_item(data, name="Gamma alpha export", status="shipped", priority="high")
        return data

    def test_filter_by_name_contains_case_insensitive(self):
        data = self._data()
        found = core.find_items(data, name_contains="ALPHA")
        self.assertEqual({i["id"] for i in found}, {"BL-001", "BL-003"})

    def test_filter_by_status(self):
        data = self._data()
        found = core.find_items(data, status="pending")
        self.assertEqual([i["id"] for i in found], ["BL-002"])

    def test_filter_by_priority(self):
        data = self._data()
        found = core.find_items(data, priority="high")
        self.assertEqual({i["id"] for i in found}, {"BL-001", "BL-003"})

    def test_filter_by_artifact_url_case_insensitive(self):
        data = self._data()
        found = core.find_items(data, artifact_url="ALPHA-SPEC")
        self.assertEqual([i["id"] for i in found], ["BL-001"])

    def test_filter_by_depends_on(self):
        data = self._data()
        found = core.find_items(data, depends_on="BL-001")
        self.assertEqual([i["id"] for i in found], ["BL-002"])

    def test_composition_of_two_filters_is_and(self):
        data = self._data()
        found = core.find_items(data, name_contains="alpha", priority="high")
        self.assertEqual({i["id"] for i in found}, {"BL-001", "BL-003"})
        found2 = core.find_items(data, name_contains="alpha", status="shipped")
        self.assertEqual([i["id"] for i in found2], ["BL-003"])

    def test_empty_result_when_nothing_matches(self):
        data = self._data()
        self.assertEqual(core.find_items(data, name_contains="zzz"), [])

    def test_no_filters_returns_all(self):
        data = self._data()
        found = core.find_items(data)
        self.assertEqual(len(found), 3)


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


class AddAutoInitTest(unittest.TestCase):
    def test_add_creates_missing_file(self):
        with TempBacklog() as t:
            p = str(t.path)
            self.assertFalse(t.path.exists())
            r = _run("add", p, "--name", "First")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(t.path.exists())
            data = json.loads(t.path.read_text())
            self.assertEqual(len(data["items"]), 1)
            self.assertEqual(data["items"][0]["id"], "BL-001")

    def test_add_creates_missing_parent_dir(self):
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d) / "docs" / "backlog" / "product-backlog.json")
            r = _run("add", p, "--name", "First")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(Path(p).exists())


class JsonOutputTest(unittest.TestCase):
    def test_add_json_outputs_item(self):
        with TempBacklog() as t:
            p = str(t.path)
            _run("init", p)
            r = _run("add", p, "--name", "First", "--json")
            self.assertEqual(r.returncode, 0, r.stderr)
            item = json.loads(r.stdout)
            self.assertEqual(item["id"], "BL-001")
            self.assertEqual(item["name"], "First")

    def test_edit_json_outputs_item(self):
        with TempBacklog() as t:
            p = str(t.path)
            _run("init", p)
            _run("add", p, "--name", "First")
            r = _run("edit", p, "BL-001", "--status", "shipped", "--json")
            self.assertEqual(r.returncode, 0, r.stderr)
            item = json.loads(r.stdout)
            self.assertEqual(item["status"], "shipped")

    def test_discard_json_outputs_item(self):
        with TempBacklog() as t:
            p = str(t.path)
            _run("init", p)
            _run("add", p, "--name", "First")
            r = _run("discard", p, "BL-001", "--json")
            self.assertEqual(r.returncode, 0, r.stderr)
            item = json.loads(r.stdout)
            self.assertEqual(item["status"], "discarded")

    def test_rm_json_outputs_removed(self):
        with TempBacklog() as t:
            p = str(t.path)
            _run("init", p)
            _run("add", p, "--name", "First")
            r = _run("rm", p, "BL-001", "--json")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout), {"removed": "BL-001"})

    def test_add_without_json_keeps_human_output(self):
        with TempBacklog() as t:
            p = str(t.path)
            _run("init", p)
            r = _run("add", p, "--name", "First")
            self.assertEqual(r.stdout.strip(), "BL-001")


class DefaultPathTest(unittest.TestCase):
    def test_default_path_with_root(self):
        with tempfile.TemporaryDirectory() as d:
            r = _run("default-path", "--root", d)
            self.assertEqual(r.returncode, 0, r.stderr)
            expected = str(Path(d) / "docs" / "backlog" / "product-backlog.json")
            self.assertEqual(r.stdout.strip(), expected)


class VersionTest(unittest.TestCase):
    def test_version_flag(self):
        r = _run("--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1.0", r.stdout)


if __name__ == "__main__":
    unittest.main()
