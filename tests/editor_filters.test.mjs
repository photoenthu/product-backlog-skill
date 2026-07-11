// tests/editor_filters.test.mjs
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const html = readFileSync(
  new URL("../skills/new-product-backlog/templates/editor.html", import.meta.url),
  "utf8",
);
const m = html.match(/\/\/ <applyFilters>([\s\S]*?)\/\/ <\/applyFilters>/);
assert.ok(m, "applyFilters sentinel block not found in editor.html");
const applyFilters = eval(`(${m[1].trim().replace(/^function applyFilters/, "function")})`);

const items = [
  { id: "BL-001", name: "Login page", description: "auth", notes: "", status: "new", priority: "high" },
  { id: "BL-002", name: "Billing", description: "stripe", notes: "soak", status: "pending", priority: "low" },
  { id: "BL-003", name: "Logout", description: "", notes: "", status: "shipped", priority: "high" },
];

// No filters -> all, default sort by id ascending.
let out = applyFilters(items, { search: "", statuses: [], priorities: [], sortKey: "id", sortDir: "asc" });
assert.deepEqual(out.map((i) => i.id), ["BL-001", "BL-002", "BL-003"]);

// Text search matches name/description/notes/id, case-insensitive.
out = applyFilters(items, { search: "log", statuses: [], priorities: [], sortKey: "id", sortDir: "asc" });
assert.deepEqual(out.map((i) => i.id), ["BL-001", "BL-003"]);

out = applyFilters(items, { search: "soak", statuses: [], priorities: [], sortKey: "id", sortDir: "asc" });
assert.deepEqual(out.map((i) => i.id), ["BL-002"]);

// Status filter (multi-select): empty means "all".
out = applyFilters(items, { search: "", statuses: ["new", "pending"], priorities: [], sortKey: "id", sortDir: "asc" });
assert.deepEqual(out.map((i) => i.id), ["BL-001", "BL-002"]);

// Priority filter composes with status filter.
out = applyFilters(items, { search: "", statuses: ["new", "shipped"], priorities: ["high"], sortKey: "id", sortDir: "asc" });
assert.deepEqual(out.map((i) => i.id), ["BL-001", "BL-003"]);

// Sort by name descending.
out = applyFilters(items, { search: "", statuses: [], priorities: [], sortKey: "name", sortDir: "desc" });
assert.deepEqual(out.map((i) => i.name), ["Logout", "Login page", "Billing"]);

// Sort by priority uses rank (critical<high<medium<low), not alphabetical.
out = applyFilters(items, { search: "", statuses: [], priorities: [], sortKey: "priority", sortDir: "asc" });
assert.deepEqual(out.map((i) => i.priority), ["high", "high", "low"]);

console.log("editor_filters.test.mjs: all assertions passed");
