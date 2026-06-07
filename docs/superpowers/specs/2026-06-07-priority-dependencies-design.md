# Priority & Dependencies for the product-backlog skill — Design

_Date: 2026-06-07 · Status: Approved_

## Problem

The `product-backlog` skill captures shippable units as atomic rows but records
nothing about **how urgent** an item is or **what blocks it**. A reader can see
what exists and its status (In-Progress / Pending / Shipped) but cannot tell, at
a glance, which Pending items matter most or which ones literally cannot be
started yet (because they depend on another row, an external event, or a date).

This design adds two pieces of judgment to each new Pending / In-Progress row:

1. A derived **priority** — `Critical | High | Medium | Low`.
2. Derived **dependency facts** — a blocking backlog row, a gating event, and/or
   an earliest-start date.

Both surface in `product-backlog.md` and in the HTML dashboard.

## Scope

- **In scope:** priority derivation + display; dependency derivation + display;
  markdown format; dashboard rendering; SKILL.md guidance.
- **Out of scope:** retroactively assigning priority/dependencies to existing
  rows; priority for Shipped rows (moot once done); auto-recomputing priority on
  every update; a new table column; changes to the helper script's schema.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Where the data lives | **Inside the Feature cell** | Matches "below the title"; no schema change; the 7-cell parser and helper stay untouched; fully backward-compatible. |
| Dashboard priority display | **Colored pill badge** | Reuses the existing status-badge design language; far more scannable than bold text. |
| Priority scope | **Pending / In-Progress only** | Priority informs sequencing; it carries no signal on an already-Shipped row. |
| Default priority | **Medium** | Safe fallback when signals are mixed, consistent with the skill's "default to lower-confidence" ethos. |

## Markdown format

The Feature cell carries the title, the priority, and the (optional) dependency
bullets in a single cell, `<br>`-separated:

```
<Title> **(<Priority>)**<br>• Dependency on BL-NNN<br>• Cannot Start Before: YYYY-MM-DD ET<br>• Reason for dependency: <note>
```

Rules:

- `<Priority>` is exactly one of `Critical`, `High`, `Medium`, `Low`, rendered
  bold in parentheses, appended after the title with a single leading space.
- Each of the three dependency bullets is **independently optional**. Emit only
  the ones that apply. An item with no dependency is just
  `<Title> **(<Priority>)**` with no bullets.
- The bullet character is a literal `•` followed by a space.
- Bullet labels are fixed strings: `Dependency on `, `Cannot Start Before: `,
  `Reason for dependency: `.
- `Reason for dependency` is one freeform sentence; it may explain a BL
  dependency, a gating event, or both. Any literal `|` inside it is escaped as
  `\|` per the existing markdown-escaping rule.
- `Cannot Start Before` is date-granularity: `YYYY-MM-DD ET`.
- Priority is set when the row is created. It is not auto-recomputed on later
  updates, but may be revised if the user explicitly asks; a revision touches
  `Last updated (ET)`.

### Worked example

```
| BL-014 | Regime-Router v2 **(High)**<br>• Dependency on BL-007<br>• Cannot Start Before: 2026-07-01 ET<br>• Reason for dependency: needs the shared auth module from BL-007 and a post-soak flag flip | Second-gen router… | 2026-06-07 11:00 ET | 2026-06-07 11:00 ET |  |  |
```

## Priority derivation rubric (SKILL.md guidance)

The skill derives priority by **judgment**, guided by:

- **Critical** — blocks shipping or users right now; a correctness, security, or
  data-loss risk; or other in-progress work is stuck on it.
- **High** — clear near-term value, or unblocks multiple other items; expected
  to be tackled this cycle.
- **Medium** — worth doing, no particular urgency. The default when signals are
  mixed or weak.
- **Low** — nice-to-have, speculative, or explicitly deferred ("punt to next
  quarter", "revisit later").

The derived priority is shown in the step-6 confirmation diff so the user can
override before anything is written.

## Dependency derivation (SKILL.md guidance)

When adding a new Pending / In-Progress row, the skill checks for:

- **BL dependency** — does this require another existing backlog row to ship
  first? If so → `Dependency on BL-NNN`. Cross-check the referenced ID exists
  via the helper's `list-ids`.
- **Gating event** — is it blocked on a soak window, an external launch, an
  approval, an upstream release, etc.? Capture it in `Reason for dependency`.
- **Earliest start date** — is there a derivable "not before" date? →
  `Cannot Start Before: YYYY-MM-DD ET`, using the `now-et` helper's clock as the
  reference for relative phrasing ("not before next month").

If a dependency is plausible but ambiguous, it becomes a step-5 clarifying
question rather than a guess. If none apply, no bullets are written.

## HTML dashboard changes (`templates/product-backlog.html`)

Version comment bumped `3` → `4` so `regenerate-html-if-stale` propagates the
update to existing users' dashboards on next skill run.

1. **Parse the Feature cell** in `renderRows()`: split the cell on `<br>`.
   Segment 0 is the title; any subsequent segments beginning with `•` are
   dependency bullets.
2. **Extract priority** from the title segment with a regex
   `/\*\*\((Critical|High|Medium|Low)\)\*\*/i`; strip the matched span from the
   displayed title text.
3. **Render the priority pill** next to the title using a new `.priority` badge
   class with per-level modifiers (`.priority.critical|high|medium|low`) and new
   `--priority-*` / `--priority-*-bg` CSS variables defined for both light and
   dark schemes:
   - Critical = red, High = orange/amber, Medium = blue, Low = gray.
4. **Render dependency bullets** as a new `.dependencies` block inside the card
   (grid-column 2, small muted type like `.meta`), one bullet per line.
5. **Add `**bold**` support to `renderInline()`** (currently absent) so any bold
   in titles/summaries/notes renders correctly — applied after the
   link/code placeholder extraction, before the `<br>` substitution.

No change to the `cells.length >= 7` parser rule, the section structure, the
helper script, or any existing row.

## Backward compatibility

- Old rows with no priority/dependencies parse unchanged — the regex simply
  finds no priority and there are no `•` segments, so the card renders exactly as
  before.
- The markdown remains a valid 7-column GFM table; GitHub renders the `<br>` and
  `•` bullets natively in the Feature cell.
- **Parser leniency:** `parseFeatureCell` treats *every* non-empty post-`<br>`
  segment as a dependency (stripping a leading `•` if present), rather than
  requiring the `•` marker. This is harmless for skill-generated rows (which
  always emit `•`) and more robust to hand edits.
- **Multi-line legacy titles:** if any pre-existing row used `<br>` inside its
  Feature cell to wrap a title, the second line now renders inside the dependency
  block rather than the title. The text is relocated, not lost. The skill has
  never produced multi-line Feature titles, so this is a theoretical edge only.

## Testing / verification

- Add a sample Pending row with priority + all three bullets to a scratch
  backlog file; open the dashboard and confirm: pill color correct, title clean
  (no `**`), bullets rendered as a distinct block.
- Add a sample row with priority but **no** bullets; confirm no empty block.
- Confirm an old-style row (no priority) still renders.
- Confirm `regenerate-html-if-stale` reports `regenerated` against a v3 file and
  `unchanged` against a fresh v4 file.
- Confirm the markdown table still parses (7 cells; `<br>`/`•` stay inside the
  Feature cell).
```
