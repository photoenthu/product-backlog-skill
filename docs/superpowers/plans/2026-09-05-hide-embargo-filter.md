# Hide Embargo Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `Hide Embargo` toggle beside `Hide Blocked` in the backlog editor toolbar that hides items whose `doNotBuildBefore` date is strictly in the future.

**Architecture:** Pure client-side view filtering. A new `hideEmbargo` predicate goes inside the existing `applyFilters()` pass in `editor.html`, taking its reference date from `opts.today` so the function stays pure and testable. The `hideEmbargo` state flag mirrors `hideBlocked` at every touchpoint: markup, `state`, `renderBody`, `clearFilters`, `persistView`, `restoreView`, and the `boot()` listener. No server, CLI, or schema change.

**Tech Stack:** Vanilla ES5-style JS inside a single self-contained `editor.html` (no build step, no CDN, no framework). Tests are Node ESM scripts run directly with `node`, plus Python `unittest` for the server/CLI side (untouched here).

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-09-05-hide-embargo-filter-design.md` — read it before starting.
- **Embargo predicate, verbatim:** `item.doNotBuildBefore && item.doNotBuildBefore > today`. Strictly greater-than. A date equal to today is **not** embargoed.
- **`applyFilters()` must stay self-contained.** It lives between the `// <applyFilters>` and `// </applyFilters>` sentinel comments, and `tests/editor_filters.test.mjs` extracts that block by regex and `eval`s it in isolation. It may not reference any identifier defined outside those sentinels — in particular it may **not** call `todayStr()`.
- **No `innerHTML` with item text.** All DOM is built with `createElement`/`textContent` (or the file's `h()` helper). The new markup is static HTML in the template, so this is only a constraint on any JS you add.
- **Style:** match the surrounding file — `function () {}` expressions (not arrows), `const`/`let`, double-quoted strings, 2-space indent.
- **Full test command (must be green before every commit):**
  ```bash
  node tests/editor_filters.test.mjs && node tests/editor_prompts.test.mjs && \
  node tests/parse_feature_cell.test.mjs && \
  python3 -m unittest discover -s tests -p "*_test.py"
  ```
- **Baseline is green.** At plan time: `editor_filters.test.mjs` passes and the Python suite reports `Ran 119 tests ... OK`. If the baseline is red before you start, stop and report it — do not "fix" it as part of this work.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `skills/new-product-backlog/templates/editor.html` | The entire editor (inline CSS + JS). Single file by design — do not split. | Modify: filter predicate + 8 state touchpoints + toolbar markup |
| `tests/editor_filters.test.mjs` | Pure-function tests for `applyFilters`, extracted from the template by regex | Modify: append a `hideEmbargo` section |
| `skills/new-product-backlog/SKILL.md` | Skill instructions; the editor paragraph lists editor features | Modify: one sentence |
| `README.md` | Repo-level docs; "The editor" section mirrors SKILL.md's feature list | Modify: one sentence |
| `.claude-plugin/plugin.json` | Plugin version | Modify: `0.8.0` → `0.9.0` |

Task 1 is the pure filter logic (fully testable with no DOM). Task 2 is the DOM/state wiring (not covered by the headless test suite — verified by reading and by a manual smoke run). Task 3 is docs + version. A reviewer could reject any one while approving the others.

---

### Task 1: The embargo predicate in `applyFilters()`

**Files:**
- Modify: `skills/new-product-backlog/templates/editor.html:652-701` (the `// <applyFilters>` … `// </applyFilters>` block)
- Test: `tests/editor_filters.test.mjs` (append at the end, before the final `console.log`)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `applyFilters(items, opts)` gains two recognised `opts` keys —
  - `opts.hideEmbargo` (`boolean`, default `false`): when `true`, drop items whose `doNotBuildBefore` is strictly after `today`.
  - `opts.today` (`string`, `"YYYY-MM-DD"`, optional): the reference date. When omitted, `applyFilters` computes the real current date itself.

  Task 2 calls this as `applyFilters(state.items, { …, hideEmbargo: state.hideEmbargo, today: todayStr() })`.

- [ ] **Step 1: Write the failing tests**

Open `tests/editor_filters.test.mjs`. The file currently ends with:

```js
assert.deepEqual(out.map((i) => i.id), ["BL-010"]);

console.log("editor_filters.test.mjs: all assertions passed");
```

Insert the following block **between** those two lines (keep the `console.log` last):

```js
/* ---------- hideEmbargo ---------- *
   An item is embargoed when doNotBuildBefore is set AND strictly after the
   reference date — the same rule the row's "Embargo" badge uses. A date equal
   to today is NOT embargoed: the gate expires that morning, so the item is
   startable and stays visible. Dependencies are deliberately not part of this
   filter. `today` is injected via opts so the boundary is testable without
   mocking the clock. */
const TODAY = "2026-09-05";
const emb = [
  { id: "BL-101", name: "Now", status: "new", priority: "high", doNotBuildBefore: null },
  { id: "BL-102", name: "NoField", status: "new", priority: "high" },
  { id: "BL-103", name: "Past", status: "new", priority: "high", doNotBuildBefore: "2026-09-04" },
  { id: "BL-104", name: "Today", status: "new", priority: "high", doNotBuildBefore: "2026-09-05" },
  { id: "BL-105", name: "Tomorrow", status: "new", priority: "high", doNotBuildBefore: "2026-09-06" },
  { id: "BL-106", name: "NextYear", status: "new", priority: "high", doNotBuildBefore: "2027-01-01" },
];
const embBase = { ...base, today: TODAY };

// Default (absent / false) keeps every item -> unchecked is a no-op.
out = applyFilters(emb, embBase);
assert.deepEqual(out.map((i) => i.id),
  ["BL-101", "BL-102", "BL-103", "BL-104", "BL-105", "BL-106"]);
out = applyFilters(emb, { ...embBase, hideEmbargo: false });
assert.equal(out.length, 6);

// Checked drops only strictly-future dates. null, a missing field, a past date,
// and today's date all survive.
out = applyFilters(emb, { ...embBase, hideEmbargo: true });
assert.deepEqual(out.map((i) => i.id), ["BL-101", "BL-102", "BL-103", "BL-104"]);

// The boundary, asserted on its own so a regression names itself.
out = applyFilters(
  [{ id: "BL-104", name: "Today", status: "new", priority: "high", doNotBuildBefore: TODAY }],
  { ...embBase, hideEmbargo: true },
);
assert.deepEqual(out.map((i) => i.id), ["BL-104"], "a date equal to today is not embargoed");

// Composes with search and with the status filter.
out = applyFilters(emb, { ...embBase, hideEmbargo: true, search: "past" });
assert.deepEqual(out.map((i) => i.id), ["BL-103"]);
out = applyFilters(
  [
    { id: "BL-110", name: "A", status: "new", priority: "high", doNotBuildBefore: "2027-01-01" },
    { id: "BL-111", name: "B", status: "shipped", priority: "high", doNotBuildBefore: null },
    { id: "BL-112", name: "C", status: "new", priority: "high", doNotBuildBefore: null },
  ],
  { ...embBase, hideEmbargo: true, statuses: ["new"] },
);
assert.deepEqual(out.map((i) => i.id), ["BL-112"]);

/* The two hide toggles are independent and compose as AND. */
const both = [
  { id: "BL-201", name: "Clean", status: "new", priority: "high", dependencies: [], doNotBuildBefore: null },
  { id: "BL-202", name: "OnlyEmbargo", status: "new", priority: "high", dependencies: [], doNotBuildBefore: "2027-01-01" },
  { id: "BL-203", name: "OnlyBlocked", status: "new", priority: "high", dependencies: ["BL-299"], doNotBuildBefore: null },
  { id: "BL-204", name: "BothHolds", status: "new", priority: "high", dependencies: ["BL-299"], doNotBuildBefore: "2027-01-01" },
];
out = applyFilters(both, { ...embBase, hideEmbargo: true });
assert.deepEqual(out.map((i) => i.id), ["BL-201", "BL-203"]);
out = applyFilters(both, { ...embBase, hideBlocked: true });
assert.deepEqual(out.map((i) => i.id), ["BL-201", "BL-202"]);
out = applyFilters(both, { ...embBase, hideBlocked: true, hideEmbargo: true });
assert.deepEqual(out.map((i) => i.id), ["BL-201"]);

// Omitting opts.today falls back to the real current date. A date far in the
// past is never embargoed and one far in the future always is, whatever "now" is.
out = applyFilters(
  [
    { id: "BL-301", name: "LongPast", status: "new", priority: "high", doNotBuildBefore: "1970-01-01" },
    { id: "BL-302", name: "LongFuture", status: "new", priority: "high", doNotBuildBefore: "9999-12-31" },
  ],
  { ...base, hideEmbargo: true },
);
assert.deepEqual(out.map((i) => i.id), ["BL-301"]);
```

Note `base` is the shared options object already declared earlier in the file
(`const base = { search: "", statuses: [], priorities: [], sortKey: "id", sortDir: "asc" };`)
and `out` is the already-declared `let` — do not redeclare either.

- [ ] **Step 2: Run the test to verify it fails**

Run: `node tests/editor_filters.test.mjs`

Expected: FAIL. The first new assertion to break is the `hideEmbargo: true` one —
`applyFilters` ignores the unknown option, so all six items come back:

```
AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
+ actual - expected
+ [ 'BL-101', 'BL-102', 'BL-103', 'BL-104', 'BL-105', 'BL-106' ]
- [ 'BL-101', 'BL-102', 'BL-103', 'BL-104' ]
```

If it *passes*, you edited the template first — revert and write the test first.

- [ ] **Step 3: Write the minimal implementation**

In `skills/new-product-backlog/templates/editor.html`, inside the sentinel block.

First, extend the option-reading preamble. Find:

```js
  const sortKey = opts.sortKey || "id";
  const sortDir = opts.sortDir === "desc" ? "desc" : "asc";
  const PRIORITY_RANK = { critical: 0, high: 1, medium: 2, low: 3 };
```

and insert after it:

```js
  /* Embargo is a per-item date gate — no cross-item lookup, so it needs no
     pre-pass. `today` is injected by the caller (renderBody passes todayStr())
     and only computed here as a fallback: this block is eval'd standalone by
     tests/editor_filters.test.mjs and cannot reach todayStr(). Dates are
     schema-validated YYYY-MM-DD, so a lexicographic ">" is chronological. */
  const hideEmbargo = opts.hideEmbargo === true;
  let today = opts.today;
  if (!today) {
    const now = new Date();
    const pad = function (n) { return String(n).padStart(2, "0"); };
    today = now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate());
  }
  const isEmbargoed = function (it) {
    return !!it.doNotBuildBefore && it.doNotBuildBefore > today;
  };
```

Then add the predicate to the existing filter pass. Find:

```js
  let out = items.filter(function (it) {
    if (hideBlocked && isBlocked(it)) return false;
    if (statuses.length && statuses.indexOf(it.status) === -1) return false;
```

and change it to:

```js
  let out = items.filter(function (it) {
    if (hideBlocked && isBlocked(it)) return false;
    if (hideEmbargo && isEmbargoed(it)) return false;
    if (statuses.length && statuses.indexOf(it.status) === -1) return false;
```

Finally, correct the now-stale comment above `hideBlocked`. Find the line:

```js
     or not shipped blocks. Embargo is not part of this filter. */
```

and replace it with:

```js
     or not shipped blocks. Embargo is a separate, independent toggle. */
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node tests/editor_filters.test.mjs`

Expected: `editor_filters.test.mjs: all assertions passed`

Then run the full suite to confirm nothing else moved:

```bash
node tests/editor_filters.test.mjs && node tests/editor_prompts.test.mjs && \
node tests/parse_feature_cell.test.mjs && \
python3 -m unittest discover -s tests -p "*_test.py"
```

Expected: all four green, Python reports `Ran 119 tests ... OK`.

- [ ] **Step 5: Commit**

```bash
git add tests/editor_filters.test.mjs skills/new-product-backlog/templates/editor.html
git commit -m "feat(new-product-backlog): embargo predicate in applyFilters

An item is embargoed when doNotBuildBefore is strictly after the reference
date, matching the Embargo badge rule. The date is injected via opts.today so
the function stays pure and the today-boundary is testable; it falls back to
the real current date because the sentinel block is eval'd standalone by the
filter tests and cannot reach todayStr().

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Toolbar toggle and state wiring

**Files:**
- Modify: `skills/new-product-backlog/templates/editor.html` at these eight sites (line numbers are pre-Task-1; they shift by roughly +16 after Task 1's insertion, so locate by the quoted text, not the number):
  - `:632-637` toolbar markup
  - `:763` `state` object
  - `:965` `renderBody()`
  - `:1388-1390` `clearFilters()`
  - `:1414` `persistView()`
  - `:1441` `restoreView()`
  - `:1781` `boot()` event listener
  - `:1818` `boot()` restore-sync
- Test: no automated test — the editor's DOM layer has no headless harness in this repo (`editor_filters.test.mjs` and `editor_prompts.test.mjs` both test extracted pure functions only). Verified by the Step 6 manual smoke run.

**Interfaces:**
- Consumes: `applyFilters(items, opts)` from Task 1, with `opts.hideEmbargo` (boolean) and `opts.today` (`"YYYY-MM-DD"` string).
- Produces: `state.hideEmbargo` (boolean) and the DOM element `#hide-embargo` (an `input[type=checkbox]`). Nothing downstream depends on these.

- [ ] **Step 1: Add the toolbar markup**

Find:

```html
    <div class="filter-group">
      <label class="toggle" for="hide-blocked">
        <input type="checkbox" id="hide-blocked">
        <span>Hide Blocked</span>
      </label>
    </div>
```

Replace with:

```html
    <div class="filter-group">
      <label class="toggle" for="hide-blocked">
        <input type="checkbox" id="hide-blocked">
        <span>Hide Blocked</span>
      </label>
      <label class="toggle" for="hide-embargo">
        <input type="checkbox" id="hide-embargo">
        <span>Hide Embargo</span>
      </label>
    </div>
```

Both toggles share the one `.filter-group`, which is already `display: flex` with
`gap: 8px`, so they sit side by side with no CSS change. The existing `.toggle`
rules (hover, `:has(input:checked)`, `:focus-within`) apply to the new label
automatically — **do not add new CSS.**

- [ ] **Step 2: Add the state flag**

Find:

```js
  hideBlocked: false,    // when true, drop items waiting on an unshipped dependency
```

Replace with:

```js
  hideBlocked: false,    // when true, drop items waiting on an unshipped dependency
  hideEmbargo: false,    // when true, drop items whose doNotBuildBefore is still in the future
```

- [ ] **Step 3: Pass it through `renderBody()`**

Find, inside `renderBody()`:

```js
  const rows = applyFilters(state.items, {
    search: state.search,
    statuses: state.statuses,
    priorities: state.priorities,
    hideBlocked: state.hideBlocked,
    sortKey: state.sortKey,
    sortDir: state.sortDir,
  });
```

Replace with:

```js
  const rows = applyFilters(state.items, {
    search: state.search,
    statuses: state.statuses,
    priorities: state.priorities,
    hideBlocked: state.hideBlocked,
    hideEmbargo: state.hideEmbargo,
    today: todayStr(),
    sortKey: state.sortKey,
    sortDir: state.sortDir,
  });
```

`todayStr()` is read at render time, so a page left open across midnight picks
up the new date on its next re-render.

- [ ] **Step 4: Wire reset, persistence, and boot**

Four separate edits.

**(a) `clearFilters()`** — find:

```js
  state.hideBlocked = false;
  document.getElementById("search").value = "";
  document.getElementById("hide-blocked").checked = false;
```

Replace with:

```js
  state.hideBlocked = false;
  state.hideEmbargo = false;
  document.getElementById("search").value = "";
  document.getElementById("hide-blocked").checked = false;
  document.getElementById("hide-embargo").checked = false;
```

**(b) `persistView()`** — find:

```js
      hideBlocked: state.hideBlocked,
      sortKey: state.sortKey,
```

Replace with:

```js
      hideBlocked: state.hideBlocked,
      hideEmbargo: state.hideEmbargo,
      sortKey: state.sortKey,
```

**(c) `restoreView()`** — find:

```js
  if (typeof saved.hideBlocked === "boolean") state.hideBlocked = saved.hideBlocked;
```

Replace with:

```js
  if (typeof saved.hideBlocked === "boolean") state.hideBlocked = saved.hideBlocked;
  if (typeof saved.hideEmbargo === "boolean") state.hideEmbargo = saved.hideEmbargo;
```

The `typeof` guard is what makes a view persisted before this change safe: the
key is simply absent, so `state.hideEmbargo` keeps its `false` default.

**(d) `boot()`, two spots.** First the listener — find:

```js
  document.getElementById("hide-blocked").addEventListener("change", function (e) {
    state.hideBlocked = e.target.checked; persistView(); renderBody(); syncSelectionUI();
  });
```

Replace with:

```js
  document.getElementById("hide-blocked").addEventListener("change", function (e) {
    state.hideBlocked = e.target.checked; persistView(); renderBody(); syncSelectionUI();
  });
  document.getElementById("hide-embargo").addEventListener("change", function (e) {
    state.hideEmbargo = e.target.checked; persistView(); renderBody(); syncSelectionUI();
  });
```

`syncSelectionUI()` is required, not optional: hiding rows changes
`state.visibleIds`, which invalidates the select-all checkbox's tri-state.

Then the restore-sync, further down — find:

```js
  document.getElementById("hide-blocked").checked = state.hideBlocked;
```

Replace with:

```js
  document.getElementById("hide-blocked").checked = state.hideBlocked;
  document.getElementById("hide-embargo").checked = state.hideEmbargo;
```

- [ ] **Step 5: Verify the template still parses and the suite is green**

The filter tests re-extract `applyFilters` from the edited template, so they
catch a syntax error introduced inside the sentinels. Guard the rest of the file
with an explicit parse of the whole inline script:

```bash
python3 - <<'PY'
import re, pathlib, subprocess, sys
html = pathlib.Path("skills/new-product-backlog/templates/editor.html").read_text()
scripts = re.findall(r"<script>([\s\S]*?)</script>", html)
assert scripts, "no inline <script> found"
src = "\n".join(scripts)
p = subprocess.run(["node", "--check", "-"], input=src, capture_output=True, text=True)
print(p.stdout, p.stderr)
sys.exit(p.returncode)
PY
```

Expected: exit 0, no output. (If `node --check -` refuses stdin on your Node
version, write `src` to a `.js` file under the scratchpad directory and check
that instead.)

Then assert the eight wiring sites are all present:

```bash
grep -c "hideEmbargo\|hide-embargo" skills/new-product-backlog/templates/editor.html
```

Expected: `12` — state declaration, `renderBody`, `clearFilters` (×2),
`persistView`, `restoreView` (×2 on one line counts once), listener (×2 on
separate lines), boot sync, markup (×2). Treat the exact count as a sanity
signal, not a gate; what matters is that every site in Step 4 is present.

Full suite:

```bash
node tests/editor_filters.test.mjs && node tests/editor_prompts.test.mjs && \
node tests/parse_feature_cell.test.mjs && \
python3 -m unittest discover -s tests -p "*_test.py"
```

Expected: all green.

- [ ] **Step 6: Manual smoke test**

This is the only verification the DOM wiring gets — actually run it, do not skip.

```bash
cd "$(mktemp -d)" && git init -q . && \
python3 /Users/subhadipchatterjee/Documents/Projects/product-backlog-skill/skills/new-product-backlog/scripts/backlog.py \
  add --name "Future work" --dnbb 2099-01-01 && \
python3 /Users/subhadipchatterjee/Documents/Projects/product-backlog-skill/skills/new-product-backlog/scripts/backlog.py \
  add --name "Ready now" && \
python3 /Users/subhadipchatterjee/Documents/Projects/product-backlog-skill/skills/new-product-backlog/scripts/backlog.py \
  add --name "Gated today" --dnbb "$(date +%F)" && \
python3 /Users/subhadipchatterjee/Documents/Projects/product-backlog-skill/skills/new-product-backlog/scripts/backlog.py serve
```

Open the printed URL and confirm:
1. `Hide Embargo` renders immediately right of `Hide Blocked`, same pill styling.
2. Unchecked: all three items visible; "Future work" shows an amber **Embargo** badge.
3. Checked: "Future work" disappears. **"Gated today" stays** — the boundary.
4. "Ready now" is never affected.
5. Reload the page: the checkbox is still checked and the row still hidden.
6. Tick both hide toggles: they compose, neither resets the other.
7. The "N on hold" readout does **not** change when you toggle the filter.

Ctrl-C the server when done.

- [ ] **Step 7: Commit**

```bash
git add skills/new-product-backlog/templates/editor.html
git commit -m "feat(new-product-backlog): Hide Embargo toggle in the editor toolbar

Mirrors Hide Blocked at every touchpoint — markup, state, renderBody,
clearFilters, persistView/restoreView, and the boot listener. The two compose
as AND. A view persisted before this change simply lacks the key and keeps the
false default.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Docs and version bump

**Files:**
- Modify: `skills/new-product-backlog/SKILL.md:220`
- Modify: `README.md:222`
- Modify: `.claude-plugin/plugin.json:4`

**Interfaces:**
- Consumes: the shipped behaviour from Tasks 1 and 2.
- Produces: nothing consumed by code.

- [ ] **Step 1: Update SKILL.md**

Find (one line, in the editor section):

```
The editor is a self-contained page (inline CSS/JS, no CDN, theme-aware) that lists all items and supports add/edit, delete (discard by default, hard-delete as an explicit option), column sort, multi-select status/priority filter chips, text search across id/name/description/notes, and per-row checkboxes for batching several items into one execution prompt. Rows are **expandable** to reveal the full description, notes, and artifact links, and it surfaces warnings when a dependency isn't yet `shipped` or when `doNotBuildBefore` is in the future.
```

Replace with:

```
The editor is a self-contained page (inline CSS/JS, no CDN, theme-aware) that lists all items and supports add/edit, delete (discard by default, hard-delete as an explicit option), column sort, multi-select status/priority filter chips, text search across id/name/description/notes, and per-row checkboxes for batching several items into one execution prompt. Rows are **expandable** to reveal the full description, notes, and artifact links, and it surfaces warnings when a dependency isn't yet `shipped` or when `doNotBuildBefore` is in the future. Two independent toolbar toggles suppress those two classes of not-yet-actionable work: **Hide Blocked** drops items waiting on an unshipped dependency, and **Hide Embargo** drops items whose `doNotBuildBefore` is still in the future (a date equal to today is *not* embargoed — that item is startable). Both compose with each other and with the chips and search.
```

- [ ] **Step 2: Update README.md**

In the `## The editor` section, find the sentence ending:

```
Filter/sort/search state persists across refreshes (per-backlog).
```

Replace that one sentence with:

```
Two independent toolbar toggles hide the not-yet-actionable: **Hide Blocked** (waiting on an unshipped dependency) and **Hide Embargo** (`doNotBuildBefore` still in the future; a date equal to today stays visible). Filter/sort/search state persists across refreshes (per-backlog).
```

- [ ] **Step 3: Bump the plugin version**

In `.claude-plugin/plugin.json`, change:

```json
  "version": "0.8.0",
```

to:

```json
  "version": "0.9.0",
```

- [ ] **Step 4: Verify**

```bash
python3 -c 'import json; print(json.load(open(".claude-plugin/plugin.json"))["version"])'
grep -c "Hide Embargo" skills/new-product-backlog/SKILL.md README.md
```

Expected: `0.9.0`, then `skills/new-product-backlog/SKILL.md:1` and `README.md:1`.

Then the full suite one last time:

```bash
node tests/editor_filters.test.mjs && node tests/editor_prompts.test.mjs && \
node tests/parse_feature_cell.test.mjs && \
python3 -m unittest discover -s tests -p "*_test.py"
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add skills/new-product-backlog/SKILL.md README.md .claude-plugin/plugin.json
git commit -m "docs(new-product-backlog): document Hide Embargo; bump to 0.9.0

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| Filter rule (`>` today, null/past/today survive) | 1, Steps 1 & 3 |
| Where "today" comes from (`opts.today` + fallback) | 1, Step 3 |
| Ordering inside `applyFilters` (inline, after `hideBlocked`, no pre-pass) | 1, Step 3 |
| State plumbing — all 7 table rows | 2, Steps 1–4 |
| `syncSelectionUI()` in the listener | 2, Step 4(d) |
| Deliberately unchanged: readout, selection, badge rule | Not edited by any task; asserted in 2, Step 6 item 7 |
| Testing — all 8 enumerated cases | 1, Step 1 |
| Docs & version | 3 |

No gaps.

**Placeholder scan:** none — every code step carries the literal before/after text.

**Type consistency:** `hideEmbargo` (boolean) and `today` (`"YYYY-MM-DD"` string)
are named identically in Task 1's `opts` contract and Task 2's `renderBody` call.
DOM id `hide-embargo` is used identically in the markup and all four
`getElementById` sites.
