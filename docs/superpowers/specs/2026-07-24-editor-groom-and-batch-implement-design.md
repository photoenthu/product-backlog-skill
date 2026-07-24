# Backlog editor: Groom action & batch Implement — Design

_Date: 2026-07-24 · Status: Approved_

## Problem

The `new-product-backlog` editor can already hand a *single* item to a *single*
implementation skill: each expanded row carries **Auto** / **Semi** buttons that
copy `Implement BL-NNN using pr-from-backlog.` (or `…semiauto-backlog-execution.`)
to the clipboard.

Two workflows the operator actually runs have no equivalent affordance, and both
require hand-typing a prompt with an exact skill name and id list:

1. **Grooming one doubtful entry.** The `backlog-analyzer` skill takes a
   `BL-NNN` *plus a free-text concern* and returns REFUTED / REVISE / RETIRE.
   Today the operator reads a stale-looking row in the editor, then leaves the
   editor to compose the invocation by hand — and the skill hard-gates on both
   inputs, so a half-typed prompt costs a round-trip of back-and-forth.
2. **Shipping a batch.** The `master-backlog-executor` skill takes a *list* of
   ids and runs each through `pr-from-backlog` in its own subagent. Assembling
   that list means eyeballing the table and transcribing ids by hand — exactly
   the kind of copying that produces a typo'd id, which the executor's
   pre-flight gate then rejects as a whole-batch decline.

This design adds both affordances to the editor: a per-item **Groom** action
that captures the concern in a modal, and **checkbox multi-select** feeding an
**Implement** button in the header.

## Scope

- **In scope:** a `Groom` entry in the row kebab menu and its concern-capture
  modal; a checkbox column with select-all; a header `Implement` button; the two
  new clipboard prompt strings; tests for the prompt contracts; SKILL.md docs;
  version bump.
- **Out of scope:** any server / CLI / schema change (both features are pure
  client-side clipboard work); actually *invoking* either skill from the editor
  (the editor only ever copies text — it never talks to Claude); persisting
  selection across page loads; grooming more than one item at a time; a
  per-item Groom button in the detail drawer (the kebab is the single home for
  item-scoped actions).

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Where Groom lives | **Kebab menu, second entry** (`Edit · Groom · Discard · ─── · Delete` — the existing divider stays put, fencing off the one irreversible action) | The kebab is already the home for item-scoped actions; the drawer's Auto/Semi row is for zero-input one-click prompts, and Groom needs input. |
| Empty concern | **Blocks submit** (primary button disabled until non-blank) | `backlog-analyzer` hard-gates on a concern and would just ask again — better to catch it in the modal than burn a round-trip. |
| Clipboard failure on Groom | **Keep the modal open, show inline error** | The typed concern is unrecoverable if the modal closes on a failed copy. |
| Trailing punctuation | **Skip the template's final `.` when the concern already ends in `.`/`?`/`!`** | Avoids `…is: it's stale..` — the only deviation from the literal template, and a cosmetic one. |
| Checkbox column position | **Between the priority rail and the disclosure chevron** | Standard leading-checkbox convention; the rail is a 3px non-interactive bar, so the checkbox is still the first control in the row. |
| Select-all scope | **Currently-visible (filtered) rows only** | A select-all that reached filtered-out rows would silently batch items the operator can't see. |
| Selection vs. filtering | **Selection survives filter/search changes**; button shows the count | Lets the operator search → tick → search again → tick to assemble a batch. The count (`Implement (3)`) keeps a hidden-but-selected item accounted for. |
| Discarded rows | **Checkbox disabled**, and an already-ticked item is dropped from the selection the moment it becomes discarded | `master-backlog-executor`'s pre-flight declines the *entire batch* if any id is discarded; one slipped-in id would waste a whole run. Disabling the checkbox alone is not enough — ticking an item and *then* discarding it would otherwise leave it in the batch while rendering as unticked, so `pruneStale()` evicts on discarded-status as well as on vanished-id. Shipped rows stay selectable — the gate merely skips them. |
| Selection persistence | **Not persisted to `localStorage`** | Filter/sort state is worth restoring; a stale batch from yesterday's session is a footgun. Row expansion is likewise not persisted. |
| Id order in the batch prompt | **Ascending by numeric part** | Board order, not click order — reproducible and diff-friendly. |
| `Implement` button emphasis | **`.btn`, not `.btn primary`** | `+ New item` keeps the single primary action in the header. |
| Selection after copy | **Retained** | Allows re-copying without re-ticking. |

## Prompt contracts

Both strings are a contract with the executing skills — a typo hands the
operator a prompt that triggers nothing. Each lives in a sentinel-delimited
block in `editor.html` and is asserted by `tests/editor_prompts.test.mjs`
(the mechanism `backlogPrompt` already uses).

**Groom** — `// <groomPrompt> … // </groomPrompt>`:

```
Run the /backlog-analyzer skill for BL-407. User's concern/feedback is: <concern>.
```

- `<concern>` is the textarea value trimmed of surrounding whitespace, with
  interior newlines preserved verbatim (a multi-line concern stays multi-line).
- The trailing `.` is appended unless the trimmed concern already ends in `.`,
  `?`, or `!`.

**Implement** — `// <implementPrompt> … // </implementPrompt>`:

```
Run the /master-backlog-executor skill for these backlog ids: BL-012, BL-107, BL-244.
```

- Ids are comma-space separated, sorted ascending by numeric part via a third
  sentinel-guarded helper, `sortBacklogIds(ids)`.
- A single-id selection produces the same sentence with one id — no special
  case, and `master-backlog-executor` handles a one-item list by design.

## Editor changes (`templates/editor.html`)

### State

`state` gains one field:

```js
selected: new Set(),   // ids ticked for the batch Implement prompt
```

`pruneExpanded()` is renamed `pruneStale()` and widened to evict ids dropped
from the backlog — hard-deleted elsewhere, or gone after a refresh — from both
`state.expanded` and `state.selected`. `restoreView()` /
`persistView()` are untouched: selection is deliberately not persisted.

### Table

- `COLUMNS` gains no entry — the checkbox is chrome, like the rail and the
  chevron — so `buildHead()` appends a third leading `<th class="select-col">`
  holding the select-all checkbox, and `renderRow()` appends a matching
  `<td class="select-cell">`. `DETAIL_COLSPAN` increments by one accordingly.
- Per-row checkbox: `aria-label` `Select BL-NNN for batch implement`, `checked`
  from `state.selected`, `disabled` for `status === "discarded"` with an
  explanatory `title`. `change` toggles membership and calls a light
  `syncSelectionUI()` (button label/disabled + header checkbox tri-state) —
  never a full `renderBody()`, so ticking a box can't scroll or collapse
  drawers.
- Select-all: `change` adds every *visible, non-discarded* id to
  `state.selected` (or removes every visible id when unticking), then
  re-renders the body once so all row checkboxes reflect it. Its
  `indeterminate` flag is set when the visible selectable set is partially
  selected.

### Header

```html
<button class="btn" id="implement-btn" disabled>Implement</button>
<button class="btn primary" id="new-btn">+ New item</button>
```

`syncSelectionUI()` sets `disabled` and the label (`Implement` → `Implement (3)`).
Click copies `implementPrompt(sortBacklogIds([...state.selected]))` and flashes
`Copied` / `Copy failed` via the existing `.is-copied` / `.is-failed` classes on
a 1400ms timer, matching the Auto/Semi buttons.

### Groom modal

`openRowMenu()` gains a `Groom` menu item calling `openGroomModal(item)`.

The modal reuses `.scrim` / `.modal` / `.modal-head` / `.modal-body` /
`.modal-foot` / `.modal-error` / `.field` unchanged, at `max-width: 520px`:

- Head: eyebrow `Groom item`, `<h2>` = the item id, and the item's **name** as
  read-only context beneath it.
- Body: a `<form>` with one required `<textarea>` (`min-height: 140px`), label
  `Your concern / feedback`, and a `.hint` reading *"What worries you about
  this entry — stale, already fixed, unclear value?"*. Autofocused.
- Foot: `Cancel` (ghost) + primary `Copy prompt`, the latter `disabled` while
  the trimmed value is empty (re-evaluated on `input`). `⌘/Ctrl-Enter` submits.
- Submit → `copyToClipboard(groomPrompt(id, concern))`. On success, close the
  modal. On failure, keep it open and render the inline `.modal-error` band.
- Esc and scrim-click close it. Since `closeModal()` keys off the shared
  `modalState`, the Groom modal sets `modalState` too (with a `kind: "groom"`
  discriminator) so the existing Escape handler and `#modal-root` teardown work
  unchanged, and Groom and Edit can never be open at once.

## Testing / verification

**`tests/editor_prompts.test.mjs`** (extended — same `eval`-the-sentinel-block
approach it already uses for `backlogPrompt`):

- `groomPrompt("BL-407", "it looks stale")` → exact expected sentence.
- Id substitution: a different id round-trips verbatim (incl. 4-digit ids).
- Whitespace: leading/trailing whitespace trimmed; interior newlines preserved.
- Punctuation: a concern ending `.` / `?` / `!` yields no doubled terminator; a
  concern ending in a word gets exactly one `.`.
- `implementPrompt(["BL-012","BL-107"])` → exact expected sentence; single-id
  case; ids comma-space joined.
- `sortBacklogIds(["BL-107","BL-12","BL-9"])` → `["BL-9","BL-12","BL-107"]`
  (numeric, not lexicographic).
- Both new prompts name exactly one skill and differ from `backlogPrompt`'s.

**`tests/editor_filters.test.mjs`**: untouched — `applyFilters` is unchanged.

**Manual check** (the DOM wiring the .mjs tests can't reach): serve a backlog,
confirm (a) Groom appears in the kebab and its modal blocks an empty concern;
(b) a discarded row's checkbox is disabled; (c) select-all ticks only visible
rows and goes indeterminate on a partial set; (d) a selection made under one
search term survives a new search and is still in the copied prompt; (e)
ticking a box does not collapse an open detail drawer.

## Documentation & versioning

- **`skills/new-product-backlog/SKILL.md`**, "The editor" → *Execution
  prompts*: add both new prompts to the table (Groom noted as taking a typed
  concern; Implement noted as batch/multi-select), and mention the checkbox
  column in the editor's feature sentence.
- **`.claude-plugin/plugin.json`** and **`.claude-plugin/marketplace.json`**:
  `0.6.3` → `0.7.0` — new user-facing capability, not a fix.

## Backward compatibility

No stored data changes shape: no schema field, no API route, no persisted-view
key. An existing `localStorage` view entry loads unchanged (selection was never
part of it). The editor is re-served from the template on every launch, so there
is no dashboard-style template-version regeneration step to trigger.
