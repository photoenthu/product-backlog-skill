// Guards the EXACT text the editor's Auto / Semi buttons copy to the clipboard.
// The strings are a contract with the executing skills — a typo here silently
// hands the user a prompt that won't trigger anything.
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const html = readFileSync(
  new URL("../skills/new-product-backlog/templates/editor.html", import.meta.url),
  "utf8",
);
const m = html.match(/\/\/ <backlogPrompt>([\s\S]*?)\/\/ <\/backlogPrompt>/);
assert.ok(m, "backlogPrompt sentinel block not found in editor.html");
const backlogPrompt = eval(`(${m[1].trim().replace(/^function backlogPrompt/, "function")})`);

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

console.log("editor_prompts.test.mjs: all assertions passed");
