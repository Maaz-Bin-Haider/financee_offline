/* Node tests for static/js/team_activity.js — the manager's grid of days
 * (TEAM_ACTIVITY_PLAN.md, Phase 4).
 *
 * The pure half: the shade scale (decision 3), the week-by-week layout,
 * the month marks, and the words a square and a day's list say.
 */

const assert = require("assert");
const T = require("../static/js/team_activity.js");

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); passed++; }
  catch (e) { failed++; console.error(`  FAIL: ${name}\n    ${e.message}`); }
}

test("one scale for every user: 1-4, 5-10, 11-25, 26 or more", () => {
  const cases = [[0, 0], [1, 1], [4, 1], [5, 2], [10, 2], [11, 3], [25, 3], [26, 4], [83, 4]];
  for (const [count, level] of cases) assert.strictEqual(T.level(count), level, `${count} actions`);
});

test("the 12 months are 53 whole weeks, Monday on top, ending with today's week", () => {
  // figures.period(2026-09-29) -> 2025-09-29 (the Monday 52 weeks before) .. 2026-09-29
  const columns = T.weeks("2025-09-29", "2026-09-29");
  assert.strictEqual(columns.length, 53);
  assert.strictEqual(columns[0].monday, "2025-09-29");
  assert.strictEqual(columns[0].cells[0], "2025-09-29");
  const last = columns[columns.length - 1];
  assert.deepStrictEqual(last.cells, ["2026-09-28", "2026-09-29", null, null, null, null, null],
                         "the days after today are left empty");
  assert.ok(columns.every((c) => T.weekday(c.monday) === 0));
});

test("a calendar year starts mid-week with the days before it left empty", () => {
  const columns = T.weeks("2026-01-01", "2026-12-31");   // 1 January 2026 is a Thursday
  assert.deepStrictEqual(columns[0].cells.slice(0, 4), [null, null, null, "2026-01-01"]);
  assert.strictEqual(columns[0].monday, "2025-12-29");
  const cells = columns.flatMap((c) => c.cells).filter(Boolean);
  assert.strictEqual(cells.length, 365);
  assert.strictEqual(cells[cells.length - 1], "2026-12-31");
});

test("a month is named over the first week it begins", () => {
  const marks = T.monthMarks(T.weeks("2026-01-01", "2026-03-31"));
  assert.deepStrictEqual(marks.map((m) => m.label), ["Jan", "Feb", "Mar"]);
  assert.strictEqual(marks[0].column, 0);
  assert.strictEqual(marks[1].column, 5, "the week of Monday 2 February");
});

test("a month begun too near the next is not named: the labels would overlap", () => {
  // The 12 months to 29 Sep 2026 open on Monday 29 Sep 2025: one column of
  // September, then October's.
  const marks = T.monthMarks(T.weeks("2025-09-29", "2026-09-29"));
  assert.strictEqual(marks[0].label, "Oct");
  assert.strictEqual(marks[marks.length - 1].label, "Sep");
  assert.ok(marks.every((m, i) => !marks[i + 1] || marks[i + 1].column - m.column >= 3));
});

test("a day reads as the report theme writes dates: three-letter months", () => {
  assert.strictEqual(T.dayLabel("2026-09-03"), "Thu 3 Sep 2026");
  assert.strictEqual(T.dayLabel("2026-08-14"), "Fri 14 Aug 2026");
  assert.strictEqual(T.addDays("2026-02-28", 1), "2026-03-01");
  assert.strictEqual(T.addDays("2026-03-01", -1), "2026-02-28");
});

test("a square says what the day held, busiest kind first", () => {
  const day = { work: 23, approximate: 0, what: { sale: 6, receipt: 9, payment: 8 } };
  assert.strictEqual(T.tooltip("2026-08-14", day),
                     "Fri 14 Aug 2026 · 23 actions: 9 receipts, 8 payments, 6 sales");
  assert.strictEqual(T.tooltip("2026-08-14", { work: 1, approximate: 1, what: { run: 1 } }),
                     "Fri 14 Aug 2026 · 1 action: 1 report run (approximate)");
  assert.strictEqual(T.tooltip("2026-08-16", undefined), "Sun 16 Aug 2026 · no activity");
  assert.strictEqual(T.counted(2, "contra"), "2 contra entries");
  assert.strictEqual(T.counted(1, "export"), "1 download");
});

test("a day's line says what was done", () => {
  assert.strictEqual(T.eventText({ action: "create", label: "Sale #1045 · EURONEXT 408 · 3 units" }),
                     "Created Sale #1045 · EURONEXT 408 · 3 units");
  assert.strictEqual(T.eventText({ action: "update", label: "Payment #1620" }), "Edited Payment #1620");
  assert.strictEqual(T.eventText({ action: "run", label: "Detailed Ledger" }), "Ran Detailed Ledger");
  assert.strictEqual(T.eventText({ action: "export", label: "PDF · Party Ledger" }), "Downloaded PDF · Party Ledger");
  assert.strictEqual(T.eventText({ action: "release", label: "Draft #1 · 2 serials" }), "Released Draft #1 · 2 serials");
  assert.strictEqual(T.eventText({ action: "sign_in", label: "Signed in" }), "Signed in");
  assert.strictEqual(T.eventText({ action: "sign_in_failed", label: "Failed sign-in as ali" }), "Failed sign-in as ali");
});

test("when something last happened reads plainly", () => {
  assert.strictEqual(T.whenText("2026-09-29T21:14", "2026-09-29"), "Today 21:14");
  assert.strictEqual(T.whenText("2026-09-28T09:03", "2026-09-29"), "Yesterday 09:03");
  assert.strictEqual(T.whenText("2026-08-15T21:14", "2026-09-29"), "15 Aug 2026 21:14");
  assert.strictEqual(T.whenText(null, "2026-09-29"), "Never");
  assert.strictEqual(T.whenText("2026-09-29T21:14"), "29 Sep 2026 21:14", "a file's dates are in full");
  assert.strictEqual(T.plural(1, "day", "days"), "1 day");
});

test("the hours and the week strips shade relative to their busiest cell", () => {
  assert.deepStrictEqual([0, 1, 5, 10, 20].map((n) => T.relativeLevel(n, 20)), [0, 1, 1, 2, 4]);
  assert.strictEqual(T.relativeLevel(3, 0), 0);
});

test("a watch-list row says what happened", () => {
  assert.strictEqual(T.watchText({ type: "old_edit", label: "Edited Payment #12", dated: "2026-06-01" }),
                     "Edited Payment #12 (dated Mon 1 Jun 2026)");
  assert.strictEqual(T.watchText({ type: "failed_sign_in", label: "Failed sign-in as ali", attempts: 3 }),
                     "Failed sign-in as ali (3 in ten minutes)");
  assert.strictEqual(T.watchText({ type: "delete", label: "Sale #5" }), "Sale #5");
  assert.deepStrictEqual(Object.keys(T.WATCH_TYPES), ["delete", "old_edit", "late", "failed_sign_in"]);
});

test("CSV quotes every cell and doubles quotes", () => {
  assert.strictEqual(T.csv([["a", 'say "hi"', 3], ["", null, "x,y"]]), '"a","say ""hi""","3"\n"","","x,y"');
});

test("a PDF line carries only what its font can print", () => {
  assert.strictEqual(T.pdfSafe("Sale #5 · ALI & SONS — 1,200.00 €"), "Sale #5 · ALI & SONS — 1,200.00 €");
  assert.strictEqual(T.pdfSafe("A \u2192 B"), "A to B");
  assert.strictEqual(T.pdfSafe("\u0639\u0644\u06cc ⇄ Contra"), "??? ? Contra");
  assert.strictEqual(T.pdfSafe(null), "");
});

test("the page's own script does nothing without the page's data", () => {
  assert.strictEqual(T.start({ getElementById: () => null }), undefined);
});

test("untrusted names cannot become spreadsheet formulas", () => {
  assert.strictEqual(T.csv([["=1+1", "  @SUM(A1)", -4]]), '"\'=1+1","\'  @SUM(A1)","-4"');
});

console.log(`team_activity.test.js: ${passed} passed, ${failed} failed.`);
process.exit(failed ? 1 : 0);
