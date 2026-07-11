# Design: `new-product-backlog` skill

**Date:** 2026-07-11
**Status:** Approved (brainstorming complete)

## Summary

A new sibling skill, `new-product-backlog`, that maintains a per-project product
backlog in a **strict, schema-validated JSON file** instead of the markdown table
used by the existing `product-backlog` skill. The two skills coexist in the same
repo (different file extensions, different trigger names).

The design keeps the existing skill's core intelligence — analyzing the current
Claude session (git commits, plans/PRDs, conversational signals) to add/update
items and flip statuses — but changes three things:

1. **Storage** is a structured JSON file governed by a bundled JSON Schema.
2. **The Python CLI is the only writer.** Nothing else touches the file directly.
3. **A live HTML editor** (not just a read-only dashboard) supports add / edit /
   delete, plus sort, multi-field filter, and text search. It persists through a
   local Python server so that Python remains the sole writer.

## Motivation

Markdown tables are lossy and fragile — the existing skill needed a structural
validator to guard against GFM separator drift, and every field is stringly-typed.
A JSON file with a strict schema makes the backlog machine-readable, removes the
whole class of table-formatting bugs, and enables a real editing UI. Structured
data also makes referential integrity (dependencies must reference real ids, no
cycles) enforceable rather than aspirational.

## Non-goals

- Not replacing or deprecating the existing `product-backlog` skill. Both ship.
- No multi-user / concurrent-write support. Single local user, single writer.
- No estimate/story-point or labels fields in v1 (YAGNI; can add later — the
  `schemaVersion` field exists to make additive migration clean).
- No cloud sync, auth, or hosted server. The `serve` command is localhost-only.

## Data model

### File location

`<project>/docs/backlog/product-backlog.json`

- `<project>` is the git toplevel (`git rev-parse --show-toplevel`) or cwd.
- Distinct extension from the old skill's `product-backlog.md`, so a project may
  hold both without collision.

### File shape

Top-level object (not a bare array) so the schema can evolve:

```json
{
  "schemaVersion": 1,
  "items": [ /* item objects, see below */ ]
}
```

### Item schema

Governed by `schema/product-backlog.schema.json` (JSON Schema draft 2020-12),
bundled with the skill. Every write is validated against it before it lands.

| Field | Type | Required | Rules |
|---|---|---|---|
| `id` | string | yes | `^BL-\d{3,}$`, zero-padded to ≥3 digits. Stable, never reused. |
| `name` | string | yes | Short title. Non-empty. |
| `description` | string | yes | Longer prose. **Editable** (unlike the old skill's immutable Summary). May be empty string. |
| `status` | enum | yes | `new` \| `pending` \| `shipped` \| `discarded` |
| `priority` | enum | yes | `critical` \| `high` \| `medium` \| `low` |
| `dependencies` | string[] | yes | Array of existing `BL-NNN` ids. May be empty. No self-reference. No cycles. |
| `doNotBuildBefore` | string \| null | yes | `YYYY-MM-DD` (a valid calendar date) or `null`. |
| `artifacts` | object[] | yes | Array of `{ "label": string, "url": string }`. May be empty. |
| `notes` | string | yes | Freeform escape valve — discard reason, deferral/soak rationale for `doNotBuildBefore`, blockers. May be empty. |
| `createdAt` | string | yes | ISO-8601 with ET offset. Set once by the script on `add`. |
| `updatedAt` | string | yes | ISO-8601 with ET offset. Touched by the script on every mutation. |

All fields are present on every item (required in the schema); "optional" fields
carry an empty value (`""`, `[]`, or `null`) rather than being absent. This keeps
the editor and consumers from having to handle missing keys.

### Status semantics

- `new` — captured, not yet triaged/prioritized.
- `pending` — triaged, prioritized, queued to build.
- `shipped` — merged/done.
- `discarded` — decided won't-do; **kept for history, not deleted.**

Session analysis maps: authoritative signals (commits implementing the item) →
`shipped`; a plan exists but no commits → `pending`; conversational intent →
`new` or `pending`. As in the old skill, prefer the lower-confidence status when
unsure, and don't demote a `shipped` item.

### Priority semantics

Priority is required on every item (including `shipped`/`discarded`, which simply
retain their last value). This differs from the old skill (which omitted priority
on shipped rows) but is simpler for a strict schema and for editor sorting.

### Referential integrity (enforced on every write and by `validate`)

1. Every id in `dependencies` must reference an existing item's `id`.
2. No item may depend on itself.
3. The dependency graph must be acyclic (reject writes that would create a cycle).
4. `id` values are unique across the file.
5. `doNotBuildBefore`, when non-null, must parse as a real calendar date.

## Components

### 1. JSON Schema — `schema/product-backlog.schema.json`

The single source of truth for field shape. Draft 2020-12. **No third-party
dependencies** — the CLI performs the structural + enum + referential-integrity
checks in pure Python (mirroring the schema's constraints). The schema file
serves two purposes: authoritative documentation of the shape, and the source
the editor fetches (`GET /api/schema`) to build its form (enums → dropdowns,
etc.). If the schema and the Python checks ever drift, a test asserts they agree
on enum values and required fields.

### 2. Python CLI — `scripts/backlog.py` (the only writer)

Pure stdlib, Python 3.9+ (`zoneinfo`). Subcommands:

| Command | Purpose |
|---|---|
| `init <path>` | Create `{ "schemaVersion": 1, "items": [] }` if missing (idempotent). |
| `add <path> --name ... [--description ... --status ... --priority ... --depends BL-001,BL-002 --dnbb YYYY-MM-DD --notes ... --artifact label=url ...]` | Assign next id, set timestamps, default `status=new` / `priority=medium`, validate, atomic-write. Print the new id. |
| `edit <path> <id> [--name ... --description ... --status ... --priority ... --depends ... --dnbb ... --notes ... --add-artifact label=url --clear-dnbb]` | Mutate only the passed fields, bump `updatedAt`, validate, atomic-write. |
| `discard <path> <id> [--notes ...]` | Set `status=discarded` (soft delete, preferred). |
| `rm <path> <id>` | Hard-delete the item. Refuses if other items depend on it (or `--force`). |
| `get <path> <id>` | Print one item as JSON. |
| `list <path> [--status ... --priority ...]` | Print filtered items as JSON. |
| `validate <path>` | Run full schema + referential-integrity check. Exit non-zero on failure. |
| `next-id <path>` | Print next free `BL-NNN` (`max + 1`, never reuses). |
| `now` | Print current ISO-8601 ET timestamp. |
| `serve <path> [--port N]` | Launch the local editor server (see below). |

**Write discipline (all mutating commands):** load JSON → apply mutation in
memory → run full validation → write to a temp file in the same dir → `os.replace`
onto the target (atomic). If validation fails, nothing is written and the command
exits non-zero with a clear message. This is the single choke point through which
every change flows.

### 3. Local server — `backlog.py serve`

A stdlib `http.server` bound to `127.0.0.1` that:

- Serves the self-contained editor HTML at `/`.
- Exposes a small JSON API:
  - `GET  /api/backlog` → the whole file.
  - `GET  /api/schema` → the JSON Schema (for the editor's dynamic form).
  - `POST /api/items` → add (body = new item fields).
  - `PATCH /api/items/<id>` → edit.
  - `DELETE /api/items/<id>?mode=discard|hard` → discard (default) or hard-delete.
- Every mutating endpoint calls the **same** `add` / `edit` / `discard` / `rm`
  functions used by the CLI → validate → atomic write. The browser never writes
  to disk; it only sends intent over HTTP. Python is the sole writer.
- Returns the updated backlog (or a validation error with a 4xx + message) so the
  editor can re-render from authoritative server state after each change.
- localhost-only, no auth (single local user). Prints the URL to open.

### 4. HTML editor — `templates/editor.html`

Self-contained (inline CSS + JS, no CDN, works offline once served). Built with
the **frontend-design** skill for a distinctive, highly usable look; theme-aware
(light/dark via `prefers-color-scheme`). Features:

- **List/table view** of all items with id, name, status, priority,
  doNotBuildBefore, dependencies, updatedAt.
- **Add / edit** via a modal form driven by the fetched schema (enum fields
  render as dropdowns; dependencies as a multi-select of existing ids; date
  picker for `doNotBuildBefore`).
- **Delete** → discard (soft) by default, with an explicit hard-delete option.
- **Sort** by any column (id, name, status, priority, doNotBuildBefore, updatedAt).
- **Filter** — multi-select chips for status (new/pending/shipped/discarded) and
  priority (critical/high/medium/low); compose with search.
- **Text search** across id / name / description / notes.
- **Dependency awareness** — surface a warning when an item's dependency is not
  yet `shipped`, or when `doNotBuildBefore` is in the future.
- All mutations POST/PATCH/DELETE to the local server; the editor re-renders from
  the server's returned state (never trusts its own optimistic copy as canonical).

### 5. `SKILL.md` — session-analysis workflow

Ports the existing skill's analyze → match → propose-diff → confirm → write loop:

1. Resolve file path; `init` if missing; load and parse the JSON.
2. Identify candidates from the session (git commits, plans in
   `docs/superpowers/plans/`, PRDs, conversational signals).
3. Match candidates to existing items by explicit id → artifact url → fuzzy title.
4. Decide new status per the mapping above.
5. Ask one clarifying question at a time when inference is non-definitive.
6. Show a brief, scannable proposed diff; get confirmation.
7. **Write exclusively through `backlog.py`** (`add` / `edit` / `discard`) —
   never edit the JSON file directly, never hand-write JSON.
8. Run `backlog.py validate` and report.
9. Mention the editor (`backlog.py serve`) as the manual-editing path.
10. Offer to commit + push `docs/backlog/product-backlog.json` (stage by explicit
    path; ask before committing; no AI-attribution footer for routine updates).

The SKILL.md description must disambiguate from the old skill: JSON-backed, strict
schema, live editor, Python-only writes.

## Packaging

- New directory: `skills/new-product-backlog/` containing `SKILL.md`,
  `scripts/backlog.py`, `schema/product-backlog.schema.json`,
  `templates/editor.html`.
- Skills in this plugin are auto-discovered from the `skills/` directory, so
  simply adding `skills/new-product-backlog/` makes the skill available — no
  change to `.claude-plugin/plugin.json` or `marketplace.json` is required for
  discovery. The plan will bump the plugin/marketplace `version` and refresh the
  descriptions to mention both skills.
- Trigger: `/new-product-backlog` and equivalent natural-language phrases.

## Testing

- **Unit tests** for `backlog.py`: id assignment (never reuses), add/edit/discard/
  rm round-trips, schema validation rejects bad enums / bad dates / missing
  required fields, referential integrity rejects unknown deps / self-deps / cycles,
  atomic write leaves the file intact on validation failure.
- **Server tests**: each API endpoint routes through the validating writer;
  malformed bodies return 4xx and do not mutate the file.
- Follow the repo's existing test style (there is a `tests/` dir with a
  `.test.mjs`; Python tests can live alongside as `tests/backlog_test.py` or
  similar — decided in the plan).

## Key decisions (resolved during brainstorming)

- **Write path for the editor:** local Python server (not direct browser writes,
  not copy-paste CLI generation). Keeps Python the sole writer while giving live
  editing.
- **Extra fields beyond the required set:** timestamps (`createdAt`/`updatedAt`)
  and `artifacts`; plus `notes` (confirmed keep). No estimate or labels in v1.
- **ID scheme:** `BL-NNN`, same as the old skill.
- **Session analysis:** kept in full (ported from the old skill), all writes
  routed through the CLI.
