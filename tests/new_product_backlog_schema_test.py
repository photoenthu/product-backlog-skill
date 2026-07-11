"""Drift guard: the bundled JSON Schema and the pure-Python checks in core.py
must agree on the enum values and the required field set.

The schema file is what the editor fetches (GET /api/schema) to build its form
dropdowns; core.py's constants are what actually gets enforced on every write.
If someone edits one without the other, the editor would offer stale options or
the validator would accept fields the schema forbids. This test fails loudly on
that drift. (Spec: 2026-07-11-new-product-backlog-design.md, Components section.)
"""
import json
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "new-product-backlog"
sys.path.insert(0, str(SKILL / "scripts"))

import core  # noqa: E402

SCHEMA = json.loads((SKILL / "schema" / "product-backlog.schema.json").read_text())
ITEM = SCHEMA["$defs"]["item"]


class SchemaAgreesWithCoreTest(unittest.TestCase):
    def test_status_enum_matches(self):
        self.assertEqual(ITEM["properties"]["status"]["enum"], list(core.STATUSES))

    def test_priority_enum_matches(self):
        self.assertEqual(ITEM["properties"]["priority"]["enum"], list(core.PRIORITIES))

    def test_required_matches_item_keys(self):
        # Order is irrelevant for JSON Schema "required"; compare as sets.
        self.assertEqual(set(ITEM["required"]), set(core.ITEM_KEYS))

    def test_schema_properties_cover_exactly_the_item_keys(self):
        self.assertEqual(set(ITEM["properties"].keys()), set(core.ITEM_KEYS))


if __name__ == "__main__":
    unittest.main()
