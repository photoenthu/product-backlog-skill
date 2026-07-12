---
name: product-backlog
description: Maintain a per-project Product Backlog table in `<project>/docs/backlog/product-backlog.md` plus an accompanying `product-backlog.html` dashboard. Trigger on `/product-backlog`, "update the backlog", "log this to the backlog", "add to product backlog", "track this for later", or at the end of a session that shipped/planned features when the user says "log progress" or "update product backlog". Analyzes the current Claude session — git commits made, plans/PRDs written, opportunities marked DONE, things the user said about future work — and adds/updates rows in a status-grouped markdown table (In-Progress → Pending → Shipped). Use this even when the user just says "remember to ship X next week" or "track this initiative" since those are pending-backlog signals. Each row is atomic (one shippable unit), updated in-place across sessions, with stable BL-NNN ids, immutable summaries, and append-only artifact links. After updating, ensures the HTML dashboard is in sync (only regenerated when the template version bumps) and asks whether to commit + push the backlog files. Do not invoke for one-off notes or todos that aren't shippable features.
---

# Product Backlog

Maintain a status-grouped Product Backlog as a markdown table. Each row is one shippable unit (a feature, a fix, a planned initiative, a deferred follow-up). Rows live in one of three sections — `## In-Progress`, `## Pending`, `## Shipped` — and flip status over time without being deleted.

The skill is invoked at the end of (or part-way through) a session to capture what was shipped, what's in-progress, and what's slated for later. It reads the existing file, examines the current session for shipped/pending/in-progress signals, asks clarifying questions when an inference is ambiguous, shows the user the proposed changes, and writes back on confirmation.

## File location

`<cwd>/docs/backlog/product-backlog.md` in whatever project you're working in.

- If `docs/` doesn't exist, create it.
- If `docs/backlog/` doesn't exist, create it.
- If `product-backlog.md` doesn't exist, create it from the template (run the helper script `scripts/backlog_helper.py init <path>` — it writes the canonical template only if the file is missing, so it's idempotent).
- The cwd is the project root, even if the user is invoking from a subdirectory. If `git rev-parse --show-toplevel` succeeds, prefer its output as the root; fall back to the cwd otherwise.

## File shape (canonical template)

```markdown
# Product Backlog

_Maintained by the `product-backlog` skill. Each row is one shippable unit. Rows flip status over time but are not deleted from the file._

## In-Progress

| ID | Feature | Summary | Created (ET) | Last updated (ET) | Artifacts | Notes |
|---|---|---|---|---|---|---|

## Pending

| ID | Feature | Summary | Created (ET) | Last updated (ET) | Artifacts | Notes |
|---|---|---|---|---|---|---|

## Shipped

| ID | Feature | Summary | Created (ET) | Last updated (ET) | Artifacts | Notes |
|---|---|---|---|---|---|---|
```

A row lives in **exactly one** section. The section header *is* the status — there is no `Status` column. Newest rows go at the **top** of their section, so the most recent activity is what a reader sees first.

## Column rules

| Column | Rule |
|---|---|
| **ID** | `BL-NNN`, zero-padded to 3 digits. Stable, never reused. Identifies the row across status transitions. Compute the next ID with `python3 <skill-dir>/scripts/backlog_helper.py next-id <path-to-backlog>` — this scans the whole file and returns `max + 1`. Always use the helper; do not eyeball the next ID. |
| **Feature** | Short title, ideally <60 chars. Reads like a PR title or ticket name. Avoid trailing periods. For new Pending/In-Progress rows, append the derived priority as `**(Critical\|High\|Medium\|Low)**` and any dependency bullets — see "Priority & dependencies" below. |
| **Summary** | 2-3 lines describing what it is and why it matters. **Immutable once written.** If the framing of the work later shifts materially, prefer adding a new follow-up row over rewriting history — the table is partly a historical record. |
| **Created (ET)** | `YYYY-MM-DD HH:MM ET`. Set once when the row is added. Get the current timestamp with `python3 <skill-dir>/scripts/backlog_helper.py now-et`. Always use this helper; do not infer the timezone from `date` or shell vars, since both can mislead on a non-ET machine. |
| **Last updated (ET)** | Same format. Touched whenever any field on the row changes (status, artifacts, notes). |
| **Artifacts** | Pipe-separated markdown links, e.g. `[plan](docs/superpowers/plans/2026-04-27-foo.md) \| [PR #42](https://github.com/...) \| `e1d3bfb``. Use **relative paths** for in-repo files, **full URLs** for PRs/issues, and **inline backticks** for commit hashes. **Append-only**: when new artifacts surface for an existing row, add them to the end; never replace existing entries. |
| **Notes** | Freeform prose. The escape valve for everything else: blockers, deferred reasons, follow-up tasks the user mentioned, gotchas. Append-friendly — prefer "X done; Y still owed" over "Y still owed" so the narrative is preserved. |

### Markdown table escaping

The `\|` literal pipe is required inside any cell that contains pipes (the "Artifacts" column will commonly need this). The pipe in the column separator is a real `|`; the pipe inside content is `\|`. If a cell contains a newline, replace it with `<br>`. If a cell contains a backtick, fence it with double-backticks `` `` `` to avoid breaking the table.

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

## When the skill is invoked

Run this checklist in order. Don't skip steps; the order matters because each step's output feeds the next.

### 1. Resolve the file path and load existing state

```bash
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
BACKLOG="$ROOT/docs/backlog/product-backlog.md"
SKILL_DIR="$(dirname "$0")"  # or the absolute path the harness gives you
python3 "$SKILL_DIR/scripts/backlog_helper.py" init "$BACKLOG"
```

Then read the file with the Read tool. Parse it into three lists of rows (`in_progress`, `pending`, `shipped`), keyed by ID. This is the **before** state.

### 2. Identify candidate items from the session

A "candidate" is anything in the session that could become a row, or that matches an existing row's identity. Look at all four signal sources below — they're complementary, not exclusive:

**Authoritative signals** (these set Status definitively):

1. **Git commits since each existing row's `Created` timestamp.** Run `git log --since="<created>" --pretty=format:"%h %s" -- <maybe-narrowed-path>` and look for commits whose subject references the row's Feature title, the row's plan/PRD path, or the same area of the codebase. A matching commit means the row should be `Shipped` and the commit hash should be appended to Artifacts.
2. **`✅ DONE YYYY-MM-DD` marks added to `docs/opportunities-for-improvement.md` during the session** → the corresponding row is `Shipped`. Match the line to a row by feature title or by the linked spec/commit.
3. **PRD files moved to `docs/processed/` during the session** → all rows tied to that PRD are `Shipped`.

**Suggestive signals** (used when no authoritative signal applies):

4. **A plan exists in `docs/superpowers/plans/` but no commits reference it** → `Pending`.
5. **A PRD exists in `docs/prds/` with `- [ ]` boxes still unchecked** → one row per unchecked item, all `Pending`. (One row per checked-off item flips to `Shipped`.)
6. **Uncommitted modifications + a referenced plan exists** → `In-Progress`.

**Conversational signals** (used to seed new rows, write Notes, capture intent):

7. **What the user said in this session.** Statements like "we should also do X next week", "Y is blocked on Z, defer for now", "after the soak window we'll flip the flag" become `Pending` rows or get added to existing rows' `Notes`. The conversation is rich but lossy — only use it when no file-based signal exists, or to *augment* (Notes/Artifacts) what file signals already established.

### 3. Match candidates to existing rows

For each candidate, decide: is this an **existing row** (update) or a **new row** (insert)?

Match in this priority order — stop at the first hit:

1. **Explicit ID reference** — the candidate's plan/PRD/commit message contains a `BL-NNN` reference. Trust it.
2. **Artifact-link match** — the candidate's plan/PRD path or PR URL exactly matches an entry in some row's Artifacts column. Trust it.
3. **Feature-title fuzzy match** — the candidate's title is substantially the same as an existing row's Feature, ignoring case, articles, and trailing punctuation. *Verify with the user before merging* if there's any ambiguity (see "Clarifying questions" below).
4. **No match** — insert as a new row with a fresh ID.

### 4. Decide the new status of each row

For each row that's been touched (existing or new), apply the signals from step 2 to determine which section it should be in. Rules of thumb:

- **Once `Shipped`, never demoted.** If a row is currently `Shipped` and a new signal says "in-progress," ignore it — likely a follow-up task that needs its own row.
- **Authoritative beats suggestive beats conversational.** A commit hash beats a written plan beats a verbal "we'll do this."
- **Default to the lower-confidence status.** When unsure between `Pending` and `In-Progress`, prefer `Pending`. Between `In-Progress` and `Shipped`, prefer `In-Progress`. Don't claim shipped without proof.

### 5. Ask clarifying questions when inference is non-definitive

If the skill can't confidently classify or match a candidate, **ask the user** rather than guessing. Concrete cases that warrant a question:

- **Ambiguous title match.** "Found `BL-007: Regime-Router v1` in the existing backlog and you mentioned 'regime router' in this session. Same row, or a follow-up?"
- **Status uncertainty.** "Plan `2026-04-27-scanner-universe-expansion.md` exists but I don't see commits to main referencing it. Mark `BL-NNN` as Pending, or is this In-Progress on a feature branch?"
- **Multi-part shipping.** "Three commits this session look related to PRD-2026-04-26. Should I close out all 8 unchecked items as Shipped, or only the items you specifically completed?"
- **Cross-session re-evaluation.** "`BL-005` was Pending as of last update; I see no new activity. Leave as Pending, or move to a `## Cancelled` section / drop it?"

Ask **one question at a time**. Don't dump a list — the user should be able to answer in a single line. If the user gives a non-answer like "you decide," fall back to the lower-confidence status and add a Note explaining the decision.

What **doesn't** warrant a question:

- A new commit obviously implements the row's plan and the user already moved the PRD file to `docs/processed/`. Just flip to `Shipped` and append the commit hash.
- A new plan was written this session and no commits reference it. Just create a `Pending` row — the file is the proof.
- Trivial typo correction in a Feature title — leave as-is. Summaries are immutable; titles are too, in practice.

### 6. Show the proposed diff and confirm

Before writing, print a **brief, scannable summary** of what's about to change. Use bullet points, not a wall of text:

```
Proposed updates to docs/backlog/product-backlog.md:
  • BL-007 "Regime-Router v1": Pending → Shipped (commit e1d3bfb appended)
  • BL-009 "vwap_reclaim_long Phase 2.1": In-Progress → Shipped (commits 597718d, aa27a4a appended)
  • BL-012 (new) "Dashboard Observability v3": Pending, Medium — plan only, no commits yet
  • BL-013 (new) "Scanner universe expansion": Pending, High — depends on BL-007

Confirm to write? (yes / edit)
```

Include the derived **priority** and any **dependency** facts for new Pending/In-Progress rows in this summary, so the user can override before anything is written — e.g. `BL-013 (new) "Scanner universe expansion": Pending, High — depends on BL-007`.

Only proceed if the user confirms. If they say "edit", let them course-correct row-by-row before writing.

### 7. Write the file

Use the Edit tool to make targeted changes — never overwrite the whole file. For each row that changed:

- **Status change** (move between sections): remove from old section, insert at top of new section.
- **In-place update** (same section, new artifacts/notes/timestamp): edit only the affected line.
- **New row**: insert at top of its target section.

> **"Top of section" means directly below the separator row, never above it.**
> A GFM table is `column-header → separator (`|---|…|`) → data`. Inserting a
> new row between the header and the separator pushes the separator down into
> the data; over many inserts it drifts out of place or (when a section
> empties and refills) goes missing entirely. A misplaced or missing separator
> makes markdown renderers — including the bundled HTML dashboard — silently
> drop every data row above it. So the newest row goes on the line *after* the
> separator, and the separator must always remain the first line under the
> column header.

After all edits, **run the structural validator** — it is the authoritative
check for the separator-drift bug above and must pass before you report
success:

```bash
python3 "$SKILL_DIR/scripts/backlog_helper.py" validate "$BACKLOG"
# if it reports problems, repair in place and re-run:
python3 "$SKILL_DIR/scripts/backlog_helper.py" validate "$BACKLOG" --fix
```

Then re-read the file once and visually verify:
- Three section headers are present and in the right order.
- Each section's table header is intact, with its separator row directly under it.
- No row appears in two sections.
- Every row has 7 cells (count the pipes).
- IDs are unique.

If any check fails, fix it before reporting success.

### 8. Regenerate the HTML dashboard if the bundled template is newer

After writing the markdown, ensure the dashboard at `docs/backlog/product-backlog.html` is in sync with the skill's bundled template:

```bash
python3 "$SKILL_DIR/scripts/backlog_helper.py" regenerate-html-if-stale "$ROOT/docs/backlog/product-backlog.html"
```

The helper prints one of three outcomes:

- `created: <path>` — the HTML didn't exist; first-time write.
- `regenerated: <path>` — the file existed but its embedded version was older than the bundled template.
- `unchanged: <path>` — the on-disk version matches the template; no write happened.

The user does **not** see a confirmation prompt for this step in the routine `unchanged` case. When `created` or `regenerated`, mention it in the final report (step 10) so the user knows their dashboard file moved.

The HTML reads the markdown live via the browser. It does **not** need to be regenerated when the markdown changes — only when the template's structure changes (a `created` or `regenerated` outcome happens at most once per template version bump).

### 9. Ask whether to commit and push

After all writes are done, surface this prompt **once** at the end:

> Commit and push `docs/backlog/product-backlog.md` (and `product-backlog.html` if it was created/regenerated) to git? **(yes / skip)**

Behavior on each answer:

- **yes** — Stage **only** the backlog files by explicit path (never `git add .` or `-A`, even if the working tree has other dirty files):
  ```bash
  git add docs/backlog/product-backlog.md
  # plus the HTML, only if step 8 returned created or regenerated
  git add docs/backlog/product-backlog.html
  git commit -m "<message>"
  git push
  ```
  The commit message should be **one line**, concise, and describe the row-level changes — e.g. `chore(backlog): mark BL-007 shipped, add BL-013` or `chore(backlog): bootstrap product backlog dashboard`. Do not include the AI-attribution footer for these commits — they're routine bookkeeping.
- **skip** — leave the files modified in the working tree. Do not stash, do not stage. The user will commit them later (or not).

Two refinements:

1. **If the working tree has unrelated dirty files**, that's fine — staging by explicit path means we won't pull them in. Don't warn the user about unrelated changes; that's not the skill's job.
2. **If the cwd isn't a git repo** (rare — the user's project structure usually puts a backlog inside a repo), skip the prompt entirely with a one-line note: `Not a git repo; commit/push skipped.`

### 10. Report what changed

End with a one-line summary: `Updated docs/backlog/product-backlog.md: 2 shipped, 1 in-progress, 2 new pending. Dashboard: unchanged. Committed e1d3bfb.` Don't restate the diff in full — the user already saw it in step 6.

## HTML dashboard

The skill bundles a single-file HTML dashboard at `templates/product-backlog.html`. On every invocation, the skill copies it into the project's `docs/backlog/product-backlog.html` if (and only if) the bundled template's version exceeds the on-disk version. The version is a single integer in an HTML comment near the top of the file:

```html
<!-- product-backlog-dashboard-version: 1 -->
```

When the skill author edits the bundled template in a way that should trigger users to re-fetch (changed columns, fixed parser bug, new feature), they bump this integer. Otherwise it stays put — most skill updates won't touch the dashboard.

### What the dashboard does

The HTML is **never bundled with data**. On first load, the user clicks "Open file…" and picks `product-backlog.md` from their machine. The browser's [File System Access API](https://developer.mozilla.org/en-US/docs/Web/API/File_System_Access_API) returns a persistent `FileSystemFileHandle`, which the page stores in IndexedDB. On subsequent visits the page restores the handle automatically — no re-pick needed unless the browser has revoked permission, in which case a single click re-grants it.

The dashboard:

- Renders three sections (In-Progress / Pending / Shipped) matching the markdown's structure.
- Shows count badges and a single search box that filters across id / title / summary / notes / artifacts.
- Offers a priority filter: four multi-select chips (Critical / High / Medium / Low), all active by default. Deselecting any chip narrows the view to rows whose derived priority is still selected; while a subset is active, unprioritized rows (all Shipped rows, which never carry a priority tag) are hidden. The priority filter and the search box compose (both must match). Re-selecting all four chips clears the filter and restores every row.
- Renders artifact cells with clickable links and inline-code commit hashes.
- Is fully self-contained — no CDN, no external CSS, no external JS. Works offline.
- Honors the OS's light/dark color scheme via `prefers-color-scheme`.

### Browser compatibility

| Browser | Persistent handle | Behavior |
|---|---|---|
| Chrome, Edge, Brave, Arc, Opera, other Chromium | ✅ | Pick once, reload, dashboard renders. |
| Safari | ❌ | Falls back to `<input type="file">`. User picks each visit; no IndexedDB persistence. Dashboard still works. |
| Firefox | ❌ | Same fallback as Safari. |

The fallback path is automatic — no code branch the user has to opt into. The "Last opened: X (re-open to refresh)" label appears in the header so the user knows what file the dashboard expects.

### Why store the handle in IndexedDB and not localStorage

`FileSystemFileHandle` objects are not strings — `localStorage` only takes strings. IndexedDB serializes them via the structured-clone algorithm. localStorage is still used for the human-readable filename (so the header can say "Last opened: product-backlog.md") since that's plain text and useful even in fallback browsers.

## Examples

### Example 1 — End of a productive session

**Session context**: User shipped a PRD with 3 items today (commits on `main`), wrote a new plan for next week's work, and discussed deferring an old idea.

**Existing backlog**: 8 rows. `BL-005` is the old idea, currently `Pending`.

**Skill behavior**:
1. Detects 3 commits matching opportunity items marked `✅ DONE` → 3 rows flip to `Shipped`.
2. Detects new plan file with no commits → inserts new `Pending` row.
3. User mentioned "let's punt BL-005 to next quarter, it's not pulling weight."
   - **Asks**: "Move BL-005 to a Cancelled section, or leave Pending with a note?"
   - User: "Leave it Pending with a note about why we're deferring."
   - Adds note: `Deferred 2026-05-02 — not pulling weight; revisit next quarter.`
   - Updates `Last updated`.
4. Shows proposed diff (5 changes), user confirms, writes.

### Example 2 — First invocation in a fresh project

**Session context**: User just finished implementing one feature on a new project. No backlog file exists yet.

**Skill behavior**:
1. Runs `init` — creates `docs/backlog/product-backlog.md` from template.
2. Detects the implementation work via git log + the conversation.
3. Inserts one `Shipped` row.
4. Reports: `Created docs/backlog/product-backlog.md and added BL-001 (Shipped).`

### Example 3 — Mid-implementation invocation

**Session context**: User is half-way through a multi-day implementation. Some commits made on a feature branch, more work to do.

**Skill behavior**:
1. Detects feature branch with commits (not on `main`) + plan exists.
2. Classifies as `In-Progress`. (Not Shipped — not on main yet.)
3. Inserts a row with the plan as Artifact and the feature branch name in Notes.
4. Mentions: "I'll flip this to Shipped once you merge to main and re-invoke."

## Anti-patterns to avoid

- **Don't trust conversational claims of "shipped" alone.** "I think we shipped that" without a corresponding commit/file change is not enough. Ask, or leave as `In-Progress`.
- **Don't rewrite Summaries.** They're a historical record. If the work changed direction, add a follow-up row instead.
- **Don't auto-archive Shipped rows.** The user explicitly chose a single-file model. If the file gets long, the user will trim manually.
- **Don't generate IDs by counting rows.** Use the helper script — it handles deleted/skipped IDs correctly.
- **Don't write status into a column.** Section *is* status. A `Status` column would create two sources of truth that can drift.
- **Don't fail silently if the table is malformed.** If parsing finds a row with the wrong number of cells, surface it to the user before writing — don't paper over it.
- **Don't invoke this skill for one-off todos.** A backlog row is a *shippable unit*, not a chore. "Update the docstring on `foo()`" is not a backlog row; "Refactor the foo subsystem" is.
- **Don't regenerate the HTML on every invocation.** It's the bundled template's version that gates regeneration, not the markdown's content. Re-copying the HTML each run would make the diff noisy and cause spurious git churn.
- **Don't `git add .` or `git add -A` in the commit step.** Stage the backlog files by explicit path. Other dirty files in the working tree are not the skill's concern.
- **Don't auto-commit without asking.** The commit/push prompt is mandatory — even if the user said "yes, push" earlier in the conversation about something else, the backlog commit needs its own confirmation. Cheap to confirm, expensive to push the wrong thing.
- **Don't assign priority to Shipped rows.** Priority informs sequencing of unfinished work; it's moot once a row is Shipped. Only Pending/In-Progress rows get a `**(Priority)**` tag.
- **Don't invent dependencies.** Only record a `Dependency on BL-NNN` when the id actually exists and the blocking relationship is real. If unsure, ask rather than guess.

## Why this skill exists

A product backlog is the lightest-weight tool for staying honest about what you've actually shipped vs. what you've only talked about shipping. In a solo workflow without a Linear/Jira instance, the same role gets played by ad-hoc notes that drift, get rewritten, or quietly get lost. The discipline this skill enforces — atomic rows, immutable summaries, append-only artifacts, status as section — is what makes the file useful six months from now: a row from April 2026 still says exactly what was meant in April 2026, plus everything that happened to it since.

The point isn't bureaucracy. It's that a future-you (or a teammate, or another Claude session) can open the file and immediately understand the state of the world without re-reading every commit.
