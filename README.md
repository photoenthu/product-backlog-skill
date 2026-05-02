# product-backlog-skill

A Claude Code skill that maintains a per-project **Product Backlog** in `docs/backlog/product-backlog.md` by analyzing each Claude session for shipped, in-progress, and pending work.

The point: when you finish a session — or check in mid-session — you say "update the backlog" and the skill reconciles what you actually did against what's tracked. It looks at git commits, plans, PRDs, opportunities-marked-DONE, and the conversation itself, then adds or updates rows in a single status-grouped markdown table. No external tooling, no SaaS, no per-project setup beyond invoking the skill once.

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

## Repo layout

```
product-backlog-skill/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── skills/
│   └── product-backlog/
│       ├── SKILL.md
│       └── scripts/
│           └── backlog_helper.py
├── LICENSE
└── README.md
```

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Issues and PRs welcome. The skill is intentionally small; if you'd like to extend it (per-quarter file rotation, owner column, integration with Linear/Jira/etc.), please open an issue first to discuss the shape of the change.
