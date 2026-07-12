# tests/new_product_backlog_mdview_test.py
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "new-product-backlog" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import mdview  # noqa: E402


class HeadingTest(unittest.TestCase):
    def test_heading_levels(self):
        out = mdview.to_fragment("# One\n\n## Two\n\n### Three")
        self.assertIn("<h1>One</h1>", out)
        self.assertIn("<h2>Two</h2>", out)
        self.assertIn("<h3>Three</h3>", out)


class InlineTest(unittest.TestCase):
    def test_bold(self):
        self.assertIn("<strong>x</strong>", mdview.to_fragment("**x**"))
        self.assertIn("<strong>x</strong>", mdview.to_fragment("__x__"))

    def test_italic(self):
        self.assertIn("<em>x</em>", mdview.to_fragment("*x*"))
        self.assertIn("<em>x</em>", mdview.to_fragment("_x_"))

    def test_code_span(self):
        self.assertIn("<code>x</code>", mdview.to_fragment("`x`"))

    def test_bold_and_italic_together(self):
        out = mdview.to_fragment("**bold** and *italic*")
        self.assertIn("<strong>bold</strong>", out)
        self.assertIn("<em>italic</em>", out)


class FencedCodeTest(unittest.TestCase):
    def test_fenced_code_block(self):
        out = mdview.to_fragment("```\nsome code\n```")
        self.assertIn("<pre><code>", out)
        self.assertIn("some code", out)

    def test_fenced_code_no_inline(self):
        # Inline markdown inside a fence must stay literal.
        out = mdview.to_fragment("```\n**x** _y_ `z`\n```")
        self.assertIn("**x**", out)
        self.assertNotIn("<strong>", out)
        self.assertNotIn("<em>", out)

    def test_fenced_code_with_language(self):
        out = mdview.to_fragment("```python\nprint(1)\n```")
        self.assertIn("<pre><code>", out)
        self.assertIn("print(1)", out)

    def test_fenced_code_escapes_html(self):
        out = mdview.to_fragment("```\n<script>alert(1)</script>\n```")
        self.assertIn("&lt;script&gt;", out)
        self.assertNotIn("<script>", out)


class ListTest(unittest.TestCase):
    def test_unordered_list(self):
        out = mdview.to_fragment("- a\n- b\n- c")
        self.assertIn("<ul>", out)
        self.assertIn("<li>a</li>", out)
        self.assertIn("<li>c</li>", out)

    def test_ordered_list(self):
        out = mdview.to_fragment("1. a\n2. b")
        self.assertIn("<ol>", out)
        self.assertIn("<li>a</li>", out)

    def test_nested_list(self):
        out = mdview.to_fragment("- a\n  - nested\n- b")
        self.assertIn("<ul>", out)
        self.assertIn("nested", out)
        # A nested <ul> should appear inside the outer list.
        self.assertEqual(out.count("<ul>"), 2)


class BlockquoteTest(unittest.TestCase):
    def test_blockquote(self):
        out = mdview.to_fragment("> quoted text")
        self.assertIn("<blockquote>", out)
        self.assertIn("quoted text", out)

    def test_blockquote_inline(self):
        out = mdview.to_fragment("> **bold** quote")
        self.assertIn("<blockquote>", out)
        self.assertIn("<strong>bold</strong>", out)


class HrTest(unittest.TestCase):
    def test_hr_dashes(self):
        self.assertIn("<hr>", mdview.to_fragment("---"))

    def test_hr_stars(self):
        self.assertIn("<hr>", mdview.to_fragment("***"))

    def test_hr_underscores(self):
        self.assertIn("<hr>", mdview.to_fragment("___"))


class TableTest(unittest.TestCase):
    def test_pipe_table(self):
        md = "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |"
        out = mdview.to_fragment(md)
        self.assertIn("<table>", out)
        self.assertIn("<th>A</th>", out)
        self.assertIn("<th>B</th>", out)
        self.assertIn("<td>1</td>", out)
        self.assertIn("<td>4</td>", out)

    def test_table_cell_inline(self):
        md = "| A | B |\n| --- | --- |\n| **x** | y |"
        out = mdview.to_fragment(md)
        self.assertIn("<strong>x</strong>", out)


class LinkTest(unittest.TestCase):
    def test_external_link(self):
        out = mdview.to_fragment("[t](https://e.com)")
        self.assertIn('href="https://e.com"', out)
        self.assertIn('target="_blank"', out)
        self.assertIn(">t</a>", out)

    def test_anchor_link(self):
        out = mdview.to_fragment("[t](#section)")
        self.assertIn('href="#section"', out)

    def test_relative_link_routes_through_file(self):
        out = mdview.to_fragment("[x](sub/other.md)", link_base="docs")
        self.assertIn("/file?path=docs/sub/other.md", out)
        self.assertIn('target="_blank"', out)

    def test_relative_link_no_base(self):
        out = mdview.to_fragment("[x](other.md)")
        self.assertIn("/file?path=other.md", out)

    def test_link_with_balanced_parens_in_url(self):
        out = mdview.to_fragment("[t](https://e.com/a_(b))")
        self.assertIn('href="https://e.com/a_(b)"', out)
        self.assertNotIn(")</p>", out)  # no stray trailing paren leaked

    def test_link_with_title_is_ignored(self):
        out = mdview.to_fragment('[t](https://e.com "the title")')
        self.assertIn('href="https://e.com"', out)
        self.assertNotIn("the title", out)

    def test_image_renders_as_link_not_img(self):
        out = mdview.to_fragment("![alt text](https://e.com/i.png)")
        self.assertNotIn("<img", out)
        self.assertIn("alt text", out)
        self.assertIn('href="https://e.com/i.png"', out)


class SecurityTest(unittest.TestCase):
    def test_raw_html_is_escaped(self):
        out = mdview.to_fragment("hello <script>alert(1)</script> world")
        self.assertIn("&lt;script&gt;", out)
        self.assertNotIn("<script>", out)

    def test_img_onerror_escaped(self):
        out = mdview.to_fragment('<img src=x onerror=alert(1)>')
        self.assertNotIn("<img", out)
        self.assertIn("&lt;img", out)

    def test_javascript_link_not_a_link(self):
        out = mdview.to_fragment("[x](javascript:alert(1))")
        self.assertNotIn("javascript:", out.lower().replace("&#", ""))
        self.assertNotIn("<a ", out)
        # The label survives as plain text, with no stray paren from the URL.
        self.assertIn("<p>x</p>", out)

    def test_data_uri_link_not_a_link(self):
        out = mdview.to_fragment("[x](data:text/html,<script>alert(1)</script>)")
        self.assertNotIn("<a ", out)

    def test_scheme_hidden_with_control_chars_rejected(self):
        out = mdview.to_fragment("[x](java\tscript:alert(1))")
        self.assertNotIn("<a ", out)

    def test_page_escapes_title(self):
        page = mdview.render_page("body", title="<script>t</script>")
        self.assertIn("&lt;script&gt;t&lt;/script&gt;", page)
        self.assertNotIn("<script>t</script>", page)


class RenderPageTest(unittest.TestCase):
    def test_full_document(self):
        page = mdview.render_page("# Hi\n\nbody", title="doc.md")
        self.assertIn("<!doctype html", page.lower())
        self.assertIn("<html", page.lower())
        self.assertIn("<style>", page)
        self.assertIn("<h1>Hi</h1>", page)
        self.assertIn("doc.md", page)

    def test_self_contained_no_external(self):
        page = mdview.render_page("# Hi", title="t")
        # No external resource references.
        self.assertNotIn("http://", page)
        self.assertNotIn("https://", page)
        self.assertNotIn("<script", page.lower())


class RobustnessTest(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(mdview.to_fragment(""), "")
        self.assertIn("<!doctype html", mdview.render_page("", title="t").lower())

    def test_none_safe(self):
        # Should not crash on odd input.
        self.assertIsInstance(mdview.to_fragment(None), str)

    def test_plain_paragraph(self):
        out = mdview.to_fragment("just some text\nwrapped onto two lines")
        self.assertIn("<p>", out)
        self.assertIn("just some text wrapped onto two lines", out)


if __name__ == "__main__":
    unittest.main()
