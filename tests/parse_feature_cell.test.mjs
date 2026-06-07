import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

// Extract the sentinel-wrapped pure function out of the single-file dashboard
// and eval it in this scope. Keeps the test honest against the real source.
const html = readFileSync(
  new URL("../skills/product-backlog/templates/product-backlog.html", import.meta.url),
  "utf8",
);
const m = html.match(/\/\/ <parseFeatureCell>([\s\S]*?)\/\/ <\/parseFeatureCell>/);
assert.ok(m, "parseFeatureCell sentinel block not found in template");
const parseFeatureCell = eval(`(${m[1].trim().replace(/^function parseFeatureCell/, "function")})`);

// Title + priority + all three bullets.
const full = parseFeatureCell(
  "Regime-Router v2 **(High)**<br>• Dependency on BL-007<br>• Cannot Start Before: 2026-07-01 ET<br>• Reason for dependency: needs auth",
);
assert.equal(full.title, "Regime-Router v2");
assert.equal(full.priority, "High");
assert.deepEqual(full.dependencies, [
  "Dependency on BL-007",
  "Cannot Start Before: 2026-07-01 ET",
  "Reason for dependency: needs auth",
]);

// Priority, no bullets.
const noDeps = parseFeatureCell("Dashboard v3 **(Medium)**");
assert.equal(noDeps.title, "Dashboard v3");
assert.equal(noDeps.priority, "Medium");
assert.deepEqual(noDeps.dependencies, []);

// Legacy row: no priority, no bullets.
const legacy = parseFeatureCell("Old feature title");
assert.equal(legacy.title, "Old feature title");
assert.equal(legacy.priority, null);
assert.deepEqual(legacy.dependencies, []);

// Case-insensitive priority, extra whitespace tolerated.
const lc = parseFeatureCell("Thing **(critical)** ");
assert.equal(lc.priority, "Critical");
assert.equal(lc.title, "Thing");

console.log("parse_feature_cell: all assertions passed");
