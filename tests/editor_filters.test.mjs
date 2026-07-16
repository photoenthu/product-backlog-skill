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

/* ---------- hideBlocked ---------- *
   An item is blocked when any dependency is unshipped or missing entirely —
   the same rule the row's "Blocked" badge uses. Embargo (doNotBuildBefore) is
   deliberately NOT part of this filter. */
const deps = [
  { id: "BL-001", name: "Auth", status: "shipped", priority: "high", dependencies: [] },
  { id: "BL-002", name: "Billing", status: "new", priority: "high", dependencies: ["BL-001"] },        // dep shipped -> not blocked
  { id: "BL-003", name: "Invoices", status: "new", priority: "high", dependencies: ["BL-002"] },       // dep unshipped -> blocked
  { id: "BL-004", name: "Reports", status: "new", priority: "high", dependencies: ["BL-001", "BL-002"] }, // one unshipped -> blocked
  { id: "BL-005", name: "Ghost", status: "new", priority: "high", dependencies: ["BL-999"] },          // missing dep -> blocked
  { id: "BL-006", name: "Standalone", status: "new", priority: "high" },                               // no deps field -> not blocked
];
const base = { search: "", statuses: [], priorities: [], sortKey: "id", sortDir: "asc" };

// Default (absent / false) keeps every item -> unchecked is a no-op.
out = applyFilters(deps, base);
assert.deepEqual(out.map((i) => i.id), ["BL-001", "BL-002", "BL-003", "BL-004", "BL-005", "BL-006"]);
out = applyFilters(deps, { ...base, hideBlocked: false });
assert.equal(out.length, 6);

// Checked drops only dependency-blocked items.
out = applyFilters(deps, { ...base, hideBlocked: true });
assert.deepEqual(out.map((i) => i.id), ["BL-001", "BL-002", "BL-006"]);

// Blockedness is judged against the full input list, not the surviving rows:
// BL-002 is filtered out by the status filter but still blocks BL-003.
out = applyFilters(deps, { ...base, hideBlocked: true, statuses: ["new"] });
assert.deepEqual(out.map((i) => i.id), ["BL-002", "BL-006"]);

// Composes with search.
out = applyFilters(deps, { ...base, hideBlocked: true, search: "bl-00" });
assert.deepEqual(out.map((i) => i.id), ["BL-001", "BL-002", "BL-006"]);

// An item depending on a discarded item is still blocked (not "shipped").
out = applyFilters(
  [
    { id: "BL-010", name: "Dropped", status: "discarded", priority: "low", dependencies: [] },
    { id: "BL-011", name: "Waiter", status: "new", priority: "low", dependencies: ["BL-010"] },
  ],
  { ...base, hideBlocked: true },
);
assert.deepEqual(out.map((i) => i.id), ["BL-010"]);

console.log("editor_filters.test.mjs: all assertions passed");
