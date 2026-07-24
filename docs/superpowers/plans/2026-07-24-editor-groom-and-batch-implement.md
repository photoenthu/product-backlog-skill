# Backlog editor: Groom action & batch Implement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-item **Groom** action (kebab menu → modal that captures a free-text concern and copies a `/backlog-analyzer` prompt) and **checkbox multi-select** feeding an **Implement** button that copies a `/master-backlog-executor` prompt for the selected ids.

**Architecture:** Everything is client-side in the single self-contained editor template `skills/new-product-backlog/templates/editor.html`. No server route, CLI subcommand, or schema field changes — the editor's only new behavior is writing text to the clipboard. The three new pure string helpers (`groomPrompt`, `implementPrompt`, `sortBacklogIds`) live in sentinel-delimited comment blocks so `tests/editor_prompts.test.mjs` can extract and assert them from the HTML without a browser, exactly as it already does for `backlogPrompt`.

**Tech Stack:** Vanilla ES5-style browser JS (no build step, no framework, no CDN), inline CSS with CSS custom properties, Node's built-in `node:assert` + `node:fs` for tests (no package.json, no dependencies).

**Design doc:** `docs/superpowers/specs/2026-07-24-editor-groom-and-batch-implement-design.md`

## Global Constraints

- **No new dependencies, no build step, no CDN.** The editor is a single self-contained HTML file with inline CSS/JS; tests are plain `.mjs` files run directly with `node`.
- **Never `innerHTML` with backlog text.** All DOM is built through the existing `h(tag, attrs, ...children)` helper, which routes text through `textContent`. The `html:` attribute is intentionally unsupported.
- **Match the file's existing JS idiom:** `function () {}` callbacks (not arrow functions), `const`/`let`, string concatenation (not template literals), `/* … */` and `//` comments explaining *why*.
- **Prompt strings are a contract with the executing skills.** A typo hands the operator a prompt that triggers nothing. Every prompt string lives inside a `// <name> … // </name>` sentinel block and is asserted in `tests/editor_prompts.test.mjs`.
- **Exact prompt text** (copy verbatim):
  - Groom: `Run the /backlog-analyzer skill for BL-NNN. User's concern/feedback is: <concern>.`
  - Implement: `Run the /master-backlog-executor skill for these backlog ids: BL-AAA, BL-BBB.`
- **Run both JS test files after any editor change:** `node tests/editor_prompts.test.mjs && node tests/editor_filters.test.mjs`.
- Working branch is `editor-groom-batch-implement` (already created; the design doc is committed on it).

---

### Task 1: Prompt helpers + their test contracts

The three pure functions, TDD'd against the test file. No UI yet — this task's deliverable is the copyable strings themselves, verified by `node`.

**Files:**
- Modify: `skills/new-product-backlog/templates/editor.html` (insert after the `// </backlogPrompt>` block, currently line 1078)
- Test: `tests/editor_prompts.test.mjs` (rewrite — generalizes the existing single-block extractor to four blocks, keeping every existing assertion)

**Interfaces:**
- Consumes: nothing (first task).
- Produces, all defined in `editor.html` at top-level `<script>` scope:
  - `groomPrompt(id: string, concern: string) -> string`
  - `sortBacklogIds(ids: string[]) -> string[]` — new array, ascending by the id's numeric part; does not mutate its input
  - `implementPrompt(ids: string[]) -> string` — joins ids in the order given; the **caller** sorts

- [ ] **Step 1: Write the failing test**

Replace the entire contents of `tests/editor_prompts.test.mjs` with:

```js
// Guards the EXACT text the editor copies to the clipboard: the per-item
// Auto / Semi buttons, the kebab's Groom modal, and the header's batch
// Implement button. These strings are a contract with the executing skills —
// a typo here silently hands the user a prompt that won't trigger anything.
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const html = readFileSync(
  new URL("../skills/new-product-backlog/templates/editor.html", import.meta.url),
  "utf8",
);

// Pull one `// <name> … // </name>` block out of the template and evaluate it
// as a standalone function, so these assertions run without a browser.
function extract(name) {
  const re = new RegExp("// <" + name + ">([\\s\\S]*?)// </" + name + ">");
  const m = html.match(re);
  assert.ok(m, name + " sentinel block not found in editor.html");
  const src = m[1].trim().replace(new RegExp("^function\\s+" + name), "function");
  return eval("(" + src + ")");
}

const backlogPrompt = extract("backlogPrompt");
const groomPrompt = extract("groomPrompt");
const implementPrompt = extract("implementPrompt");
const sortBacklogIds = extract("sortBacklogIds");

/* ---------- Auto / Semi (pre-existing contract) ---------- */

// Auto -> pr-from-backlog
assert.equal(
  backlogPrompt("BL-001", "auto"),
  "Implement BL-001 using pr-from-backlog.",
);

// Semi -> semiauto-backlog-execution
assert.equal(
  backlogPrompt("BL-001", "semi"),
  "Implement BL-001 using semiauto-backlog-execution.",
);

// The id is substituted, not hardcoded.
assert.equal(
  backlogPrompt("BL-042", "auto"),
  "Implement BL-042 using pr-from-backlog.",
);
assert.equal(
  backlogPrompt("BL-137", "semi"),
  "Implement BL-137 using semiauto-backlog-execution.",
);

// Ids wider than 3 digits still round-trip verbatim.
assert.equal(
  backlogPrompt("BL-1000", "auto"),
  "Implement BL-1000 using pr-from-backlog.",
);

// Both prompts end with a period and name exactly one skill.
for (const mode of ["auto", "semi"]) {
  const out = backlogPrompt("BL-007", mode);
  assert.ok(out.endsWith("."), `prompt should end with a period: ${out}`);
  assert.ok(out.startsWith("Implement BL-007 using "), `unexpected prefix: ${out}`);
}

// The two modes must not produce the same prompt.
assert.notEqual(backlogPrompt("BL-001", "auto"), backlogPrompt("BL-001", "semi"));

/* ---------- Groom -> backlog-analyzer ---------- */

assert.equal(
  groomPrompt("BL-407", "it looks stale"),
  "Run the /backlog-analyzer skill for BL-407. User's concern/feedback is: it looks stale.",
);

// The id is substituted, not hardcoded; 4-digit ids round-trip.
assert.equal(
  groomPrompt("BL-1042", "no idea if this still matters"),
  "Run the /backlog-analyzer skill for BL-1042. User's concern/feedback is: no idea if this still matters.",
);

// Surrounding whitespace is trimmed off the concern.
assert.equal(
  groomPrompt("BL-1", "   padded   "),
  "Run the /backlog-analyzer skill for BL-1. User's concern/feedback is: padded.",
);

// Interior newlines survive verbatim — a multi-line concern stays multi-line.
assert.equal(
  groomPrompt("BL-2", "first line\nsecond line"),
  "Run the /backlog-analyzer skill for BL-2. User's concern/feedback is: first line\nsecond line.",
);

// A concern that already ends in terminal punctuation must not get a second one.
assert.equal(
  groomPrompt("BL-3", "is this still valid?"),
  "Run the /backlog-analyzer skill for BL-3. User's concern/feedback is: is this still valid?",
);
assert.equal(
  groomPrompt("BL-4", "already fixed."),
  "Run the /backlog-analyzer skill for BL-4. User's concern/feedback is: already fixed.",
);
assert.equal(
  groomPrompt("BL-5", "this is nonsense!"),
  "Run the /backlog-analyzer skill for BL-5. User's concern/feedback is: this is nonsense!",
);
assert.ok(
  !/\.\.$/.test(groomPrompt("BL-6", "trailing period.")),
  "must never produce a doubled period",
);

/* ---------- Implement -> master-backlog-executor ---------- */

assert.equal(
  implementPrompt(["BL-012", "BL-107", "BL-244"]),
  "Run the /master-backlog-executor skill for these backlog ids: BL-012, BL-107, BL-244.",
);

// A single selected id is not a special case.
assert.equal(
  implementPrompt(["BL-7"]),
  "Run the /master-backlog-executor skill for these backlog ids: BL-7.",
);

/* ---------- sortBacklogIds ---------- */

// Numeric, not lexicographic ("BL-107" must not sort before "BL-9").
assert.deepEqual(
  sortBacklogIds(["BL-107", "BL-12", "BL-9"]),
  ["BL-9", "BL-12", "BL-107"],
);

// Zero-padded and unpadded ids of the same number compare by number.
assert.deepEqual(
  sortBacklogIds(["BL-30", "BL-004", "BL-2"]),
  ["BL-2", "BL-004", "BL-30"],
);

// Does not mutate its input.
const input = ["BL-9", "BL-1"];
sortBacklogIds(input);
assert.deepEqual(input, ["BL-9", "BL-1"], "sortBacklogIds must not mutate its argument");

// The composition the editor actually calls.
assert.equal(
  implementPrompt(sortBacklogIds(["BL-107", "BL-9", "BL-12"])),
  "Run the /master-backlog-executor skill for these backlog ids: BL-9, BL-12, BL-107.",
);

/* ---------- Cross-prompt sanity ---------- */

// Each prompt names exactly one skill, and the three are all distinct.
const all = [
  backlogPrompt("BL-1", "auto"),
  groomPrompt("BL-1", "concern"),
  implementPrompt(["BL-1"]),
];
assert.equal(new Set(all).size, 3, "the three prompts must be distinct");
assert.ok(!groomPrompt("BL-1", "c").includes("master-backlog-executor"));
assert.ok(!implementPrompt(["BL-1"]).includes("backlog-analyzer"));

console.log("editor_prompts.test.mjs: all assertions passed");
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node tests/editor_prompts.test.mjs`

Expected: FAIL — `AssertionError: groomPrompt sentinel block not found in editor.html`

- [ ] **Step 3: Write the minimal implementation**

In `skills/new-product-backlog/templates/editor.html`, immediately after the existing `// </backlogPrompt>` line (currently line 1078) and before `function legacyCopy(text) {`, insert:

```js
// <groomPrompt>
function groomPrompt(id, concern) {
  // The concern is trimmed but its interior newlines are kept, so a multi-line
  // worry pastes as written. The template's final period is skipped when the
  // concern already ends in terminal punctuation (otherwise: "…stale..").
  const body = String(concern == null ? "" : concern).trim();
  const tail = /[.?!]$/.test(body) ? "" : ".";
  return "Run the /backlog-analyzer skill for " + id +
    ". User's concern/feedback is: " + body + tail;
}
// </groomPrompt>

// <sortBacklogIds>
function sortBacklogIds(ids) {
  // Board order, not click order: compare the numeric part so BL-9 precedes
  // BL-107 (a plain string sort would not). Ties fall back to the raw string
  // so zero-padded variants stay deterministic.
  const num = function (id) {
    const m = String(id).match(/(\d+)/);
    return m ? parseInt(m[1], 10) : 0;
  };
  return ids.slice().sort(function (a, b) {
    const d = num(a) - num(b);
    return d !== 0 ? d : String(a).localeCompare(String(b));
  });
}
// </sortBacklogIds>

// <implementPrompt>
function implementPrompt(ids) {
  // Takes the ids in the order given — the caller sorts with sortBacklogIds.
  return "Run the /master-backlog-executor skill for these backlog ids: " +
    ids.join(", ") + ".";
}
// </implementPrompt>
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node tests/editor_prompts.test.mjs && node tests/editor_filters.test.mjs`

Expected, both lines printed, exit 0:
```
editor_prompts.test.mjs: all assertions passed
editor_filters.test.mjs: all assertions passed
```

- [ ] **Step 5: Commit**

```bash
git add tests/editor_prompts.test.mjs skills/new-product-backlog/templates/editor.html
git commit -m "feat(new-product-backlog): groom + batch-implement clipboard prompt helpers"
```

---

### Task 2: Groom action — kebab entry + concern modal

**Files:**
- Modify: `skills/new-product-backlog/templates/editor.html`
  - CSS: append to the `/* ---------- Modal ---------- */` section (after the `.hint` rule, currently line 560)
  - `openRowMenu()` (currently lines 1273–1292): add the `Groom` menu item
  - JS: add `openGroomModal()` + `submitGroom()` after `closeModal()` (currently line 1459)

**Interfaces:**
- Consumes: `groomPrompt(id, concern)` from Task 1; the existing `h()`, `copyToClipboard(text) -> Promise<boolean>`, `closeModal()`, `closeRowMenu()`, and the shared `modalState` variable.
- Produces: `openGroomModal(item)` — opens the modal for one backlog item object; `submitGroom(item, concernIn, errBox)`.

This task's verification is manual (DOM behavior the `.mjs` tests can't reach) plus the unchanged automated suite.

- [ ] **Step 1: Add the CSS**

In `editor.html`, after the `.hint { … }` rule (currently line 560), insert:

```css
/* Groom modal: one required free-text concern, narrower than the edit form. */
.modal.groom { max-width: 520px; }
.modal-head .subject { margin-top: 5px; font-size: 13px; color: var(--muted); }
.field textarea.groom-in { min-height: 140px; }

/* Disabled buttons (Groom's OK before a concern is typed; Implement with an
   empty selection) must not light up on hover. */
.btn[disabled] { opacity: .5; cursor: not-allowed; }
.btn[disabled]:hover { background: var(--surface); border-color: var(--border-2); }
.btn.primary[disabled]:hover { background: var(--accent); border-color: var(--accent); }
```

- [ ] **Step 2: Add the `Groom` kebab entry**

In `openRowMenu()`, insert a third `h("button", …)` between the existing `Edit` and `Discard` entries, so the appended list reads Edit → Groom → Discard → separator → Delete:

```js
    h("button", { type: "button", role: "menuitem",
      onClick: function () { closeRowMenu(); openGroomModal(item); } }, "Groom"),
```

- [ ] **Step 3: Add the modal**

After `closeModal()` (currently ending line 1459) and before `async function saveModal(f) {`, insert:

```js
/* ---------- Groom modal ----------
   Captures one free-text concern and copies a /backlog-analyzer prompt. The
   skill hard-gates on a non-empty concern, so OK stays disabled until one is
   typed. A failed clipboard write keeps the modal open — closing it would
   throw away text the user just typed with no way to recover it. */
function openGroomModal(item) {
  closeRowMenu();
  // Shares `modalState` with the edit modal so the Escape handler and
  // #modal-root teardown work unchanged, and the two can never both be open.
  modalState = { kind: "groom", editingId: null };

  const errBox = h("div", { class: "modal-error" });
  const concernIn = h("textarea", { class: "groom-in", id: "f-concern", required: true,
    placeholder: "e.g. a recent fix may already have resolved this" });
  const okBtn = h("button", { class: "btn primary", type: "submit", disabled: true,
    onClick: function () { form.requestSubmit(); } }, "Copy prompt");

  concernIn.addEventListener("input", function () {
    okBtn.disabled = concernIn.value.trim() === "";
  });
  concernIn.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      if (!okBtn.disabled) form.requestSubmit();
    }
  });

  const form = h("form", { onSubmit: function (e) {
      e.preventDefault();
      submitGroom(item, concernIn, errBox);
    } },
    errBox,
    h("div", { class: "field" },
      h("label", { for: "f-concern" }, "Your concern / feedback",
        h("span", { class: "req" }, "*")),
      concernIn,
      h("div", { class: "hint" },
        "What worries you about this entry — stale, already fixed, unclear value?")));

  const root = document.getElementById("modal-root");
  root.textContent = "";
  const scrim = h("div", { class: "scrim",
    onClick: function (e) { if (e.target === scrim) closeModal(); } },
    h("div", { class: "modal groom", role: "dialog", "aria-modal": "true",
               "aria-label": "Groom " + item.id },
      h("div", { class: "modal-head" },
        h("div", null,
          h("div", { class: "eyebrow" }, "Groom item"),
          h("h2", null, item.id),
          h("div", { class: "subject" }, item.name)),
        h("button", { class: "x", type: "button", "aria-label": "Close",
                      onClick: closeModal }, "✕")),
      h("div", { class: "modal-body" }, form),
      h("div", { class: "modal-foot" },
        h("button", { class: "btn", type: "button", onClick: closeModal }, "Cancel"),
        okBtn)));
  root.append(scrim);
  setTimeout(function () { concernIn.focus(); }, 0);
}

function submitGroom(item, concernIn, errBox) {
  const text = groomPrompt(item.id, concernIn.value);
  copyToClipboard(text).then(function (ok) {
    if (ok) { closeModal(); return; }
    errBox.textContent = "";
    errBox.append(h("span", { class: "etitle" }, "Could not copy. "),
      "Your browser blocked clipboard access. Copy this prompt manually:\n\n" + text);
    errBox.classList.add("show");
    errBox.scrollIntoView({ block: "nearest" });
  });
}
```

- [ ] **Step 4: Verify the automated suite still passes**

Run: `node tests/editor_prompts.test.mjs && node tests/editor_filters.test.mjs`

Expected: both `all assertions passed` lines, exit 0. (Task 1's `groomPrompt` assertions cover the copied text; this step confirms the edits didn't disturb the sentinel blocks.)

- [ ] **Step 5: Verify the modal by hand**

Serve any backlog with at least one item:

```bash
python3 skills/new-product-backlog/scripts/backlog.py serve docs/backlog/product-backlog.json
```

If this repo has no backlog file, create a scratch one first:

```bash
python3 skills/new-product-backlog/scripts/backlog.py add /tmp/pb-groom-check.json \
  --name "Scratch item" --description "for manual UI check" --priority high
python3 skills/new-product-backlog/scripts/backlog.py serve /tmp/pb-groom-check.json
```

Open the printed URL and confirm, in order:
1. A row's `⋯` menu lists **Edit · Groom · Discard · ─── · Delete** (the divider stays where it already was, above Delete).
2. `Groom` opens a modal headed `GROOM ITEM` / the id / the item name, with the textarea focused.
3. `Copy prompt` is greyed out and unclickable; typing a space keeps it disabled; typing a word enables it.
4. Typing `it looks stale` and clicking `Copy prompt` closes the modal, and pasting gives exactly:
   `Run the /backlog-analyzer skill for BL-NNN. User's concern/feedback is: it looks stale.`
5. Re-open, type a multi-line concern, press ⌘/Ctrl-Enter — it copies and closes with the newlines intact.
6. Esc and a click on the dark backdrop both close the modal.

- [ ] **Step 6: Commit**

```bash
git add skills/new-product-backlog/templates/editor.html
git commit -m "feat(new-product-backlog): Groom action in the row menu with a concern modal"
```

---

### Task 3: Multi-select checkboxes + header Implement button

One deliverable: the checkbox column and the button that consumes it are useless apart, so they ship and are reviewed together.

**Files:**
- Modify: `skills/new-product-backlog/templates/editor.html`
  - HTML: `.header-actions` block (currently lines 582–585)
  - CSS: after the row-disclosure section (after the `.expand-btn.open .chev` rule, currently line 380)
  - JS: `state` (line ~735), `DETAIL_COLSPAN` (line ~751), `buildHead()` (line ~837), `refresh()` (line ~875), `pruneExpanded()` (line ~882), `renderBody()` (line ~905), `renderRow()` (line ~944), `boot()` (line ~1520); new selection helpers

**Interfaces:**
- Consumes: `sortBacklogIds(ids)` and `implementPrompt(ids)` from Task 1; existing `h()`, `copyToClipboard()`, `itemsById()`, `applyFilters()`.
- Produces:
  - `state.selected: Set<string>` — ticked ids; survives re-render and filtering; not persisted to `localStorage`
  - `state.visibleIds: string[]` — ids of the rows the last `renderBody()` drew, in display order
  - `pruneStale()` — replaces `pruneExpanded()`; evicts vanished ids from `state.expanded` **and** `state.selected`
  - `selectableVisible() -> string[]` — visible, non-discarded ids
  - `syncSelectionUI()` — updates the Implement button + select-all tri-state without re-rendering the body
  - `toggleSelectAllVisible(on: boolean)`, `copySelectedImplementPrompt()`

- [ ] **Step 1: Add the header button**

Replace the `.header-actions` block:

```html
    <div class="header-actions">
      <button class="btn icon" id="theme-toggle" title="Toggle theme" aria-label="Toggle color theme">◑</button>
      <button class="btn" id="implement-btn" type="button" disabled
              title="Copy a master-backlog-executor prompt for the selected items">
        <span class="exec-ic" aria-hidden="true">⧉</span><span class="implement-label">Implement</span>
      </button>
      <button class="btn primary" id="new-btn">+ New item</button>
    </div>
```

- [ ] **Step 2: Add the CSS**

After the `.expand-btn.open .chev { … }` rule (currently line 380), insert:

```css
/* ---------- Batch-select column ---------- */
thead th.select-col { padding: 0 2px 0 8px; width: 30px; }
td.select-cell { padding: 0 2px 0 8px; width: 30px; text-align: center; }
.row-check {
  margin: 0; cursor: pointer; accent-color: var(--accent);
  width: 15px; height: 15px; vertical-align: middle;
}
.row-check:disabled { cursor: not-allowed; opacity: .4; }
.row-check:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }

/* Copy feedback on the header Implement button (mirrors .exec-btn's). */
.btn.is-copied { color: var(--st-shipped); border-color: currentColor; }
.btn.is-failed { color: var(--block); border-color: currentColor; }
.btn .exec-ic { font-size: 11px; color: var(--faint); }
.btn.is-copied .exec-ic, .btn.is-failed .exec-ic { color: currentColor; }
```

- [ ] **Step 3: Extend the state and the detail colspan**

In `state`, add two fields after the `expanded` line:

```js
  expanded: new Set(),   // ids of rows whose detail drawer is open (survives re-render)
  selected: new Set(),   // ids ticked for the batch Implement prompt (never persisted)
  visibleIds: [],        // ids drawn by the last renderBody(), in display order
```

Update the `DETAIL_COLSPAN` comment and value (the drawer now also spans the checkbox column):

```js
// Detail drawer's single <td> spans every column except the priority rail:
// the checkbox column (+1), the disclosure column (+1), and all COLUMNS entries.
const DETAIL_COLSPAN = COLUMNS.length + 2;
```

- [ ] **Step 4: Widen the prune helper and the refresh cycle**

Replace `pruneExpanded()` with:

```js
/* Drop expansion + selection state for items that no longer exist (e.g.
   hard-deleted here or edited away in another session). */
function pruneStale() {
  if (!state.expanded.size && !state.selected.size) return;
  const ids = new Set(state.items.map(function (i) { return i.id; }));
  Array.from(state.expanded).forEach(function (id) {
    if (!ids.has(id)) state.expanded.delete(id);
  });
  Array.from(state.selected).forEach(function (id) {
    if (!ids.has(id)) state.selected.delete(id);
  });
}
```

And update `refresh()` to call it and to re-sync the selection chrome after the body is drawn:

```js
function refresh() {
  pruneStale();
  syncChipStates();
  renderReadout();
  renderBody();
  syncSelectionUI();
}
```

- [ ] **Step 5: Add the select-all header cell**

In `buildHead()`, insert the checkbox `<th>` between the rail and the disclosure column so the leading chrome reads rail │ ☐ │ ▸:

```js
  row.append(h("th", { class: "rail-col", "aria-hidden": "true" }));
  row.append(h("th", { class: "select-col" }, buildSelectAll()));
  row.append(h("th", { class: "expand-col", "aria-hidden": "true" }));
```

And add, directly after `buildHead()`:

```js
/* Select-all ticks only the rows currently visible — a select-all that reached
   filtered-out rows would silently batch items the user can't see. */
function buildSelectAll() {
  const cb = h("input", { type: "checkbox", class: "row-check", id: "select-all",
    "aria-label": "Select all visible items for batch implement",
    onChange: function () { toggleSelectAllVisible(cb.checked); } });
  return cb;
}
```

- [ ] **Step 6: Record the visible rows**

In `renderBody()`, immediately after the `applyFilters(...)` call that assigns `rows` and **before** the `if (!rows.length)` early return, add:

```js
  state.visibleIds = rows.map(function (r) { return r.id; });
```

- [ ] **Step 7: Add the per-row checkbox**

In `renderRow()`, after the priority-rail `tr.append(rail);` line and before the disclosure toggle, insert:

```js
  // batch-select checkbox. Discarded rows are unselectable: master-backlog-
  // executor's pre-flight declines the ENTIRE batch if any id is discarded,
  // so one slipped-in id would waste a whole run.
  const isDiscarded = it.status === "discarded";
  const check = h("input", { type: "checkbox", class: "row-check",
    "aria-label": "Select " + it.id + " for batch implement",
    disabled: isDiscarded || null,
    title: isDiscarded ? "Discarded items can't be implemented" : null,
    onChange: function () {
      if (check.checked) state.selected.add(it.id);
      else state.selected.delete(it.id);
      syncSelectionUI();
    } });
  check.checked = state.selected.has(it.id) && !isDiscarded;
  tr.append(h("td", { class: "select-cell" }, check));
```

- [ ] **Step 8: Add the selection helpers**

Insert after `renderRow()` ends (before the `/* ---------- Row detail drawer ---------- */` comment):

```js
/* ---------- Batch selection ---------- */

/* Visible AND selectable (discarded rows can't be batched). */
function selectableVisible() {
  const byId = itemsById();
  return state.visibleIds.filter(function (id) {
    const it = byId[id];
    return it && it.status !== "discarded";
  });
}

/* Reflect state.selected into the Implement button and the select-all
   tri-state. Deliberately does NOT re-render the body: a re-render on every
   tick would collapse any open detail drawer mid-selection. */
function syncSelectionUI() {
  const n = state.selected.size;
  const btn = document.getElementById("implement-btn");
  if (btn) {
    btn.disabled = n === 0;
    const lab = btn.querySelector(".implement-label");
    // Leave the label alone while it's flashing "Copied" / "Copy failed".
    const flashing = btn.classList.contains("is-copied") || btn.classList.contains("is-failed");
    if (lab && !flashing) lab.textContent = n ? "Implement (" + n + ")" : "Implement";
  }
  const all = document.getElementById("select-all");
  if (all) {
    const sel = selectableVisible();
    const on = sel.filter(function (id) { return state.selected.has(id); }).length;
    all.checked = sel.length > 0 && on === sel.length;
    all.indeterminate = on > 0 && on < sel.length;
    all.disabled = sel.length === 0;
  }
}

/* Unticking clears every visible id (including any discarded row that somehow
   carries a stale selection); ticking adds only the selectable ones. */
function toggleSelectAllVisible(on) {
  if (on) {
    selectableVisible().forEach(function (id) { state.selected.add(id); });
  } else {
    state.visibleIds.forEach(function (id) { state.selected.delete(id); });
  }
  renderBody();          // every row's checkbox must re-reflect the new state
  syncSelectionUI();
}

/* Selection is intentionally kept after copying, so the batch can be re-copied
   without re-ticking. */
function copySelectedImplementPrompt() {
  const ids = sortBacklogIds(Array.from(state.selected));
  if (!ids.length) return;
  const btn = document.getElementById("implement-btn");
  const lab = btn.querySelector(".implement-label");
  copyToClipboard(implementPrompt(ids)).then(function (ok) {
    lab.textContent = ok ? "Copied" : "Copy failed";
    btn.classList.add(ok ? "is-copied" : "is-failed");
    setTimeout(function () {
      btn.classList.remove("is-copied", "is-failed");
      syncSelectionUI();
    }, 1400);
  });
}
```

- [ ] **Step 9: Wire the button in `boot()`**

In `boot()`, after the existing `new-btn` listener line, add:

```js
  document.getElementById("implement-btn")
    .addEventListener("click", copySelectedImplementPrompt);
```

- [ ] **Step 10: Run the automated suite**

Run: `node tests/editor_prompts.test.mjs && node tests/editor_filters.test.mjs`

Expected: both `all assertions passed` lines, exit 0.

- [ ] **Step 11: Verify by hand**

Serve a backlog with at least four items, one of them discarded and one shipped:

```bash
B=/tmp/pb-batch-check.json
S=skills/new-product-backlog/scripts/backlog.py
python3 $S add $B --name "Alpha" --priority high
python3 $S add $B --name "Beta" --priority medium
python3 $S add $B --name "Gamma" --priority low
python3 $S add $B --name "Delta" --priority low
python3 $S edit $B BL-004 --status shipped
python3 $S discard $B BL-003
python3 $S serve $B
```

Open the printed URL and confirm:
1. A checkbox column sits between the priority rail and the `▸` chevron, with a select-all box in the header.
2. `Implement` sits left of `+ New item`, greyed out and unclickable with nothing selected.
3. Ticking two rows makes it read `Implement (2)`; clicking it flashes `Copied` and pasting gives exactly
   `Run the /master-backlog-executor skill for these backlog ids: BL-001, BL-002.` — ids in ascending numeric order regardless of tick order.
4. The discarded row's checkbox is greyed out and unclickable, with the tooltip `Discarded items can't be implemented`. The shipped row's checkbox **is** usable.
5. Select-all ticks every non-discarded visible row; unticking clears them. With one of three ticked, the header box shows the dash (indeterminate) state.
6. Search for `Alpha`, tick it, then search for `Beta` and tick that: the button reads `Implement (2)` and the copied prompt contains **both** ids even though only one is on screen.
7. Filter down to only the discarded row: the select-all box is disabled.
8. Expand a row's detail drawer, then tick a checkbox — the drawer stays open.
9. Reload the page: nothing is selected, but the search/filter/sort state is restored as before.

- [ ] **Step 12: Commit**

```bash
git add skills/new-product-backlog/templates/editor.html
git commit -m "feat(new-product-backlog): multi-select rows + batch Implement prompt"
```

---

### Task 4: Documentation and version bump

**Files:**
- Modify: `skills/new-product-backlog/SKILL.md` (the editor feature sentence, currently line 220; the "Execution prompts" section, currently lines 226–233)
- Modify: `.claude-plugin/plugin.json` (`version`, line 4)
- Modify: `.claude-plugin/marketplace.json` (`version` at line 8 and line 18)

**Interfaces:**
- Consumes: the shipped behavior of Tasks 1–3. Produces: nothing consumed by later tasks.

- [ ] **Step 1: Document the checkbox column in the editor feature sentence**

In `SKILL.md`, in the paragraph starting "The editor is a self-contained page", replace:

```
column sort, multi-select status/priority filter chips, and text search across id/name/description/notes.
```

with:

```
column sort, multi-select status/priority filter chips, text search across id/name/description/notes, and per-row checkboxes for batching several items into one execution prompt.
```

- [ ] **Step 2: Rewrite the "Execution prompts" section**

Replace the whole block from `**Execution prompts.**` through the sentence ending `…kick off that item's implementation.` with:

```markdown
**Execution prompts.** The editor never invokes Claude itself — it copies a ready-to-paste prompt to the clipboard, which you paste into a session:

| Where | Button | Copies |
|---|---|---|
| Expanded item, under the description | **Auto** | `Implement BL-NNN using pr-from-backlog.` |
| Expanded item, under the description | **Semi** | `Implement BL-NNN using semiauto-backlog-execution.` |
| Row `⋯` menu | **Groom** | `Run the /backlog-analyzer skill for BL-NNN. User's concern/feedback is: <your concern>.` |
| Header, next to `+ New item` | **Implement** | `Run the /master-backlog-executor skill for these backlog ids: BL-AAA, BL-BBB, BL-CCC.` |

`BL-NNN` is the item's own id. **Groom** opens a modal that captures what worries you about the entry — required, since the analyzer skill hard-gates on a concern — and copies the prompt when you confirm; if the browser blocks clipboard access, the modal stays open with the prompt shown so nothing you typed is lost. **Implement** batches whatever rows you tick in the checkbox column: it stays disabled until something is selected, shows the running count (`Implement (3)`), and lists the ids in ascending numeric order. Selections survive search/filter changes (so you can assemble a batch across several searches) but are not remembered across a page reload. Discarded rows can't be ticked, because `master-backlog-executor`'s pre-flight gate declines an entire batch that contains one.
```

- [ ] **Step 3: Bump the version in all three places**

```bash
sed -i '' 's/"version": "0.6.3"/"version": "0.7.0"/' .claude-plugin/plugin.json .claude-plugin/marketplace.json
grep -n '"version"' .claude-plugin/plugin.json .claude-plugin/marketplace.json
```

Expected output — three lines, all `0.7.0`:
```
.claude-plugin/plugin.json:4:  "version": "0.7.0",
.claude-plugin/marketplace.json:8:    "version": "0.7.0"
.claude-plugin/marketplace.json:18:      "version": "0.7.0",
```

- [ ] **Step 4: Verify the JSON is still valid and the suite still passes**

```bash
python3 -c 'import json;[json.load(open(p)) for p in [".claude-plugin/plugin.json",".claude-plugin/marketplace.json"]];print("json ok")'
node tests/editor_prompts.test.mjs && node tests/editor_filters.test.mjs
```

Expected: `json ok`, then both `all assertions passed` lines, exit 0.

- [ ] **Step 5: Commit**

```bash
git add skills/new-product-backlog/SKILL.md .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "docs(new-product-backlog): document Groom + batch Implement; bump to 0.7.0"
```

---

## Cross-check against the spec

| Spec requirement | Task |
|---|---|
| Groom in kebab, second entry | 2 (Step 2) |
| Groom modal: eyebrow, id, item name, required textarea, hint | 2 (Step 3) |
| OK disabled while concern blank; ⌘/Ctrl-Enter submits | 2 (Step 3) |
| Clipboard failure keeps the modal open with an inline error | 2 (Step 3) |
| Groom prompt text incl. no-doubled-terminator rule | 1 |
| Shared `modalState` with a `kind: "groom"` discriminator | 2 (Step 3) |
| Checkbox column between rail and chevron; `DETAIL_COLSPAN` +1 | 3 (Steps 5, 7, 3) |
| Select-all scoped to visible rows, with indeterminate state | 3 (Steps 5, 8) |
| Selection survives filtering; count in the button label | 3 (Steps 8, 11.6) |
| Discarded rows' checkbox disabled | 3 (Step 7) |
| Selection not persisted to `localStorage` | 3 (Step 3 — no `persistView` change; verified 11.9) |
| Ticking never re-renders the body | 3 (Step 8 `syncSelectionUI`; verified 11.8) |
| `pruneExpanded()` → `pruneStale()`, widened | 3 (Step 4) |
| Header button `.btn` not `.btn primary`, left of `+ New item` | 3 (Step 1) |
| Ids sorted ascending by numeric part | 1 (`sortBacklogIds`) |
| Copy flash reuses `.is-copied` / `.is-failed`, 1400ms | 3 (Steps 2, 8) |
| Selection retained after copy | 3 (Step 8) |
| Implement prompt text | 1 |
| Three sentinel-guarded helpers asserted in tests | 1 |
| `editor_filters.test.mjs` untouched | — (run as a regression gate in every task) |
| SKILL.md prompt table + editor feature sentence | 4 |
| Version 0.6.3 → 0.7.0 in plugin + marketplace | 4 |
| No server / CLI / schema change | — (no task touches `scripts/` or `schema/`) |
