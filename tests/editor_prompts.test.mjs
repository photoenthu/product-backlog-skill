// Guards the EXACT text the editor copies to the clipboard: the per-item
// Auto / Semi buttons, the kebab's Groom modal, and the header's batch
// Implement button. These strings are a contract with the executing skills —
// a typo here silently hands the user a prompt that won't trigger anything.
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const html = readFileSync(
  new URL("../skills/new-product-backlog/templates/editor.html", import.meta.url),
  "utf8",
);

// Pull one `// <name> … // </name>` block out of the template and evaluate it
// as a standalone function, so these assertions run without a browser.
function extract(name) {
  const re = new RegExp("// <" + name + ">([\\s\\S]*?)// </" + name + ">");
  const m = html.match(re);
  assert.ok(m, name + " sentinel block not found in editor.html");
  const src = m[1].trim().replace(new RegExp("^function\\s+" + name), "function");
  return eval("(" + src + ")");
}

const backlogPrompt = extract("backlogPrompt");
const groomPrompt = extract("groomPrompt");
const implementPrompt = extract("implementPrompt");
const sortBacklogIds = extract("sortBacklogIds");

/* ---------- Whole-script parse guard ----------
 *
 * Everything above only extracts and evaluates four ~10-line sentinel blocks
 * out of a 45,000-character <script>. That extraction is blind to the other
 * ~99% of the script: a syntax error anywhere outside a sentinel block, a
 * call site that got typo'd (e.g. `groomPromt(...)`), or a helper that is
 * defined but never wired to any button, would all sail through every
 * assertion above while leaving the real page's boot() throwing at parse or
 * runtime time and the table rendering as a blank shell. This suite is the
 * named gate after every editor change, so it needs to at least catch that
 * class of failure — hence the two checks below. */

// Pull the single inline <script> block out of the template.
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(scriptMatch, "editor.html: <script> block not found");
const scriptSource = scriptMatch[1];

// `new Function(...)` compiles the source without executing it, so a syntax
// error anywhere in the script — not just inside the four sentinel blocks —
// throws here. It never touches `document`/`window`, so this is safe outside
// a browser. Do NOT eval() or run this: we only want the parse check.
assert.doesNotThrow(
  () => new Function(scriptSource),
  "editor.html's <script> block failed to parse — boot() would never run " +
    "and the page would render as a blank table shell",
);

// Each helper must appear at least twice in the source: once for its
// `function name(...)` definition and at least once more for a real call
// site. A count of exactly 1 means the helper is defined but never called
// (dead code, or its call site was renamed/typo'd elsewhere in the script) —
// a bug the sentinel-block extraction above can never see, since it only
// looks at the helper's own definition. `>=` rather than `=== 2` because a
// helper legitimately gaining a second call site later must not fail this.
for (const name of ["backlogPrompt", "groomPrompt", "implementPrompt", "sortBacklogIds"]) {
  const occurrences = scriptSource.split(name + "(").length - 1;
  assert.ok(
    occurrences >= 2,
    `${name}: expected >= 2 occurrences of "${name}(" (one definition + at ` +
      `least one call site) but found ${occurrences} — this means ${name} ` +
      "is defined but never called, or its call site was renamed/typo'd",
  );
}

/* ---------- Auto / Semi / No Research (pre-existing contract) ---------- */

// Auto -> pr-from-backlog
assert.equal(
  backlogPrompt("BL-001", "auto"),
  "Implement BL-001 using pr-from-backlog.",
);

// Semi -> semiauto-backlog-execution
assert.equal(
  backlogPrompt("BL-001", "semi"),
  "Implement BL-001 using semiauto-backlog-execution.",
);

// No Research -> no-research-backlog-execution
assert.equal(
  backlogPrompt("BL-001", "none"),
  "Implement BL-001 using no-research-backlog-execution.",
);

// The id is substituted, not hardcoded.
assert.equal(
  backlogPrompt("BL-042", "auto"),
  "Implement BL-042 using pr-from-backlog.",
);
assert.equal(
  backlogPrompt("BL-137", "semi"),
  "Implement BL-137 using semiauto-backlog-execution.",
);
assert.equal(
  backlogPrompt("BL-88", "none"),
  "Implement BL-88 using no-research-backlog-execution.",
);

// Ids wider than 3 digits still round-trip verbatim.
assert.equal(
  backlogPrompt("BL-1000", "auto"),
  "Implement BL-1000 using pr-from-backlog.",
);

// Every prompt ends with a period and names exactly one skill.
for (const mode of ["auto", "semi", "none"]) {
  const out = backlogPrompt("BL-007", mode);
  assert.ok(out.endsWith("."), `prompt should end with a period: ${out}`);
  assert.ok(out.startsWith("Implement BL-007 using "), `unexpected prefix: ${out}`);
}

// No two modes may produce the same prompt.
const execPrompts = ["auto", "semi", "none"].map((m) => backlogPrompt("BL-001", m));
assert.equal(new Set(execPrompts).size, 3, "each exec mode needs its own skill");

// An unknown mode must not fabricate a skill name (`skills[mode]` on a
// prototype key like "constructor" would otherwise stringify a function into
// the prompt). It falls back to auto's skill.
for (const bogus of ["constructor", "toString", "", undefined]) {
  assert.equal(
    backlogPrompt("BL-001", bogus),
    "Implement BL-001 using pr-from-backlog.",
    `unknown mode ${JSON.stringify(bogus)} should fall back to auto`,
  );
}

// Each button in the editor's EXEC_MODES list must map to a real mode: the
// labels and modes are wired here, so a typo'd mode would silently copy the
// auto prompt from a button labelled something else.
const modesBlock = scriptSource.match(/const EXEC_MODES = \[([\s\S]*?)\];/);
assert.ok(modesBlock, "EXEC_MODES list not found in editor.html");
const wiredModes = [...modesBlock[1].matchAll(/mode:\s*"([^"]+)"/g)].map((m) => m[1]);
assert.deepEqual(
  wiredModes,
  ["auto", "semi", "none"],
  "EXEC_MODES must wire exactly the three known modes, in button order",
);
const wiredLabels = [...modesBlock[1].matchAll(/label:\s*"([^"]+)"/g)].map((m) => m[1]);
assert.deepEqual(wiredLabels, ["Auto", "Semi", "No Research"]);

/* ---------- Groom -> backlog-analyzer ---------- */

assert.equal(
  groomPrompt("BL-407", "it looks stale"),
  "Run the /backlog-analyzer skill for BL-407. User's concern/feedback is: it looks stale.",
);

// The id is substituted, not hardcoded; 4-digit ids round-trip.
assert.equal(
  groomPrompt("BL-1042", "no idea if this still matters"),
  "Run the /backlog-analyzer skill for BL-1042. User's concern/feedback is: no idea if this still matters.",
);

// Surrounding whitespace is trimmed off the concern.
assert.equal(
  groomPrompt("BL-1", "   padded   "),
  "Run the /backlog-analyzer skill for BL-1. User's concern/feedback is: padded.",
);

// Interior newlines survive verbatim — a multi-line concern stays multi-line.
assert.equal(
  groomPrompt("BL-2", "first line\nsecond line"),
  "Run the /backlog-analyzer skill for BL-2. User's concern/feedback is: first line\nsecond line.",
);

// A concern that already ends in terminal punctuation must not get a second one.
assert.equal(
  groomPrompt("BL-3", "is this still valid?"),
  "Run the /backlog-analyzer skill for BL-3. User's concern/feedback is: is this still valid?",
);
assert.equal(
  groomPrompt("BL-4", "already fixed."),
  "Run the /backlog-analyzer skill for BL-4. User's concern/feedback is: already fixed.",
);
assert.equal(
  groomPrompt("BL-5", "this is nonsense!"),
  "Run the /backlog-analyzer skill for BL-5. User's concern/feedback is: this is nonsense!",
);
assert.ok(
  !/\.\.$/.test(groomPrompt("BL-6", "trailing period.")),
  "must never produce a doubled period",
);

/* ---------- Implement -> master-backlog-executor ---------- */

assert.equal(
  implementPrompt(["BL-012", "BL-107", "BL-244"]),
  "Run the /master-backlog-executor skill for these backlog ids: BL-012, BL-107, BL-244.",
);

// A single selected id is not a special case.
assert.equal(
  implementPrompt(["BL-7"]),
  "Run the /master-backlog-executor skill for these backlog ids: BL-7.",
);

/* ---------- sortBacklogIds ---------- */

// Numeric, not lexicographic ("BL-107" must not sort before "BL-9").
assert.deepEqual(
  sortBacklogIds(["BL-107", "BL-12", "BL-9"]),
  ["BL-9", "BL-12", "BL-107"],
);

// Three distinct numeric parts (30, 4, 2) sort purely numerically — this
// does NOT exercise the tie-break (no two ids here share a number).
assert.deepEqual(
  sortBacklogIds(["BL-30", "BL-004", "BL-2"]),
  ["BL-2", "BL-004", "BL-30"],
);

// Tie-break: two ids with the SAME numeric part (4) fall back to
// localeCompare on the raw string, which puts "BL-04" before "BL-4" ('0' <
// '4'). Order determined empirically, not assumed — this is purely a
// determinism guarantee for sortBacklogIds itself: the backlog CLI mints
// zero-padded ids monotonically, so two *live* ids can never actually share
// a number. Fed in reverse of the expected output to prove the comparator
// is doing the reordering, not incidental input/Array.sort stability.
assert.deepEqual(
  sortBacklogIds(["BL-4", "BL-04"]),
  ["BL-04", "BL-4"],
);

// Does not mutate its input.
const input = ["BL-9", "BL-1"];
sortBacklogIds(input);
assert.deepEqual(input, ["BL-9", "BL-1"], "sortBacklogIds must not mutate its argument");

// The composition the editor actually calls.
assert.equal(
  implementPrompt(sortBacklogIds(["BL-107", "BL-9", "BL-12"])),
  "Run the /master-backlog-executor skill for these backlog ids: BL-9, BL-12, BL-107.",
);

/* ---------- Cross-prompt sanity ---------- */

// Each prompt names exactly one skill, and the three are all distinct.
const all = [
  backlogPrompt("BL-1", "auto"),
  groomPrompt("BL-1", "concern"),
  implementPrompt(["BL-1"]),
];
assert.equal(new Set(all).size, 3, "the three prompts must be distinct");
assert.ok(!groomPrompt("BL-1", "c").includes("master-backlog-executor"));
assert.ok(!implementPrompt(["BL-1"]).includes("backlog-analyzer"));

console.log("editor_prompts.test.mjs: all assertions passed");
