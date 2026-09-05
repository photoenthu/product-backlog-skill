# Backlog editor: Hide Embargo filter — Design

_Date: 2026-09-05 · Status: Approved_

## Problem

The `new-product-backlog` editor surfaces two independent readiness signals on
every row, both computed by `warningsFor()`:

- **Blocked** — some dependency is missing or not yet `shipped`.
- **Embargo** — `doNotBuildBefore` is a date in the future ("don't start before").

Only the first has a filter. The toolbar's `Hide Blocked` checkbox strips
dependency-blocked rows from the table, so an operator scanning for "what can I
pick up right now" can clear that class of noise in one click. Date-gated items
have no equivalent: an item deliberately parked until next quarter keeps
occupying a table row, and the only way to skip past it is to read the badge on
every row by eye.

The two signals answer different questions and are cleared by different events —
a dependency shipping versus a calendar date passing — so the operator needs to
suppress them independently. This design adds a `Hide Embargo` toggle beside
`Hide Blocked`.

## Scope

- **In scope:** a `Hide Embargo` checkbox toggle in the toolbar; the embargo
  predicate inside `applyFilters()`; state, persistence, reset and boot-sync
  plumbing mirroring `hideBlocked`; tests in `tests/editor_filters.test.mjs`;
  SKILL.md + README doc updates; plugin version bump.
- **Out of scope:** any server, CLI, or schema change (this is pure client-side
  view filtering); changing the Embargo *badge* rule; changing the "N on hold"
  readout; a combined "hide anything on hold" control; persisting or clearing
  row selection when rows are hidden.

## Filter rule

An item is embargoed when `doNotBuildBefore` is set **and strictly greater than
today's date string**:

```js
item.doNotBuildBefore && item.doNotBuildBefore > today
```

This is the exact predicate `warningsFor()` already uses for the Embargo badge,
so `Hide Embargo` hides precisely the rows that carry an Embargo badge — one
rule, no drift between filter and badge.

Consequences, each of which is a test case:

- `doNotBuildBefore: null` (or absent) is never embargoed.
- A **past** date is never embargoed — the gate has expired.
- A date equal to **today** is *not* embargoed. The item is startable today, so
  it stays visible. This is the boundary case, decided deliberately.

Dates are ISO `YYYY-MM-DD` strings, validated on every write by `core.py`, so
lexicographic `>` is a correct chronological comparison and no date parsing is
needed.

## Where "today" comes from

`applyFilters()` is delimited by `// <applyFilters>` … `// </applyFilters>`
sentinels because `tests/editor_filters.test.mjs` extracts that block by regex
and `eval`s it **in isolation**. The extracted function therefore cannot call
`todayStr()`, which is defined further down `editor.html` and is outside the
sentinels.

So the reference date is an input: `applyFilters()` reads `opts.today`, and
computes today internally only as a fallback when the caller omits it.
`renderBody()` passes `todayStr()` explicitly. This keeps the function pure and
makes the today-boundary case directly assertable without mocking the clock.

## Ordering inside applyFilters

Blockedness needs a pre-pass — it is resolved against the **full** input list
(via a `statusById` map built before filtering) so that a dependency hidden by
the status or search filter still blocks its dependents.

Embargo needs no such thing: it is a per-item property with no cross-item
lookup. The check goes inline in the existing `items.filter` pass, immediately
after the `hideBlocked` check, and adds no second traversal.

Both toggles compose as AND with each other and with the status, priority, and
search filters. Both on = the intersection: neither blocked nor embargoed.

## State plumbing

`hideEmbargo` mirrors `hideBlocked` at every one of its touchpoints in
`skills/new-product-backlog/templates/editor.html`:

| Location | Change |
|---|---|
| Toolbar markup | a second `<label class="toggle" for="hide-embargo">` inside the same `.filter-group` as `hide-blocked` |
| `state` object | `hideEmbargo: false`, with a comment stating the rule |
| `renderBody()` | pass `hideEmbargo: state.hideEmbargo` and `today: todayStr()` into `applyFilters` |
| `clearFilters()` | reset the flag and uncheck the box |
| `persistView()` | include `hideEmbargo` in the localStorage payload |
| `restoreView()` | accept it only when `typeof === "boolean"` |
| `boot()` | reflect restored state into the checkbox; add a `change` listener |

The `change` listener does `persistView(); renderBody(); syncSelectionUI()` —
the same three calls as `hide-blocked`. `syncSelectionUI()` is required because
hiding rows invalidates the select-all checkbox's tri-state.

Persistence is keyed by backlog file path (`npb:view:<path>`) and every
read/write is already guarded against private-mode and quota failures; the new
field inherits that. A stored view written before this change simply has no
`hideEmbargo` key, and `restoreView()`'s type guard leaves the default `false`.

## Deliberately unchanged

- **The "N on hold" readout** still counts against the full item list. It is a
  statistic about the backlog, not about the current view, so filtering rows out
  of the table must not change it. This matches how `Hide Blocked` behaves today.
- **Row selection** is untouched when rows are hidden — ids stay in
  `state.selected` and a hidden-but-selected item still contributes to the batch
  Implement prompt. Identical to `Hide Blocked`; changing it is a separate
  question about both toggles, not this one.
- **The Embargo badge rule** in `warningsFor()` is the source of truth the filter
  copies; it is not modified.

## Testing

TDD in `tests/editor_filters.test.mjs`, which already exercises `applyFilters`
as a pure function over literal item arrays. New assertions, using dates fixed
relative to a hard-coded `today` passed via `opts`:

1. Default (absent and explicit `false`) keeps every item — unchecked is a no-op.
2. Checked drops only future-dated items.
3. `null` / absent `doNotBuildBefore` survives.
4. A past date survives.
5. A date **equal to today** survives — the boundary.
6. Composes with `hideBlocked`: both on yields the intersection, and an item
   that is embargoed but not blocked is dropped only by the embargo toggle.
7. Composes with the status filter and with search.
8. Omitting `opts.today` falls back to the real current date without throwing.

## Docs & version

- `SKILL.md` editor paragraph: extend the feature list to name both hide toggles.
- `README.md` editor section: same.
- `.claude-plugin/plugin.json`: bump `0.8.0` → `0.9.0`.
