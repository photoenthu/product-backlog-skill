---
name: product-backlog
description: Maintain a per-project Product Backlog table in `<project>/docs/backlog/product-backlog.md`. Trigger on `/product-backlog`, "update the backlog", "log this to the backlog", "add to product backlog", "track this for later", or at the end of a session that shipped/planned features when the user says "log progress" or "update product backlog". Analyzes the current Claude session — git commits made, plans/PRDs written, opportunities marked DONE, things the user said about future work — and adds/updates rows in a status-grouped markdown table (In-Progress → Pending → Shipped). Use this even when the user just says "remember to ship X next week" or "track this initiative" since those are pending-backlog signals. Each row is atomic (one shippable unit), updated in-place across sessions, with stable BL-NNN ids, immutable summaries, and append-only artifact links. Do not invoke for one-off notes or todos that aren't shippable features.
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
| **Feature** | Short title, ideally <60 chars. Reads like a PR title or ticket name. Avoid trailing periods. |
| **Summary** | 2-3 lines describing what it is and why it matters. **Immutable once written.** If the framing of the work later shifts materially, prefer adding a new follow-up row over rewriting history — the table is partly a historical record. |
| **Created (ET)** | `YYYY-MM-DD HH:MM ET`. Set once when the row is added. Get the current timestamp with `python3 <skill-dir>/scripts/backlog_helper.py now-et`. Always use this helper; do not infer the timezone from `date` or shell vars, since both can mislead on a non-ET machine. |
| **Last updated (ET)** | Same format. Touched whenever any field on the row changes (status, artifacts, notes). |
| **Artifacts** | Pipe-separated markdown links, e.g. `[plan](docs/superpowers/plans/2026-04-27-foo.md) \| [PR #42](https://github.com/...) \| `e1d3bfb``. Use **relative paths** for in-repo files, **full URLs** for PRs/issues, and **inline backticks** for commit hashes. **Append-only**: when new artifacts surface for an existing row, add them to the end; never replace existing entries. |
| **Notes** | Freeform prose. The escape valve for everything else: blockers, deferred reasons, follow-up tasks the user mentioned, gotchas. Append-friendly — prefer "X done; Y still owed" over "Y still owed" so the narrative is preserved. |

### Markdown table escaping

The `\|` literal pipe is required inside any cell that contains pipes (the "Artifacts" column will commonly need this). The pipe in the column separator is a real `|`; the pipe inside content is `\|`. If a cell contains a newline, replace it with `<br>`. If a cell contains a backtick, fence it with double-backticks `` `` `` to avoid breaking the table.

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
  • BL-012 (new) "Dashboard Observability v3": Pending — plan only, no commits yet
  • BL-013 (new) "Scanner universe expansion": Pending — referenced in this session as future work

Confirm to write? (yes / edit)
```

Only proceed if the user confirms. If they say "edit", let them course-correct row-by-row before writing.

### 7. Write the file

Use the Edit tool to make targeted changes — never overwrite the whole file. For each row that changed:

- **Status change** (move between sections): remove from old section, insert at top of new section.
- **In-place update** (same section, new artifacts/notes/timestamp): edit only the affected line.
- **New row**: insert at top of its target section.

After all edits, re-read the file once and visually verify:
- Three section headers are present and in the right order.
- Each section's table header is intact.
- No row appears in two sections.
- Every row has 7 cells (count the pipes).
- IDs are unique.

If any check fails, fix it before reporting success.

### 8. Report what changed

End with a one-line summary: `Updated docs/backlog/product-backlog.md: 2 shipped, 1 in-progress, 2 new pending.` Don't restate the diff in full — the user already saw it in step 6.

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

## Why this skill exists

A product backlog is the lightest-weight tool for staying honest about what you've actually shipped vs. what you've only talked about shipping. In a solo workflow without a Linear/Jira instance, the same role gets played by ad-hoc notes that drift, get rewritten, or quietly get lost. The discipline this skill enforces — atomic rows, immutable summaries, append-only artifacts, status as section — is what makes the file useful six months from now: a row from April 2026 still says exactly what was meant in April 2026, plus everything that happened to it since.

The point isn't bureaucracy. It's that a future-you (or a teammate, or another Claude session) can open the file and immediately understand the state of the world without re-reading every commit.
