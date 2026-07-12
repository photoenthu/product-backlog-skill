# product-backlog-skill

A Claude Code skill that maintains a per-project **Product Backlog** in `docs/backlog/product-backlog.md` — plus a self-contained HTML dashboard for browsing it — by analyzing each Claude session for shipped, in-progress, and pending work.

The point: when you finish a session — or check in mid-session — you say "update the backlog" and the skill reconciles what you actually did against what's tracked. It looks at git commits, plans, PRDs, opportunities-marked-DONE, and the conversation itself, then adds or updates rows in a single status-grouped markdown table. After writing, it offers to commit and push both files to git. No external tooling, no SaaS, no per-project setup beyond invoking the skill once.

## What it produces

A single file per project at `docs/backlog/product-backlog.md`, structured as three sections:

```markdown
# Product Backlog

## In-Progress

| ID | Feature | Summary | Created (ET) | Last updated (ET) | Artifacts | Notes |
|---|---|---|---|---|---|---|
| BL-009 | vwap_reclaim_long Phase 2.1 | Adds VWAP-reclaim long entries with 35% min win-rate gate. Replaces the open-only entry path on bull-trend days. | 2026-04-28 14:10 ET | 2026-05-02 09:45 ET | [plan](docs/superpowers/plans/2026-04-28-vwap-reclaim.md) \| `597718d` | Awaiting 10-trade soak; revert if expectancy ≤ 0. |

## Pending

| ID | Feature | Summary | Created (ET) | Last updated (ET) | Artifacts | Notes |
|---|---|---|---|---|---|---|

## Shipped

| ID | Feature | Summary | Created (ET) | Last updated (ET) | Artifacts | Notes |
|---|---|---|---|---|---|---|
```

Design choices that the skill enforces, and why:

- **Atomic rows** — one shippable unit per row, not one initiative. PRD with 8 items = 8 rows. Easier to reason about; never edited after shipping.
- **Update-in-place** — a row is identified by a stable `BL-NNN` id. Status flips by moving the row between sections; the row's identity, summary, and creation date never change.
- **Immutable summaries** — once written, the 2-3 line description doesn't change. If the framing of work shifts, you add a follow-up row instead. The table doubles as a historical record.
- **Append-only artifacts** — plan/PRD/PR/commit links accumulate over the row's lifetime; older entries are never replaced.
- **Status is the section** — no `Status` column. Two sources of truth would drift; section position is unambiguous.
- **ET timestamps** — every project, regardless of where it runs, uses `America/New_York` so a multi-machine workflow stays consistent.

## When the skill triggers

Phrases that should invoke it:

- `/product-backlog`
- "update the backlog"
- "log this to the backlog"
- "add to product backlog"
- "track this for later"
- At the end of a productive session: "log progress" / "update product backlog"

What it does, in order:

1. Resolves `<git-root>/docs/backlog/product-backlog.md` (creates it if missing).
2. Parses existing rows by section.
3. Examines four signal sources for candidates:
   - **Authoritative** — commits to `main`, ✅ DONE marks added in `docs/opportunities-for-improvement.md`, PRDs moved to `docs/processed/`.
   - **Suggestive** — plans in `docs/superpowers/plans/`, PRDs in `docs/prds/`, uncommitted modifications.
   - **Conversational** — what the user actually said in the session.
4. Matches each candidate against existing rows by ID → artifact link → fuzzy title.
5. Decides each row's new status, never demoting `Shipped`, defaulting to lower confidence on ties.
6. **Asks clarifying questions** when an inference is ambiguous, one question at a time.
7. Shows a brief proposed-changes summary and waits for confirmation.
8. Writes targeted edits (never a full file overwrite) and verifies the table is well-formed.
9. Ensures `docs/backlog/product-backlog.html` is in sync — written on first run, re-copied only when the bundled template's version is bumped.
10. Asks whether to commit and push both files. Stages by explicit path so unrelated dirty files in your working tree are left alone.

## HTML dashboard

Alongside the markdown, the skill bootstraps a single-file HTML dashboard at `docs/backlog/product-backlog.html`. Open it in any modern browser, click **Open file…**, point it at your `product-backlog.md`, and you get:

- Three sections (In-Progress / Pending / Shipped) matching the markdown.
- Count badges (e.g. `2 In-Progress · 3 Pending · 7 Shipped · 12 Total`).
- A single search box that filters across id, title, summary, notes, and artifacts.
- Clickable artifact links and inline commit hashes.
- Light/dark mode that follows your OS setting.
- Zero CDN dependencies — fully offline.

In Chrome / Edge / Brave / Arc / any Chromium-based browser, the dashboard remembers your file via the [File System Access API](https://developer.mozilla.org/en-US/docs/Web/API/File_System_Access_API) (the handle is stored in IndexedDB). Reload the page and it renders immediately — the only time you'll re-pick is if you explicitly click **Change file**. Firefox and Safari don't support persistent file handles, so they fall back to a one-shot file picker each visit; the dashboard still works, just without the "remember me" affordance.

The HTML is **never bundled with data**. It always reads the live markdown from your machine, which means:

- The dashboard never goes stale.
- The skill doesn't regenerate it on every run — only when the bundled template's version changes (a `<!-- product-backlog-dashboard-version: N -->` comment near the top of the file gates this).
- You can edit the markdown manually between Claude sessions and the dashboard reflects the change on the next refresh.

## Commit-and-push prompt

After writing the markdown (and regenerating the HTML if needed), the skill asks:

> Commit and push `docs/backlog/product-backlog.md` (and `product-backlog.html` if it was created/regenerated) to git? **(yes / skip)**

`yes` stages **only** the backlog files (explicit `git add <path>`, never `-A` or `.`), commits with a one-line message describing the row-level changes, and pushes. `skip` leaves the files modified in the working tree for you to handle later.

## Install

### As a Claude Code plugin (recommended)

```
/plugin marketplace add photoenthu/product-backlog-skill
/plugin install product-backlog@product-backlog-skill
```

### As a user-level skill (no plugin system)

```
git clone https://github.com/photoenthu/product-backlog-skill.git ~/.claude/skills-src/product-backlog-skill
ln -s ~/.claude/skills-src/product-backlog-skill/skills/product-backlog ~/.claude/skills/product-backlog
```

The skill is self-contained — Python 3.9+ stdlib, no third-party dependencies.

## Usage

In any project where you want a backlog, just invoke the skill. It will:

1. Create `docs/backlog/product-backlog.md` on first run.
2. Analyze the current session.
3. Propose updates and ask before writing.

That's it. There's no configuration to do.

## Anti-patterns the skill won't fall into

- Trusting conversational claims of "shipped" without a corresponding commit/file change.
- Rewriting historical summaries to match the current framing.
- Auto-archiving shipped rows (the file is meant to be a single source of truth).
- Writing `Status` into a column (section *is* status).
- Generating new IDs by row-counting (the helper script handles deleted/skipped IDs).

---

# new-product-backlog (JSON-backed)

A second, independent skill bundled in this same plugin: `skills/new-product-backlog/`. Where `product-backlog` (above) keeps a markdown table plus a read-only HTML dashboard, `new-product-backlog` keeps a **strict, schema-validated JSON file**, mutated **only** through a pure-stdlib Python CLI, with a live localhost HTML **editor** (not just a viewer) for manual add/edit/filter/search. Both skills can coexist in the same project — they use different file extensions (`.json` vs `.md`) and different trigger names, so pick the one that matches what you ask for.

It produces `<project>/docs/backlog/product-backlog.json`, and it runs the same kind of session-analysis workflow as the original skill (git commits, plans/PRDs, opportunities marked DONE, conversational signals) — see `skills/new-product-backlog/SKILL.md` for the full checklist.

## Why JSON instead of markdown

- **Machine-validated on every write.** Every mutation is schema-checked (shape, enums, id/date patterns) *and* checked for referential integrity (unique ids, dependencies that exist, no self-deps, no cycles) before anything touches disk. An invalid write is rejected and the file is left untouched.
- **Python is the only writer.** The CLI and the local editor server both funnel every mutation through the same `core.py` functions, which write atomically (temp file + `os.replace`). Never hand-edit the JSON with `sed`, a text editor, or the Read/Edit/Write tools — that bypasses the validator and can leave the file structurally broken.
- **A live editor, not just a static dashboard.** `backlog.py serve` starts a `127.0.0.1`-only HTTP server that backs a self-contained HTML page with add/edit, discard/hard-delete, sort, multi-select filters, and search — every action round-trips through the same validating `core` functions, so the browser can't produce an invalid file any more than the CLI can.

## Schema

Every item in `items` is an object with all fields present (required fields carry an empty value rather than being omitted):

| Field | Type | Rules |
|---|---|---|
| `id` | string | `^BL-\d{3,}$`, e.g. `BL-001`. Stable, never reused. |
| `name` | string | Short title. Non-empty. |
| `description` | string | Longer prose. Editable. May be empty. |
| `status` | enum | `new` \| `pending` \| `shipped` \| `discarded`. |
| `priority` | enum | `critical` \| `high` \| `medium` \| `low`. |
| `dependencies` | string[] | Existing `BL-NNN` ids. No self-reference; graph must stay acyclic. |
| `doNotBuildBefore` | string \| null | `YYYY-MM-DD` (a valid calendar date) or `null`. |
| `artifacts` | object[] | `{ "label": string, "url": string }`, both non-empty. |
| `notes` | string | Freeform: discard reason, deferral rationale, blockers. May be empty. |
| `createdAt` | string | ISO-8601 with an ET offset. Set once on `add`. |
| `updatedAt` | string | ISO-8601 with an ET offset. Touched on every mutation. |

The full JSON Schema (draft 2020-12) lives at `skills/new-product-backlog/schema/product-backlog.schema.json`.

## CLI reference

All commands: `python3 skills/new-product-backlog/scripts/backlog.py <cmd> ...`. Subcommands: `init`, `add`, `edit`, `discard`, `rm`, `get`, `list`, `validate`, `next-id`, `now`, `serve`.

```bash
# Create the file if missing (idempotent) — also makes docs/backlog/ if needed.
python3 skills/new-product-backlog/scripts/backlog.py init docs/backlog/product-backlog.json

# Add an item. --name is required; everything else is optional.
# Defaults: status=new, priority=medium, empty deps/artifacts/notes, doNotBuildBefore=null.
python3 skills/new-product-backlog/scripts/backlog.py add docs/backlog/product-backlog.json \
  --name "Scanner universe expansion" --description "Widen the intraday scan set" \
  --status pending --priority high --depends BL-001,BL-002 --dnbb 2026-09-01 \
  --notes "Blocked on the router landing first" \
  --artifact "plan=docs/superpowers/plans/2026-07-11-scanner.md"

# Edit only the passed fields; bumps updatedAt. Same flags as add, plus --clear-dnbb.
python3 skills/new-product-backlog/scripts/backlog.py edit docs/backlog/product-backlog.json BL-001 --status shipped --artifact "commit=e1d3bfb"

# Discard (soft delete — sets status=discarded, kept for history).
python3 skills/new-product-backlog/scripts/backlog.py discard docs/backlog/product-backlog.json BL-005 --notes "Superseded by BL-009"

# Hard-delete. Refuses if other items depend on it, unless --force.
python3 skills/new-product-backlog/scripts/backlog.py rm docs/backlog/product-backlog.json BL-007 --force

# Print one item, or a filtered array of items, as JSON.
python3 skills/new-product-backlog/scripts/backlog.py get docs/backlog/product-backlog.json BL-001
python3 skills/new-product-backlog/scripts/backlog.py list docs/backlog/product-backlog.json --status pending --priority high

# Full schema + referential-integrity check. Prints "ok: <path>" and exits 0 if clean.
python3 skills/new-product-backlog/scripts/backlog.py validate docs/backlog/product-backlog.json

# Print the next free id (max + 1, never reuses), or the current ISO-8601 ET timestamp.
python3 skills/new-product-backlog/scripts/backlog.py next-id docs/backlog/product-backlog.json
python3 skills/new-product-backlog/scripts/backlog.py now
```

`--status` and `--priority` are validated by argparse against the enums, so a typo like `--status done` fails fast with a usage error before any file is touched.

### Newer commands: `find`, `default-path`, `--json`, `--version`

- **`add` auto-initializes.** Calling `add` on a path whose file/dirs don't exist yet now bootstraps the store first (creates `docs/backlog/` and the JSON file), then adds the item — no separate `init` call required. `init` still exists and stays idempotent for consumers that prefer to bootstrap explicitly. `edit`/`discard`/`rm`/`get`/`list`/`validate` still require an existing file and exit 1 if it's missing.
- **`--json`** on `add`/`edit`/`discard`/`rm` prints the affected item as JSON instead of the human-readable string (`rm --json` prints `{"removed": "<id>"}`); omitting it keeps the original plain-text output.
- **`find <path> [--name-contains STR] [--status S] [--priority P] [--artifact-url STR] [--depends-on BL-NNN]`** prints items matching *all* given filters (AND-composed) as a JSON array — always JSON, no `--json` flag needed. Use it to check whether an item already exists before deciding to `add` or `edit`.
- **`default-path [--root DIR]`** prints the canonical backlog path for the current project (`<root|git-root|cwd>/docs/backlog/product-backlog.json`), so scripts never have to hardcode the location.
- **`--version`** (top-level flag) prints the CLI's own interface version, e.g. `new-product-backlog 1.0`.

These are what make the skill callable as a subprocess from *other* skills (in this project or a different one) — see [`skills/new-product-backlog/SKILL.md`](skills/new-product-backlog/SKILL.md#integration-calling-this-skill-from-other-skills) for the full integration contract and a copy-pasteable add-or-update example.

## The editor

```bash
python3 skills/new-product-backlog/scripts/backlog.py serve docs/backlog/product-backlog.json
# then open http://127.0.0.1:8765/  (Ctrl-C to stop; override the starting port with --port N)
```

If the requested port is busy, `serve` scans upward to the next free port automatically and prints the URL it actually bound to.

The server binds `127.0.0.1` only — no auth, single local user, not reachable from the network. The page itself is a self-contained HTML file (inline CSS/JS, no CDN, theme-aware) that lists all items and supports add/edit, delete (discard by default, hard-delete as an explicit option), column sort, multi-select status/priority filter chips, and text search across id/name/description/notes. Rows expand to show the full description, notes, and artifact links, and it warns when a dependency isn't yet `shipped`, or when `doNotBuildBefore` is in the future. Filter/sort/search state persists across refreshes (per-backlog).

Artifact links: full `http(s)://` URLs open externally; in-repo paths (e.g. `docs/plans/foo.md`) are served from the project root via a traversal-safe `/file` route so they open in the browser. The path may be repo-root-relative, backlog-dir-relative, or absolute — whichever resolves inside the project root wins; escapes are refused.

**Markdown artifacts (`.md`) render as formatted, read-only HTML** — headings, bold/italic, code, lists, blockquotes, tables, links — via the bundled pure-stdlib `mdview.py`. The original file is never modified. Raw HTML in the markdown is escaped (an embedded `<script>` shows as text, never runs) and link hrefs are sanitized; other HTML/SVG artifacts are still served as inert `text/plain`.

## How it differs from `product-backlog`

| | `product-backlog` | `new-product-backlog` |
|---|---|---|
| Storage | `docs/backlog/product-backlog.md`, markdown table | `docs/backlog/product-backlog.json`, schema-validated |
| Status model | Section position (In-Progress / Pending / Shipped) | `status` enum field (`new`/`pending`/`shipped`/`discarded`) |
| Priority | Not tracked | `priority` enum field, required |
| Dependencies | Not tracked | `dependencies`, referential-integrity checked, cycle-free |
| Writer | Direct markdown edits (targeted, never full overwrite) | Python CLI / server only — never hand-edited |
| Browsing UI | Read-only HTML dashboard (file picker) | Live localhost HTML **editor** (add/edit/delete/filter/search) |
| Discard semantics | No discard state; rows just don't move | Explicit `discarded` status, kept for history |

## Repo layout

```
product-backlog-skill/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── skills/
│   ├── product-backlog/
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   │   └── backlog_helper.py
│   │   └── templates/
│   │       └── product-backlog.html      # the dashboard template
│   └── new-product-backlog/
│       ├── SKILL.md
│       ├── schema/
│       │   └── product-backlog.schema.json
│       ├── scripts/
│       │   ├── core.py                   # data model, validation, mutations
│       │   ├── backlog.py                # CLI (init/add/edit/discard/rm/get/list/validate/next-id/now/serve)
│       │   └── server.py                 # localhost HTTP API backing the editor
│       └── templates/
│           └── editor.html               # the live editor
├── LICENSE
└── README.md
```

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Issues and PRs welcome. The skill is intentionally small; if you'd like to extend it (per-quarter file rotation, owner column, integration with Linear/Jira/etc.), please open an issue first to discuss the shape of the change.
