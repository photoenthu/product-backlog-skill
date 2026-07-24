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

/* ---------- Auto / Semi (pre-existing contract) ---------- */

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

// The id is substituted, not hardcoded.
assert.equal(
  backlogPrompt("BL-042", "auto"),
  "Implement BL-042 using pr-from-backlog.",
);
assert.equal(
  backlogPrompt("BL-137", "semi"),
  "Implement BL-137 using semiauto-backlog-execution.",
);

// Ids wider than 3 digits still round-trip verbatim.
assert.equal(
  backlogPrompt("BL-1000", "auto"),
  "Implement BL-1000 using pr-from-backlog.",
);

// Both prompts end with a period and name exactly one skill.
for (const mode of ["auto", "semi"]) {
  const out = backlogPrompt("BL-007", mode);
  assert.ok(out.endsWith("."), `prompt should end with a period: ${out}`);
  assert.ok(out.startsWith("Implement BL-007 using "), `unexpected prefix: ${out}`);
}

// The two modes must not produce the same prompt.
assert.notEqual(backlogPrompt("BL-001", "auto"), backlogPrompt("BL-001", "semi"));

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

// Zero-padded and unpadded ids of the same number compare by number.
assert.deepEqual(
  sortBacklogIds(["BL-30", "BL-004", "BL-2"]),
  ["BL-2", "BL-004", "BL-30"],
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
