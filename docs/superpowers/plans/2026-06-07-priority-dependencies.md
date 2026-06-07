# Priority & Dependencies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a derived priority (`Critical|High|Medium|Low`) and optional dependency facts (blocking BL row, gating event, earliest-start date) to each new Pending/In-Progress backlog row, surfaced in both `product-backlog.md` and the HTML dashboard.

**Architecture:** Priority + dependency bullets live entirely inside the existing Feature table cell (`<br>`-separated), so the 7-column schema, the helper script, and existing rows are untouched. The dashboard gains a pure `parseFeatureCell()` function that splits the cell into `{title, priority, dependencies[]}`, a colored priority pill, a dependency block, and `**bold**` support in `renderInline()`. SKILL.md documents the derivation rubric and format.

**Tech Stack:** Markdown (GFM tables), vanilla browser JS (single-file HTML, IIFE), Python 3.9+ stdlib helper, Node.js (for the parse unit test only).

---

## File Structure

- `skills/product-backlog/SKILL.md` — add priority/dependency format, rubric, derivation guidance, column-rule updates. (Docs only.)
- `skills/product-backlog/templates/product-backlog.html` — pure `parseFeatureCell()`, priority pill CSS + render, dependency block CSS + render, `**bold**` in `renderInline()`, version bump 3→4.
- `tests/parse_feature_cell.test.mjs` — Node test that extracts the sentinel-wrapped `parseFeatureCell` from the HTML and asserts its behavior. (New file; repo has no prior test dir.)

No changes to `scripts/backlog_helper.py` (schema unchanged).

---

## Task 1: Document priority & dependencies in SKILL.md

**Files:**
- Modify: `skills/product-backlog/SKILL.md`

**Recommended agent model:** Sonnet (prose edits, no logic).

- [ ] **Step 1: Add a "Priority & dependencies" subsection under "Column rules"**

After the `### Markdown table escaping` block (currently ends ~line 60), insert a new `### Priority & dependencies (Feature cell)` section with this exact content:

````markdown
### Priority & dependencies (Feature cell)

New **Pending** and **In-Progress** rows carry a derived priority and optional
dependency facts **inside the Feature cell**, after the title, `<br>`-separated:

```
<Title> **(<Priority>)**<br>• Dependency on BL-NNN<br>• Cannot Start Before: YYYY-MM-DD ET<br>• Reason for dependency: <note>
```

- **Priority** is exactly one of `Critical | High | Medium | Low`, bold, in
  parentheses, appended after the title with one leading space. Derived for
  Pending/In-Progress rows only — **not** for rows logged as already Shipped.
- The three dependency bullets are **each optional**; emit only those that apply.
  A row with no dependency is just `<Title> **(<Priority>)**` (no bullets).
- Bullet char is a literal `•` + space. Labels are fixed:
  `Dependency on `, `Cannot Start Before: `, `Reason for dependency: `.
- `Reason for dependency` is one freeform sentence (may cover a BL dependency, a
  gating event, or both). Escape any literal `|` as `\|`.
- Priority is set at creation; not auto-recomputed, but may be revised on
  explicit user request (touch `Last updated (ET)` when revised).

**Priority rubric** (use judgment):

- **Critical** — blocks shipping/users now; a correctness, security, or
  data-loss risk; or other in-progress work is stuck on it.
- **High** — clear near-term value or unblocks multiple items; expected this
  cycle.
- **Medium** — worth doing, no urgency. **Default** when signals are mixed.
- **Low** — nice-to-have, speculative, or explicitly deferred.

**Dependency derivation** — when adding a new Pending/In-Progress row, check:

- **BL dependency** — does it need another backlog row shipped first? →
  `Dependency on BL-NNN` (confirm the id exists via `list-ids`).
- **Gating event** — blocked on a soak window, external launch, approval, or
  upstream release? → state it in `Reason for dependency`.
- **Earliest start date** — a derivable "not before" date? →
  `Cannot Start Before: YYYY-MM-DD ET` (use `now-et` as the reference clock).

If a dependency is plausible but ambiguous, ask it as a clarifying question
(step 5) rather than guessing. If none apply, write no bullets.
````

- [ ] **Step 2: Update the Feature row in the "Column rules" table**

In the column-rules table, replace the existing **Feature** row:

```
| **Feature** | Short title, ideally <60 chars. Reads like a PR title or ticket name. Avoid trailing periods. |
```

with:

```
| **Feature** | Short title, ideally <60 chars. Reads like a PR title or ticket name. Avoid trailing periods. For new Pending/In-Progress rows, append the derived priority as `**(Critical\|High\|Medium\|Low)**` and any dependency bullets — see "Priority & dependencies" below. |
```

- [ ] **Step 3: Add a priority/dependency note to step 6 (confirmation diff)**

In `### 6. Show the proposed diff and confirm`, after the existing code block, add this line before "Only proceed if the user confirms.":

```markdown
Include the derived **priority** and any **dependency** facts for new Pending/In-Progress rows in this summary, so the user can override before anything is written — e.g. `BL-013 (new) "Scanner universe expansion": Pending, High — depends on BL-007`.
```

- [ ] **Step 4: Add anti-patterns**

In `## Anti-patterns to avoid`, append two bullets:

```markdown
- **Don't assign priority to Shipped rows.** Priority informs sequencing of unfinished work; it's moot once a row is Shipped. Only Pending/In-Progress rows get a `**(Priority)**` tag.
- **Don't invent dependencies.** Only record a `Dependency on BL-NNN` when the id actually exists and the blocking relationship is real. If unsure, ask rather than guess.
```

- [ ] **Step 5: Verify and commit**

Run: `grep -c "Priority & dependencies" skills/product-backlog/SKILL.md`
Expected: `2` (the subsection heading + the in-table reference).

```bash
git add skills/product-backlog/SKILL.md
git commit -m "docs(skill): document priority & dependency derivation"
```

---

## Task 2: Add pure `parseFeatureCell()` to the dashboard (test-first)

**Files:**
- Create: `tests/parse_feature_cell.test.mjs`
- Modify: `skills/product-backlog/templates/product-backlog.html` (add function in the `// ---------- Markdown parsing ----------` area, after `parseBacklog`)

**Recommended agent model:** Opus (parsing logic + extraction-based test).

- [ ] **Step 1: Write the failing Node test**

Create `tests/parse_feature_cell.test.mjs` with exactly:

```javascript
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

// Extract the sentinel-wrapped pure function out of the single-file dashboard
// and eval it in this scope. Keeps the test honest against the real source.
const html = readFileSync(
  new URL("../skills/product-backlog/templates/product-backlog.html", import.meta.url),
  "utf8",
);
const m = html.match(/\/\/ <parseFeatureCell>([\s\S]*?)\/\/ <\/parseFeatureCell>/);
assert.ok(m, "parseFeatureCell sentinel block not found in template");
// The block references escapeHtml only inside makeAnchor-free code, so eval the
// function definition standalone.
const parseFeatureCell = eval(`(${m[1].trim().replace(/^function parseFeatureCell/, "function")})`);

// Title + priority + all three bullets.
const full = parseFeatureCell(
  "Regime-Router v2 **(High)**<br>• Dependency on BL-007<br>• Cannot Start Before: 2026-07-01 ET<br>• Reason for dependency: needs auth",
);
assert.equal(full.title, "Regime-Router v2");
assert.equal(full.priority, "High");
assert.deepEqual(full.dependencies, [
  "Dependency on BL-007",
  "Cannot Start Before: 2026-07-01 ET",
  "Reason for dependency: needs auth",
]);

// Priority, no bullets.
const noDeps = parseFeatureCell("Dashboard v3 **(Medium)**");
assert.equal(noDeps.title, "Dashboard v3");
assert.equal(noDeps.priority, "Medium");
assert.deepEqual(noDeps.dependencies, []);

// Legacy row: no priority, no bullets.
const legacy = parseFeatureCell("Old feature title");
assert.equal(legacy.title, "Old feature title");
assert.equal(legacy.priority, null);
assert.deepEqual(legacy.dependencies, []);

// Case-insensitive priority, extra whitespace tolerated.
const lc = parseFeatureCell("Thing **(critical)** ");
assert.equal(lc.priority, "Critical");
assert.equal(lc.title, "Thing");

console.log("parse_feature_cell: all assertions passed");
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `node tests/parse_feature_cell.test.mjs`
Expected: FAIL — `parseFeatureCell sentinel block not found in template` (assertion error).

- [ ] **Step 3: Implement `parseFeatureCell` in the template**

In `product-backlog.html`, immediately after the `parseBacklog` function definition (ends ~line 456, before `// ---------- Inline markdown rendering ----------`), insert:

```javascript
  // <parseFeatureCell>
  // Split a Feature cell into its title, optional priority, and optional
  // dependency bullets. The cell looks like:
  //   "Title **(High)**<br>• Dependency on BL-007<br>• Cannot Start Before: …"
  // Returns { title, priority|null, dependencies:[] }. Pure; unit-tested in
  // tests/parse_feature_cell.test.mjs via the sentinel markers around it.
  function parseFeatureCell(cell) {
    const segments = String(cell || "").split(/<br\s*\/?>/i);
    let title = (segments[0] || "").trim();
    const dependencies = [];
    for (let i = 1; i < segments.length; i++) {
      const seg = segments[i].trim();
      if (!seg) continue;
      dependencies.push(seg.replace(/^•\s*/, "").trim());
    }
    let priority = null;
    const pm = title.match(/\*\*\(\s*(Critical|High|Medium|Low)\s*\)\*\*/i);
    if (pm) {
      priority = pm[1].charAt(0).toUpperCase() + pm[1].slice(1).toLowerCase();
      title = title.replace(pm[0], "").trim();
    }
    return { title, priority, dependencies };
  }
  // </parseFeatureCell>
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `node tests/parse_feature_cell.test.mjs`
Expected: PASS — `parse_feature_cell: all assertions passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/parse_feature_cell.test.mjs skills/product-backlog/templates/product-backlog.html
git commit -m "feat(dashboard): pure parseFeatureCell for priority + deps"
```

---

## Task 3: Render priority pill, dependency block, bold; bump version

**Files:**
- Modify: `skills/product-backlog/templates/product-backlog.html` (CSS `:root`/dark vars, `.priority`/`.dependencies` rules, `renderInline`, `renderRows`, version comment)

**Recommended agent model:** Opus (touches CSS + two render paths + version).

- [ ] **Step 1: Bump the dashboard version comment**

Change line 7:

```html
<!-- product-backlog-dashboard-version: 3 -->
```

to:

```html
<!-- product-backlog-dashboard-version: 4 -->
```

- [ ] **Step 2: Add priority CSS variables (light + dark)**

In the `:root` block (after `--code-bg: #f5f5f4;`, ~line 24) add:

```css
    --priority-critical: #dc2626; --priority-critical-bg: #fee2e2;
    --priority-high: #ea580c; --priority-high-bg: #ffedd5;
    --priority-medium: #2563eb; --priority-medium-bg: #dbeafe;
    --priority-low: #6b7280; --priority-low-bg: #f3f4f6;
```

In the `@media (prefers-color-scheme: dark) :root` block (after `--code-bg: #292524;`, ~line 37) add:

```css
      --priority-critical-bg: #450a0a; --priority-high-bg: #431407;
      --priority-medium-bg: #172554; --priority-low-bg: #1f2937;
```

- [ ] **Step 3: Add `.priority` pill + `.dependencies` block CSS**

After the `.row .notes { … }` rule (~line 228) add:

```css
  .row .priority {
    display: inline-flex;
    align-items: center;
    margin-left: 8px;
    padding: 1px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    vertical-align: middle;
  }
  .row .priority.critical { color: var(--priority-critical); background: var(--priority-critical-bg); }
  .row .priority.high { color: var(--priority-high); background: var(--priority-high-bg); }
  .row .priority.medium { color: var(--priority-medium); background: var(--priority-medium-bg); }
  .row .priority.low { color: var(--priority-low); background: var(--priority-low-bg); }
  .row .dependencies {
    grid-column: 2;
    margin-top: 6px;
    padding-left: 0;
    list-style: none;
    font-size: 12px;
    color: var(--fg-muted);
  }
  .row .dependencies li {
    margin: 2px 0;
    padding-left: 14px;
    position: relative;
  }
  .row .dependencies li::before {
    content: "•";
    position: absolute;
    left: 0;
    color: var(--fg-subtle);
  }
```

In the mobile `@media (max-width: 640px)` block, add `.dependencies` to the grid-column reset line so it becomes:

```css
    .row .summary, .row .meta, .row .artifacts, .row .notes, .row .dependencies { grid-column: 1; }
```

- [ ] **Step 4: Add `**bold**` support to `renderInline()`**

In `renderInline` (~line 500), after the line `let html = escapeHtml(s);` and before the `LK` restore line, add:

```javascript
    html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
```

- [ ] **Step 5: Use `parseFeatureCell` in `renderRows()`**

In `renderRows` (~line 831), replace the `.title`/`.summary` portion of the row template. The current block is:

```javascript
      container.innerHTML = rows.map((r) => `
        <div class="row">
          <div class="id">${escapeHtml(r.id)}</div>
          <div>
            <div class="title">${renderInline(r.feature)}</div>
            <div class="summary">${renderInline(r.summary)}</div>
            <div class="meta">
              <span><strong>Created:</strong> ${escapeHtml(r.created)}</span>
              <span><strong>Updated:</strong> ${escapeHtml(r.updated)}</span>
            </div>
            ${r.artifacts ? `<div class="artifacts">${renderArtifacts(r.artifacts)}</div>` : ""}
            ${r.notes ? `<div class="notes">${renderInline(r.notes)}</div>` : ""}
          </div>
        </div>
      `).join("");
```

Replace it with:

```javascript
      container.innerHTML = rows.map((r) => {
        const fc = parseFeatureCell(r.feature);
        const pill = fc.priority
          ? `<span class="priority ${fc.priority.toLowerCase()}">${escapeHtml(fc.priority)}</span>`
          : "";
        const deps = fc.dependencies.length
          ? `<ul class="dependencies">${fc.dependencies.map((d) => `<li>${renderInline(d)}</li>`).join("")}</ul>`
          : "";
        return `
        <div class="row">
          <div class="id">${escapeHtml(r.id)}</div>
          <div>
            <div class="title">${renderInline(fc.title)}${pill}</div>
            <div class="summary">${renderInline(r.summary)}</div>
            ${deps}
            <div class="meta">
              <span><strong>Created:</strong> ${escapeHtml(r.created)}</span>
              <span><strong>Updated:</strong> ${escapeHtml(r.updated)}</span>
            </div>
            ${r.artifacts ? `<div class="artifacts">${renderArtifacts(r.artifacts)}</div>` : ""}
            ${r.notes ? `<div class="notes">${renderInline(r.notes)}</div>` : ""}
          </div>
        </div>`;
      }).join("");
```

- [ ] **Step 6: Re-run the parse test (guard against regressions)**

Run: `node tests/parse_feature_cell.test.mjs`
Expected: PASS — `parse_feature_cell: all assertions passed`.

- [ ] **Step 7: Structural verification of the template**

Run:
```bash
grep -c "product-backlog-dashboard-version: 4" skills/product-backlog/templates/product-backlog.html
grep -c "priority.critical" skills/product-backlog/templates/product-backlog.html
grep -c 'replace(/\*\*' skills/product-backlog/templates/product-backlog.html
grep -c "class=\"dependencies\"" skills/product-backlog/templates/product-backlog.html
```
Expected: first `1`, the `priority.critical` count `≥2` (CSS var + class rule), the bold-replace `≥1`, the dependencies `1`.

- [ ] **Step 8: Commit**

```bash
git add skills/product-backlog/templates/product-backlog.html
git commit -m "feat(dashboard): priority pill, dependency block, bold; v4"
```

---

## Task 4: End-to-end verification

**Files:**
- Create (temporary): `/tmp/pb-verify/` scratch files. Do not commit.

**Recommended agent model:** Sonnet (mechanical verification).

- [ ] **Step 1: Build a scratch backlog with new + legacy rows**

```bash
mkdir -p /tmp/pb-verify/docs/backlog
cat > /tmp/pb-verify/docs/backlog/product-backlog.md <<'EOF'
# Product Backlog

## In-Progress

| ID | Feature | Summary | Created (ET) | Last updated (ET) | Artifacts | Notes |
|---|---|---|---|---|---|---|
| BL-002 | Auth module **(Critical)**<br>• Cannot Start Before: 2026-06-15 ET<br>• Reason for dependency: blocked on security review | Shared auth. | 2026-06-07 11:00 ET | 2026-06-07 11:00 ET |  |  |

## Pending

| ID | Feature | Summary | Created (ET) | Last updated (ET) | Artifacts | Notes |
|---|---|---|---|---|---|---|
| BL-003 | Regime-Router v2 **(High)**<br>• Dependency on BL-002<br>• Reason for dependency: needs auth module | Second-gen. | 2026-06-07 11:00 ET | 2026-06-07 11:00 ET |  |  |
| BL-004 | Cleanup task **(Low)** | No deps. | 2026-06-07 11:00 ET | 2026-06-07 11:00 ET |  |  |

## Shipped

| ID | Feature | Summary | Created (ET) | Last updated (ET) | Artifacts | Notes |
|---|---|---|---|---|---|---|
| BL-001 | Legacy item | Old style row. | 2026-06-01 09:00 ET | 2026-06-01 09:00 ET | `abc1234` |  |
EOF
echo "scratch written"
```

- [ ] **Step 2: Verify `parseBacklog` still parses all rows (pure-function smoke)**

Run this Node snippet (extracts `splitTableRow`, `isSeparatorRow`, `parseBacklog` via sentinel-free regex slices and runs them):

```bash
node --input-type=module <<'EOF'
import { readFileSync } from "node:fs";
const html = readFileSync("skills/product-backlog/templates/product-backlog.html","utf8");
function slice(name){const re=new RegExp(`function ${name}\\\\([\\\\s\\\\S]*?\\\\n  \\\\}`);const m=html.match(re);if(!m)throw new Error("missing "+name);return m[0];}
const src = slice("splitTableRow")+"\n"+slice("isSeparatorRow")+"\n"+slice("parseBacklog");
const parseBacklog = eval(`(function(){${src}; return parseBacklog;})()`);
const md = readFileSync("/tmp/pb-verify/docs/backlog/product-backlog.md","utf8");
const s = parseBacklog(md);
import assert from "node:assert/strict";
assert.equal(s["in-progress"].length,1);
assert.equal(s["pending"].length,2);
assert.equal(s["shipped"].length,1);
assert.ok(s["pending"][0].feature.includes("**(High)**"));
console.log("parseBacklog smoke: OK");
EOF
```
Expected: `parseBacklog smoke: OK`. (If the brace-matching slice regex proves brittle, fall back to asserting the markdown has 7 pipes per data row via `grep`, and rely on Task 2's test for the parsing guarantee.)

- [ ] **Step 3: Verify `regenerate-html-if-stale` propagates v4**

```bash
# Stale (v3) on-disk file should regenerate.
python3 - <<'EOF'
from pathlib import Path
p = Path("/tmp/pb-verify/docs/backlog/product-backlog.html")
p.write_text("<!-- product-backlog-dashboard-version: 3 -->\n", encoding="utf-8")
EOF
python3 skills/product-backlog/scripts/backlog_helper.py regenerate-html-if-stale /tmp/pb-verify/docs/backlog/product-backlog.html
# Run again: should now be unchanged.
python3 skills/product-backlog/scripts/backlog_helper.py regenerate-html-if-stale /tmp/pb-verify/docs/backlog/product-backlog.html
```
Expected: first call prints `regenerated: …`, second prints `unchanged: …`.

- [ ] **Step 4: Confirm the regenerated file is v4 and has the new code**

```bash
grep -c "product-backlog-dashboard-version: 4" /tmp/pb-verify/docs/backlog/product-backlog.html
grep -c "parseFeatureCell" /tmp/pb-verify/docs/backlog/product-backlog.html
```
Expected: both `≥1`.

- [ ] **Step 5: Clean up scratch (no commit)**

```bash
rm -rf /tmp/pb-verify
echo "cleaned"
```

No commit for this task — it is verification only.

---

## Self-Review

**Spec coverage:**
- Markdown format (priority in title, `<br>•` bullets, optional) → Task 1 (docs), Task 2 (parse), Task 3 (render). ✓
- Priority rubric + scope (Pending/In-Progress only) → Task 1 Steps 1, 4. ✓
- Dependency derivation (BL dep / gating event / date) → Task 1 Step 1. ✓
- Colored pill (Critical=red, High=orange, Medium=blue, Low=gray) → Task 3 Steps 2-3, 5. ✓
- Dependency block in cards → Task 3 Steps 3, 5. ✓
- `**bold**` in `renderInline` → Task 3 Step 4. ✓
- Version bump 3→4 + propagation → Task 3 Step 1, Task 4 Step 3. ✓
- Backward compat (legacy rows) → Task 2 test (legacy case), Task 4 rows. ✓

**Placeholder scan:** No TBD/TODO; all code blocks complete. ✓

**Type consistency:** `parseFeatureCell` returns `{title, priority, dependencies}` — same shape used in the test (Task 2) and in `renderRows` (Task 3 Step 5). Pill class derived as `fc.priority.toLowerCase()` matches CSS classes `.critical/.high/.medium/.low` (Task 3 Step 3). ✓
