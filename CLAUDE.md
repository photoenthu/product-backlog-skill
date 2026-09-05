# CLAUDE.md — product-backlog-skill

## Git workflow: solo developer, work directly on `main`

Single maintainer. **No feature branches, no PRs.** Commit straight to `main` and push.

This deliberately overrides two defaults: the harness's "if on the default branch,
branch first," and the global CLAUDE.md's deploy-from-main discipline (which is about
*production deploys* — this repo publishes a plugin, and `main` IS the release channel).
Don't create a branch unless explicitly asked.

Commit → run tests → push. Push without asking; the user has standing authorization.

## Releasing: bump THREE version fields, always together

Any change to skill behaviour is a release. Three fields must move in lockstep:

| File | Field |
|---|---|
| `.claude-plugin/plugin.json` | `version` |
| `.claude-plugin/marketplace.json` | `metadata.version` |
| `.claude-plugin/marketplace.json` | `plugins[0].version` |

**`marketplace.json` is what installed copies read to detect an update.** Bumping only
`plugin.json` ships code that other machines will never auto-update to — they'll report
"already up to date" while running the old version. Verify before pushing:

```bash
python3 -c '
import json
pv = json.load(open(".claude-plugin/plugin.json"))["version"]
m  = json.load(open(".claude-plugin/marketplace.json"))
assert pv == m["metadata"]["version"] == m["plugins"][0]["version"], "version fields out of sync"
print("all three in sync at", pv)'
```

## Tests — run all four before every push

```bash
node tests/editor_filters.test.mjs && node tests/editor_prompts.test.mjs && \
node tests/parse_feature_cell.test.mjs && \
python3 -m unittest discover -s tests -p "*_test.py"
```

Pure stdlib both sides — no npm install, no pip install, no test runner config.

## `editor.html` gotchas

- **`applyFilters()` must stay self-contained.** It sits between `// <applyFilters>` and
  `// </applyFilters>`; `tests/editor_filters.test.mjs` extracts that block by regex and
  `eval`s it in isolation. It cannot reference anything defined outside the sentinels
  (e.g. `todayStr()`) — inject such values via `opts` instead.
- **The DOM layer has no automated harness.** Both `.mjs` suites test extracted pure
  functions only. Verify UI wiring by driving the real page in headless Chrome over CDP
  (`--headless=new --remote-debugging-port=N`, then `/json/list` → `Runtime.evaluate`).
- **Top-level `const state` is a lexical global, not `window.state`.** In `Runtime.evaluate`,
  probe with `typeof state !== "undefined"`; `window.state` is always `undefined`.
- All DOM is built via `createElement`/`textContent` (the `h()` helper). Never `innerHTML`
  with item text. Style is ES5-flavoured: `function () {}` not arrows, 2-space indent.

## `backlog.py` CLI signature

Every subcommand takes the backlog **path as a positional argument**, first:

```bash
python3 skills/new-product-backlog/scripts/backlog.py add "$F" --name "X" --dnbb 2099-01-01
python3 skills/new-product-backlog/scripts/backlog.py add "$F" --name "Y" --depends BL-001
python3 skills/new-product-backlog/scripts/backlog.py serve "$F" [--port N]
```

The dependency flag is `--depends`, **not** `--deps`. `add` auto-creates the file and
`docs/backlog/` if missing, so it bootstraps a fresh project with no `init` step.

**Python is the only writer** for `product-backlog.json`. Never hand-edit it with sed,
Edit, or Write — that bypasses the schema validator and atomic write.
