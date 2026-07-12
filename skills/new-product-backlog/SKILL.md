---
name: new-product-backlog
description: Maintain a per-project product backlog in a strict, schema-validated JSON file at `<project>/docs/backlog/product-backlog.json`, mutated ONLY through the bundled Python CLI and browsable/editable via a live localhost HTML editor. Trigger on `/new-product-backlog`, "add to the new backlog", "log this to the JSON backlog", "update the JSON backlog", "track this in the new backlog", or at the end of a session that shipped/planned features when the user says "log progress" or "update the backlog" and wants the JSON-backed store. Analyzes the current Claude session — git commits made, plans/PRDs written, opportunities marked DONE, things the user said about future work — and adds/updates items whose status flips over time (new → pending → shipped, or discarded) with stable BL-NNN ids, referential-integrity-checked dependencies, and append-only artifact links. Use this even when the user just says "remember to ship X next week" or "track this initiative" since those are pending-backlog signals. DISAMBIGUATION: this is the JSON-backed sibling of the older `product-backlog` skill (which keeps a markdown table + read-only HTML dashboard). Prefer THIS skill when the user names JSON, the schema, the strict validator, or the live editor; prefer the old one when they name the markdown table or the `.md` file. Every write is schema- and integrity-checked and atomic because Python is the sole writer — never hand-edit the JSON. Do not invoke for one-off notes or todos that aren't shippable features.
---

# New Product Backlog (JSON-backed)

Maintain a per-project product backlog as a **strict, schema-validated JSON file**. Each item is one shippable unit (a feature, a fix, a planned initiative, a deferred follow-up). Items carry a `status` that flips over time — `new` → `pending` → `shipped`, or `discarded` — without ever being silently dropped.

This is the JSON-backed sibling of the older `product-backlog` skill. Where the old skill keeps a markdown table plus a read-only HTML dashboard, this one keeps a machine-readable JSON file governed by a bundled JSON Schema, mutated **only** through a pure-stdlib Python CLI, with a live localhost HTML **editor** (not just a viewer) for manual add/edit/filter/search. Both skills can coexist in the same project — they use different file extensions (`.json` vs `.md`) and different trigger names.

The skill is invoked at the end of (or part-way through) a session to capture what was shipped, what's queued, and what's slated for later. It resolves the file, examines the current session for shipped/pending/new signals, asks clarifying questions when an inference is ambiguous, shows the user a proposed diff, and — on confirmation — writes back **exclusively through the CLI**.

## File location

`<project>/docs/backlog/product-backlog.json` in whatever project you're working in.

- `<project>` is the git toplevel. Resolve it with `git rev-parse --show-toplevel`; fall back to the cwd if that fails (not a git repo). The cwd is the project root even when the user invokes from a subdirectory.
- If the file doesn't exist, create it with the CLI's `init` subcommand (see below). `init` is idempotent — it writes the canonical empty file `{ "schemaVersion": 1, "items": [] }` only if the file is missing, and creates `docs/backlog/` if needed.

## The one rule

**The JSON file is mutated ONLY through `scripts/backlog.py`.** Never edit it with the Read/Edit/Write tools, never hand-write or hand-patch JSON, never `sed` it. Every change — add, edit, discard, remove — goes through the CLI (or the editor server, which calls the same code).

This is not a style preference; it's what keeps the file always-valid. Each write flows through one choke point in `core.py` that: loads the current JSON, applies the mutation in memory, runs the **full** validation (schema shape + enums + id/date patterns + referential integrity), and only then writes — to a temp file in the same directory, followed by an atomic `os.replace` onto the target. If validation fails, **nothing is written** and the command exits non-zero with a clear message. Hand-editing bypasses that choke point and can leave the file structurally broken, with a dangling dependency, or with a cycle — exactly the failure modes the schema exists to prevent.

## Schema summary

Every item is an object with all of these fields present (the schema requires them all; "optional" fields carry an empty value rather than being absent, so consumers never handle missing keys):

| Field | Type | Rules |
|---|---|---|
| `id` | string | `^BL-\d{3,}$`, zero-padded to ≥3 digits (e.g. `BL-001`). Stable, never reused. |
| `name` | string | Short title. Non-empty. |
| `description` | string | Longer prose. **Editable** (unlike the old skill's immutable Summary). May be empty. |
| `status` | enum | `new` \| `pending` \| `shipped` \| `discarded`. |
| `priority` | enum | `critical` \| `high` \| `medium` \| `low`. Required on every item, including shipped/discarded (they simply retain their last value). |
| `dependencies` | string[] | Array of existing `BL-NNN` ids. May be empty. Must reference real ids; no self-reference; the graph must stay acyclic. |
| `doNotBuildBefore` | string \| null | `YYYY-MM-DD` (a valid calendar date) or `null`. A "don't start before" gate. |
| `artifacts` | object[] | Array of `{ "label": string, "url": string }` (both non-empty). Plans, PRs, commit refs. Append-only in spirit. |
| `notes` | string | Freeform escape valve: discard reason, deferral/soak rationale for `doNotBuildBefore`, blockers. May be empty. |
| `createdAt` | string | ISO-8601 with ET offset. Set once by the script on `add`. |
| `updatedAt` | string | ISO-8601 with ET offset. Touched by the script on every mutation. |

**Status semantics:**

- `new` — captured, not yet triaged/prioritized.
- `pending` — triaged, prioritized, queued to build.
- `shipped` — merged/done.
- `discarded` — decided won't-do; **kept for history, not deleted.**

**Referential integrity** (enforced on every write and by `validate`): ids are unique; every id in `dependencies` references an existing item; no item depends on itself; the dependency graph is acyclic; `doNotBuildBefore`, when non-null, parses as a real calendar date. A write that would violate any of these is rejected and the file is left untouched.

## CLI reference

All commands take the form `python3 <skill-dir>/scripts/backlog.py <cmd> ...`, where `<skill-dir>` is this skill's directory (the one containing this `SKILL.md`). `<path>` is the backlog JSON file (`docs/backlog/product-backlog.json`). Every example below matches the real argparse in `scripts/backlog.py`.

```bash
# Create the file if missing (idempotent). Exits 0 whether it created or already existed.
python3 <skill-dir>/scripts/backlog.py init docs/backlog/product-backlog.json

# Add an item. --name is required; everything else is optional.
# Defaults: status=new, priority=medium, empty deps/artifacts/notes, doNotBuildBefore=null.
# Prints the new id (e.g. BL-001).
python3 <skill-dir>/scripts/backlog.py add docs/backlog/product-backlog.json --name "Regime-Router v1"

# Add with the full field set. --depends is comma-separated ids; --dnbb is YYYY-MM-DD;
# --artifact is label=url and is repeatable.
python3 <skill-dir>/scripts/backlog.py add docs/backlog/product-backlog.json \
  --name "Scanner universe expansion" --description "Widen the intraday scan set" \
  --status pending --priority high --depends BL-001,BL-002 --dnbb 2026-09-01 \
  --notes "Blocked on the router landing first" \
  --artifact "plan=docs/superpowers/plans/2026-07-11-scanner.md" --artifact "PR #42=https://github.com/org/repo/pull/42"

# Edit only the passed fields on an existing item; bumps updatedAt. Same flags as add,
# plus --clear-dnbb to set doNotBuildBefore back to null.
python3 <skill-dir>/scripts/backlog.py edit docs/backlog/product-backlog.json BL-001 --status shipped --artifact "commit=e1d3bfb"
python3 <skill-dir>/scripts/backlog.py edit docs/backlog/product-backlog.json BL-002 --clear-dnbb

# Discard (soft delete — sets status=discarded, kept for history). Optional --notes reason.
python3 <skill-dir>/scripts/backlog.py discard docs/backlog/product-backlog.json BL-005 --notes "Superseded by BL-009"

# Hard-delete. Refuses if other items depend on it, unless --force (which also strips
# the id from every dependent's dependencies so the file stays valid).
python3 <skill-dir>/scripts/backlog.py rm docs/backlog/product-backlog.json BL-007
python3 <skill-dir>/scripts/backlog.py rm docs/backlog/product-backlog.json BL-007 --force

# Print one item as JSON.
python3 <skill-dir>/scripts/backlog.py get docs/backlog/product-backlog.json BL-001

# Print items as a JSON array, optionally filtered by status and/or priority.
python3 <skill-dir>/scripts/backlog.py list docs/backlog/product-backlog.json --status pending --priority high

# Query for matching items (JSON array). Filters AND together; all optional:
#   --name-contains (case-insensitive substring), --status, --priority,
#   --artifact-url (substring of any artifact url), --depends-on BL-NNN.
python3 <skill-dir>/scripts/backlog.py find docs/backlog/product-backlog.json --name-contains "router" --status pending

# Print the conventional backlog path for a repo: <root|git-root|cwd>/docs/backlog/product-backlog.json
python3 <skill-dir>/scripts/backlog.py default-path            # uses the current git root
python3 <skill-dir>/scripts/backlog.py default-path --root /path/to/project

# Full schema + referential-integrity check. Prints "ok: <path>" and exits 0 if clean;
# prints problems to stderr and exits 1 otherwise.
python3 <skill-dir>/scripts/backlog.py validate docs/backlog/product-backlog.json

# Print the next free id (max + 1, never reuses). Use this instead of eyeballing.
python3 <skill-dir>/scripts/backlog.py next-id docs/backlog/product-backlog.json

# Print the current ISO-8601 ET timestamp. Takes no path.
python3 <skill-dir>/scripts/backlog.py now

# Launch the localhost editor (see "The editor" below). Default --port 8765.
python3 <skill-dir>/scripts/backlog.py serve docs/backlog/product-backlog.json --port 8765
```

`--status` and `--priority` are validated by argparse against the enums, so a typo like `--status done` fails fast with a usage error before any file is touched.

Two conveniences aimed at scripted/other-skill callers (see "Integration" below): **`add` auto-creates** the file and `docs/backlog/` directories if they don't exist, so the first `add` bootstraps the store; and `add`/`edit`/`discard`/`rm` accept **`--json`** to print the affected item as JSON (`rm --json` prints `{"removed": "<id>"}`) instead of the human string. `backlog.py --version` prints the CLI version.

## Session-analysis workflow

Run this checklist in order when the skill is invoked. The order matters — each step feeds the next.

### 1. Resolve the path and initialize

```bash
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
BACKLOG="$ROOT/docs/backlog/product-backlog.json"
python3 "<skill-dir>/scripts/backlog.py" init "$BACKLOG"
```

Then read the current state with `list` (or `get` per id) — do **not** open the file with the Read tool for parsing decisions if you can query it through the CLI, and never open it to edit. This is your **before** state.

### 2. Gather candidates from the session

A "candidate" is anything in the session that could become an item or matches an existing one. Look at all sources — they're complementary:

**Authoritative signals** (these set status definitively):
- **Git commits since each existing item's `createdAt`.** `git log --since="<createdAt>" --pretty=format:"%h %s"` — a commit whose subject references the item's `name`, its plan/PRD artifact path, or the same code area means the item is `shipped` and the commit hash should be appended to `artifacts`.
- **PRDs / opportunities marked done** during the session → the matching item is `shipped`.

**Suggestive signals** (used when no authoritative signal applies):
- **A plan exists in `docs/superpowers/plans/` but no commits reference it** → `pending`.
- **A PRD with unchecked boxes** → one `pending` item per unchecked line (checked-off items flip to `shipped`).

**Conversational signals** (seed new items, write `notes`, capture intent):
- **What the user said** — "we should also do X next week", "Y is blocked on Z, defer for now" become `new`/`pending` items or augment an existing item's `notes`. The conversation is rich but lossy; use it only when no file-based signal exists, or to augment what file signals already established.

### 3. Match candidates to existing items

For each candidate, decide update-vs-insert. Match in this priority order — stop at the first hit:

1. **Explicit id** — the plan/PRD/commit mentions a `BL-NNN`. Trust it.
2. **Artifact-url match** — the candidate's plan path / PR URL exactly matches an entry in some item's `artifacts`. Trust it.
3. **Fuzzy title** — the candidate's title is substantially the same as an existing item's `name`, ignoring case, articles, and trailing punctuation. *Verify with the user* if there's any ambiguity.
4. **No match** — insert as a new item with a fresh id (`next-id`).

### 4. Decide the new status

- **Once `shipped`, never demoted.** If an item is `shipped` and a new signal says otherwise, it's likely a follow-up that needs its own item.
- **Authoritative beats suggestive beats conversational.** A commit hash beats a written plan beats a verbal "we'll do this."
- **Default to the lower-confidence status when unsure.** Commit → `shipped`; plan-only → `pending`; conversation → `new` or `pending`. Don't claim shipped without proof.

### 5. Ask clarifying questions when inference is non-definitive

Ask **one question at a time** — the user should be able to answer in a single line. Concrete cases that warrant a question: ambiguous title match, status uncertainty (plan exists but no commits — pending, or in-progress on a branch?), multi-part shipping (close all unchecked PRD items or only some?), cross-session re-evaluation (leave pending, or discard?). If the user gives a non-answer like "you decide," fall back to the lower-confidence status and record the reasoning in `notes`.

Don't ask about the obvious: a commit that plainly implements a plan the user already closed out → just flip to `shipped`. A new plan with no commits → just add a `pending` item; the file is the proof.

### 6. Show the proposed diff and confirm

Before writing, print a **brief, scannable** summary — bullets, not a wall of text:

```
Proposed updates to docs/backlog/product-backlog.json:
  • BL-007 "Regime-Router v1": pending → shipped (commit e1d3bfb appended)
  • BL-009 "vwap_reclaim Phase 2.1": pending → shipped (commits 597718d, aa27a4a appended)
  • BL-012 (new) "Dashboard Observability v3": pending, medium — plan only, no commits yet
  • BL-013 (new) "Scanner universe expansion": pending, high — depends on BL-007

Confirm to write? (yes / edit)
```

Only proceed on confirmation. If the user says "edit," let them course-correct before anything is written.

### 7. Write — exclusively through the CLI

Apply each confirmed change with **one CLI invocation per change**. Never hand-edit the JSON.

```bash
python3 "<skill-dir>/scripts/backlog.py" edit "$BACKLOG" BL-007 --status shipped --artifact "commit=e1d3bfb"
python3 "<skill-dir>/scripts/backlog.py" add  "$BACKLOG" --name "Scanner universe expansion" --status pending --priority high --depends BL-007
python3 "<skill-dir>/scripts/backlog.py" discard "$BACKLOG" BL-005 --notes "Superseded by BL-009"
```

Each command self-validates and refuses to write anything invalid, so a bad `--depends` or a would-be cycle fails that single command without corrupting the file. Add new items **before** the items that depend on them (a dependency id must already exist when referenced).

### 8. Validate and report

Run the full check as a final gate:

```bash
python3 "<skill-dir>/scripts/backlog.py" validate "$BACKLOG"
```

It must print `ok: <path>` and exit 0 before you claim success. If it reports problems, fix them through the CLI and re-run — never repair by editing the file. Then end with a one-line summary, e.g. `Updated docs/backlog/product-backlog.json: 2 shipped, 2 new pending. Validated ok.` Don't restate the full diff — the user already saw it in step 6.

## The editor

For manual editing — add/edit/filter/search outside a session-analysis run — launch the bundled localhost editor:

```bash
python3 <skill-dir>/scripts/backlog.py serve docs/backlog/product-backlog.json
# then open http://127.0.0.1:8765/  (Ctrl-C to stop; override with --port N)
```

The editor is a self-contained page (inline CSS/JS, no CDN, theme-aware) that lists all items and supports add/edit, delete (discard by default, hard-delete as an explicit option), column sort, multi-select status/priority filter chips, and text search across id/name/description/notes. It also surfaces warnings when a dependency isn't yet `shipped` or when `doNotBuildBefore` is in the future.

Critically, the browser **never writes to disk**: every mutation POSTs/PATCHes/DELETEs to the local server, which routes through the same validating `core` functions the CLI uses and returns the authoritative backlog for the page to re-render. So the editor is a **safe manual path** — it can't produce an invalid file any more than the CLI can. The server binds **127.0.0.1 only** (no auth, single local user, not reachable from the network).

One deliberate asymmetry with the CLI: the editor's **hard-delete always forces** (like `rm --force`). Deleting an item that others depend on will succeed and strip that id from every dependent's `dependencies` list — it never refuses the way `rm` does without `--force`. Discard (the default action) is the non-destructive choice; reach for hard-delete only when you mean it.

## Integration: calling this skill from other skills

Other skills can drive this backlog too — not just the session-analysis workflow above. A `pr-from-backlog` skill that marks an item shipped when its PR merges, an `add-to-backlog` skill invoked from a completely different project (a trading bot, a web app, anything), or any other automation can mutate `product-backlog.json` by shelling out to `scripts/backlog.py`. This section is the contract for that.

**The contract: subprocess only, never direct file access.** Exactly like the session-analysis workflow, a consuming skill must never read or write the JSON with its own Read/Edit/Write tools, `sed`, or hand-rolled JSON parsing-and-rewriting. It calls `scripts/backlog.py` as a subprocess and treats stdout/exit code as the interface. This is the same sole-writer guarantee (schema validation, referential integrity, atomic writes) — it just now extends across skill and project boundaries instead of being scoped to one session.

**Locating the file: always resolved in the consuming project.** There is no shared or central backlog — every project gets its own `docs/backlog/product-backlog.json` under its own git root. Use the `default-path` subcommand instead of hardcoding `docs/backlog/product-backlog.json` or guessing at a root:

```bash
python3 <skill-dir>/scripts/backlog.py default-path
# -> <git-root-of-cwd>/docs/backlog/product-backlog.json

python3 <skill-dir>/scripts/backlog.py default-path --root /path/to/some/project
# -> /path/to/some/project/docs/backlog/product-backlog.json
```

`default-path` resolves `--root` if given, else `git rev-parse --show-toplevel` run from the current working directory, else `cwd` — the identical resolution rule the session-analysis workflow uses by hand in step 1. Run it from (or point `--root` at) whatever project the consuming skill is actually working in; that's what keeps each project's backlog isolated from every other project's.

**Bootstrapping: `add` self-initializes.** As of this version, `add` creates `docs/backlog/` and the JSON file (if missing) before adding the item — a consumer can call `add` directly on a brand-new project with no separate init step. `init` still exists and stays idempotent (a no-op if the file already exists) for consumers that prefer to bootstrap explicitly or want to create an empty file up front. `edit`, `discard`, `rm`, `get`, `list`, and `validate` still require the file to already exist and fail (exit 1) if it doesn't.

**Machine-readable I/O.** Every command a script needs is scriptable without screen-scraping prose:

- `add` prints the new item's id on stdout (e.g. `BL-014`); pass `--json` to print the full item object instead.
- `edit`, `discard`, and `rm` print a short human string by default (`edited BL-014`, `discarded BL-005`, `removed BL-007`); pass `--json` on any of them to get the affected item as JSON instead (`rm --json` prints `{"removed": "BL-007"}`, since the item no longer exists to echo back).
- `get`, `list`, and `find` always print JSON — a single item object for `get`, an array for `list`/`find`.
- `find <path> [--name-contains STR] [--status S] [--priority P] [--artifact-url STR] [--depends-on BL-NNN]` returns items matching **all** of the given filters (AND-composed; omitted filters are ignored) as a JSON array — this is the query a consumer uses to check "does an item like this already exist" before deciding whether to `add` or `edit`.
- Exit codes are consistent everywhere: `0` success, `1` a `BacklogError` (validation failure, referential-integrity violation, file not found), `2` a usage error (bad flags, missing required argument) — a consumer can branch on `$?` without parsing stderr.
- `--version` (top-level flag) prints `new-product-backlog 1.0` — the CLI's own interface version, independent of the plugin/marketplace version — for a consumer that wants to guard against calling flags that don't exist yet in an older install.

A concrete add-or-update flow, e.g. a `pr-from-backlog`-style skill that upserts an item by title:

```bash
BL="python3 /path/to/new-product-backlog/scripts/backlog.py"
BACKLOG="$($BL default-path)"                 # resolves to THIS project's root

# add-or-update: find by title, else add
EXISTING=$($BL find "$BACKLOG" --name-contains "Regime router" | python3 -c 'import json,sys;m=json.load(sys.stdin);print(m[0]["id"] if m else "")')
if [ -n "$EXISTING" ]; then
  $BL edit "$BACKLOG" "$EXISTING" --status shipped --json
else
  $BL add "$BACKLOG" --name "Regime router" --priority high --json
fi
```

**Locating the script.** `scripts/backlog.py` lives inside this skill's own install directory — wherever it was installed (a plugin cache path or a checked-out copy of this repo), not inside the consuming project. A consuming skill's instructions should tell the agent to resolve that path itself (the agent generally knows where its skills are installed) rather than this document guessing a path that only holds for one install layout.

**CLI only — not `serve`.** `serve` starts an interactive localhost editor for a human to browse and click through; it is not meant to be driven by automation. Other skills and scripts should always call the `backlog.py` subcommands above directly, never spin up (or talk HTTP to) the `serve` server.

## Commit prompt

After all writes are done, surface this **once** at the end:

> Commit and push `docs/backlog/product-backlog.json` to git? **(yes / skip)**

- **yes** — Stage **only** the backlog file by explicit path (never `git add .` or `git add -A`, even if other files are dirty), then commit and push:
  ```bash
  git add docs/backlog/product-backlog.json
  git commit -m "chore(backlog): mark BL-007 shipped, add BL-013"
  git push
  ```
  The message is one concise line describing the item-level changes. **Do not** include an AI-attribution footer — these are routine bookkeeping commits.
- **skip** — leave the file modified in the working tree; don't stash, don't stage.

If unrelated files are dirty, that's fine — staging by explicit path won't pull them in; don't warn about them. If the cwd isn't a git repo, skip the prompt with a one-line note.

## Anti-patterns to avoid

- **Don't hand-edit the JSON.** No Read/Edit/Write, no `sed`, no hand-written JSON. Every change goes through `backlog.py` (or the editor server, which is the same code).
- **Don't bypass the CLI to "just fix one field."** A one-character manual edit can drop a required field or dangle a dependency and defeat the whole always-valid guarantee. Use `edit`.
- **Don't invent dependencies.** Only add a `BL-NNN` to `dependencies` when that id actually exists and the blocking relationship is real. Add depended-on items first. If unsure, ask rather than guess — the validator will reject a phantom id anyway.
- **Don't demote a `shipped` item.** Once shipped, it stays shipped; a later "still in progress" signal means a follow-up item, not a status flip backward.
- **Don't create cycles.** If A depends on B, B (transitively) can't depend on A. The validator rejects it; don't try to force it through the editor either.
- **Don't `git add .` or `git add -A`.** Stage `docs/backlog/product-backlog.json` by explicit path. Other dirty files aren't the skill's concern.
- **Don't auto-commit without asking.** The commit/push prompt is mandatory each time, even if the user said "yes, push" earlier about something else.
- **Don't invoke this skill for one-off todos.** A backlog item is a *shippable unit*, not a chore. "Fix the docstring on `foo()`" is not an item; "Refactor the foo subsystem" is.
- **Don't reach for this skill when the user means the markdown one.** If they name the markdown table or the `.md` file, that's the older `product-backlog` skill. This skill owns the JSON file, the strict schema, and the live editor.
