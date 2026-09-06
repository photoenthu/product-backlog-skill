# tests/skill_frontmatter_test.py
"""Guard the SKILL.md YAML frontmatter against plain-scalar syntax hazards.

Claude Code parses each skill's frontmatter as strict YAML and silently drops
the skill when parsing fails. The descriptions here are long, unquoted plain
scalars, so a single ": " (which YAML reads as a nested mapping key) is enough
to make the whole skill disappear from the skill list with no error surfaced to
the user. Pure stdlib: no PyYAML, matching the rest of the suite.
"""
import re
import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / "skills"
KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):(?: (.*))?$")
# Leading indicator characters that change a plain scalar's meaning.
BAD_FIRST = set("-?:,[]{}#&*!|>'\"%@`")


def _frontmatter_lines(path):
    lines = path.read_text().split("\n")
    assert lines[0] == "---", f"{path} does not start with a --- frontmatter fence"
    end = lines.index("---", 1)
    return lines[1:end]


def _scalars(path):
    """Yield (key, line_no, text) for every line belonging to a plain scalar."""
    key = None
    for i, line in enumerate(_frontmatter_lines(path), start=2):
        m = KEY_RE.match(line)
        if m:
            key, value = m.group(1), m.group(2) or ""
        else:
            value = line
        yield key, i, value


class SkillFrontmatterTest(unittest.TestCase):
    def skill_files(self):
        files = sorted(SKILLS.glob("*/SKILL.md"))
        self.assertTrue(files, "no SKILL.md files found")
        return files

    def test_no_colon_space_in_plain_scalars(self):
        for path in self.skill_files():
            for key, line_no, value in _scalars(path):
                self.assertNotIn(
                    ": ", value,
                    f"{path}:{line_no} ({key}): ': ' inside an unquoted YAML "
                    f"scalar terminates it and breaks frontmatter parsing; "
                    f"use an em dash or quote the value",
                )

    def test_no_trailing_colon_in_plain_scalars(self):
        for path in self.skill_files():
            for key, line_no, value in _scalars(path):
                self.assertFalse(
                    value.rstrip().endswith(":"),
                    f"{path}:{line_no} ({key}): a trailing ':' turns the value "
                    f"into a mapping key",
                )

    def test_no_inline_comment_in_plain_scalars(self):
        for path in self.skill_files():
            for key, line_no, value in _scalars(path):
                self.assertNotIn(
                    " #", value,
                    f"{path}:{line_no} ({key}): ' #' starts a YAML comment and "
                    f"truncates the value",
                )

    def test_plain_scalars_do_not_start_with_an_indicator(self):
        for path in self.skill_files():
            for key, line_no, value in _scalars(path):
                v = value.strip()
                if v:
                    self.assertNotIn(
                        v[0], BAD_FIRST,
                        f"{path}:{line_no} ({key}): value starts with the YAML "
                        f"indicator {v[0]!r}; quote it",
                    )

    def test_name_and_description_present(self):
        for path in self.skill_files():
            keys = {k for k, _, _ in _scalars(path) if k}
            self.assertIn("name", keys, f"{path} frontmatter has no name")
            self.assertIn("description", keys, f"{path} frontmatter has no description")

    def test_name_matches_directory(self):
        for path in self.skill_files():
            for key, _, value in _scalars(path):
                if key == "name":
                    self.assertEqual(
                        value.strip(), path.parent.name,
                        f"{path}: frontmatter name must match its directory",
                    )
                    break


if __name__ == "__main__":
    unittest.main()
