#!/usr/bin/env node
/* Dependency-free unit tests for the Report Email module's pure JavaScript
   helpers (static/js/report_email.js). Run with:
   node tests/test_report_email.js

   No browser, jQuery, or npm packages required; the module guards its DOM
   wiring so requiring it here only exposes the pure functions. */

"use strict";
const assert = require("assert");
const R = require("../static/js/report_email.js");

let passed = 0;
function test(name, fn) {
  try { fn(); passed++; }
  catch (err) { console.error(`FAIL: ${name}\n  ${err.stack || err.message}`); process.exitCode = 1; }
}

// ── The schedule field ──────────────────────────────────────────────────────

test("the time field and the stored hour/minute round-trip", () => {
  assert.deepStrictEqual(R.timeToParts("00:00"), { hour: 0, minute: 0 });
  assert.deepStrictEqual(R.timeToParts("07:35"), { hour: 7, minute: 35 });
  assert.deepStrictEqual(R.timeToParts("23:59"), { hour: 23, minute: 59 });
  assert.strictEqual(R.partsToTime(0, 0), "00:00");
  assert.strictEqual(R.partsToTime(7, 5), "07:05");
  assert.strictEqual(R.partsToTime(23, 59), "23:59");
});

test("a nonsense time is midnight rather than NaN", () => {
  // The field is a native time input, so this only happens to a browser that
  // renders it as text -- but midnight is the documented default and a NaN
  // would poison the countdown.
  assert.deepStrictEqual(R.timeToParts(""), { hour: 0, minute: 0 });
  assert.deepStrictEqual(R.timeToParts("not a time"), { hour: 0, minute: 0 });
  assert.deepStrictEqual(R.timeToParts(null), { hour: 0, minute: 0 });
});

test("out-of-range values are clamped, never wrapped", () => {
  // 25:70 must not become 01:10 and quietly move the schedule.
  assert.deepStrictEqual(R.timeToParts("25:70"), { hour: 23, minute: 59 });
  assert.strictEqual(R.partsToTime(99, 99), "23:59");
  assert.strictEqual(R.partsToTime(-3, -1), "00:00");
});

// ── Email validation ────────────────────────────────────────────────────────

test("the client-side email check catches the obvious typos", () => {
  ["a@b.com", "owner.name@company.co.uk", "x+tag@mail.example.com"]
    .forEach(v => assert.ok(R.looksLikeEmail(v), v));
  ["", "   ", "nope", "a@b", "a b@c.com", "@b.com", "a@.com", null, undefined]
    .forEach(v => assert.ok(!R.looksLikeEmail(v), String(v)));
});

// ── The countdown ───────────────────────────────────────────────────────────

const KARACHI = { timezone: "Asia/Karachi", send_hour: 0, send_minute: 0 };

test("the wall clock is read in the business zone, not the browser's", () => {
  // 19:00 UTC is 00:00 the next day in Karachi (UTC+5), which is the whole
  // reason the zone is configurable: it decides which day "yesterday" is.
  const at = new Date("2027-03-14T19:00:00Z");
  const karachi = R.zoneNow("Asia/Karachi", at);
  assert.strictEqual(karachi.hour, 0);
  assert.strictEqual(karachi.day, 15);
  const utc = R.zoneNow("UTC", at);
  assert.strictEqual(utc.hour, 19);
  assert.strictEqual(utc.day, 14);
  // And an hour behind Karachi, Dubai is still on the previous day -- the
  // difference this setting exists to get right.
  const dubai = R.zoneNow("Asia/Dubai", at);
  assert.strictEqual(dubai.hour, 23);
  assert.strictEqual(dubai.day, 14);
});

test("an unknown zone falls back instead of throwing", () => {
  // The server falls back the same way. A typed zone must never break the
  // screen; only the countdown suffers.
  const parts = R.zoneNow("Not/AZone", new Date("2027-03-14T19:00:00Z"));
  assert.strictEqual(parts.hour, 19);
});

test("the countdown runs to the next occurrence, today or tomorrow", () => {
  // 23:00 Karachi, sending at midnight: one hour to go.
  const hourBefore = new Date("2027-03-14T18:00:00Z");
  assert.strictEqual(R.secondsUntilNextSend(KARACHI, hourBefore), 3600);
  // 01:00 Karachi, sending at midnight: 23 hours, not minus one.
  const hourAfter = new Date("2027-03-14T20:00:00Z");
  assert.strictEqual(R.secondsUntilNextSend(KARACHI, hourAfter), 23 * 3600);
});

test("a send time that is not midnight counts to that time", () => {
  const settings = { timezone: "Asia/Karachi", send_hour: 7, send_minute: 30 };
  // 06:00 Karachi is 01:00 UTC.
  const at = new Date("2027-03-14T01:00:00Z");
  assert.strictEqual(R.secondsUntilNextSend(settings, at), 90 * 60);
});

test("exactly on the send time counts a whole day, not zero", () => {
  // Zero would flash 00:00:00 and stay there; the send has just happened.
  const atMidnight = new Date("2027-03-14T19:00:00Z");
  assert.strictEqual(R.secondsUntilNextSend(KARACHI, atMidnight), 86400);
});

test("the module's default zone is Pakistan, and all three copies agree", () => {
  // The same default is written in production_fixes.sql section 19 as the
  // column default and in reportmailer/mailer.py as DEFAULT_TIMEZONE; a
  // disagreement would show as a countdown an hour out from the delivery.
  assert.strictEqual(R.DEFAULT_TIMEZONE, "Asia/Karachi");
});

test("the countdown is formatted as padded hours, minutes and seconds", () => {
  assert.strictEqual(R.formatCountdown(0), "00:00:00");
  assert.strictEqual(R.formatCountdown(3725), "01:02:05");
  assert.strictEqual(R.formatCountdown(86399), "23:59:59");
  assert.strictEqual(R.formatCountdown(-5), "00:00:00");
  assert.strictEqual(R.formatCountdown("abc"), "00:00:00");
});

// ── The hero ────────────────────────────────────────────────────────────────

const READY = {
  configured: true, has_password: true, is_enabled: true,
  send_hour: 0, send_minute: 0, timezone: "Asia/Karachi",
  sender_email: "reports@example.com",
};
const ONE_ACTIVE = [{ is_active: true }];

test("a fully configured module is armed and shows a countdown", () => {
  const state = R.heroState(READY, ONE_ACTIVE);
  assert.strictEqual(state.state, "armed");
  assert.strictEqual(state.showNext, true);
  assert.ok(state.line.includes("00:00"));
  assert.ok(state.line.includes("Asia/Karachi"));
  assert.ok(state.line.includes("1 recipient"));
});

test("each thing that stops a delivery says so, in the order you fix them", () => {
  const cases = [
    [{}, [], "blocked", "Not configured"],
    [Object.assign({}, READY, { has_password: false }), ONE_ACTIVE, "blocked", "No app password"],
    [READY, [], "blocked", "No recipients"],
    [READY, [{ is_active: false }], "blocked", "No recipients"],
    [Object.assign({}, READY, { is_enabled: false }), ONE_ACTIVE, "paused", "Paused"],
  ];
  cases.forEach(([settings, recipients, state, label]) => {
    const got = R.heroState(settings, recipients);
    assert.strictEqual(got.state, state, label);
    assert.strictEqual(got.label, label);
    // Nothing that cannot send offers a countdown to a send.
    assert.strictEqual(got.showNext, false, label);
  });
});

test("a paused recipient is not counted as a recipient", () => {
  const state = R.heroState(READY, [{ is_active: true }, { is_active: false }]);
  assert.ok(state.line.includes("1 recipient"), state.line);
  assert.ok(!state.line.includes("2 recipient"), state.line);
});

test("the recipient count is pluralised", () => {
  assert.ok(R.heroState(READY, [{ is_active: true }]).line.includes("to 1 recipient at"));
  assert.ok(R.heroState(READY, [{ is_active: true }, { is_active: true }])
             .line.includes("to 2 recipients at"));
  // And in the delivered state, which is a different sentence.
  const done = { report_date: "2026-09-05", due: false,
                 last_sent_at: "2026-09-06T11:45:39Z" };
  assert.ok(R.heroState(READY, [{ is_active: true }], done).line.includes("to 1 recipient"));
  assert.ok(R.heroState(READY, [{ is_active: true }, { is_active: true }], done)
             .line.includes("to 2 recipients"));
});

test("a delivered day says so instead of counting down to nothing", () => {
  // The bug this exists to prevent: the hero said "Armed" with a countdown
  // whether or not the day had already gone out, so a second scheduled send
  // that the once-a-day guard correctly refused looked like a module that had
  // quietly stopped -- no mail, and no log row either, because the loop never
  // attempted one.
  const state = R.heroState(READY, ONE_ACTIVE, {
    report_date: "2026-09-05", due: false,
    last_sent_at: "2026-09-06T11:45:39Z",
  });
  assert.strictEqual(state.state, "delivered");
  assert.strictEqual(state.label, "Delivered");
  assert.ok(state.line.includes("05 Sep 2026"), state.line);
  assert.ok(/went out/.test(state.line), state.line);
  assert.ok(/tomorrow/.test(state.line), state.line);
  // The countdown still runs, because the next delivery is still coming.
  assert.strictEqual(state.showNext, true);
});

test("the delivery time is shown in the business zone, not the browser's", () => {
  // 11:45 UTC is 16:45 in Karachi. Shown in the browser's zone it would be a
  // different number from the one in the schedule beside it.
  const state = R.heroState(READY, ONE_ACTIVE, {
    report_date: "2026-09-05", due: false,
    last_sent_at: "2026-09-06T11:45:39Z",
  });
  assert.ok(state.line.includes("16:45"), state.line);
  assert.strictEqual(R.timeInZone("2026-09-06T11:45:39Z", "Asia/Karachi"), "16:45");
  assert.strictEqual(R.timeInZone("2026-09-06T11:45:39Z", "Asia/Dubai"), "15:45");
});

test("a day whose retries are spent says that, not that it is armed", () => {
  const state = R.heroState(READY, ONE_ACTIVE, {
    report_date: "2026-09-05", due: false, last_sent_at: null, attempts: 12,
  });
  assert.strictEqual(state.state, "paused");
  assert.strictEqual(state.label, "Retries spent");
  assert.ok(state.line.includes("12 attempts"), state.line);
  assert.ok(/Send now/.test(state.line), state.line);
});

test("a day still owed reads as armed and names the day", () => {
  const state = R.heroState(READY, ONE_ACTIVE, { report_date: "2026-09-05", due: true });
  assert.strictEqual(state.state, "armed");
  assert.ok(state.line.includes("05 Sep 2026"), state.line);
  assert.ok(state.line.includes("Asia/Karachi"), state.line);
});

test("no schedule block at all still renders the armed state", () => {
  // An older cached page, or a settings read that predates the schedule field.
  const state = R.heroState(READY, ONE_ACTIVE);
  assert.strictEqual(state.state, "armed");
  assert.strictEqual(state.showNext, true);
});

test("a bad timestamp or zone yields an empty stamp, never NaN", () => {
  assert.strictEqual(R.timeInZone(null, "Asia/Karachi"), "");
  assert.strictEqual(R.timeInZone("not a date", "Asia/Karachi"), "");
  assert.strictEqual(R.timeInZone("2026-09-06T11:45:39Z", "Not/AZone"), "");
});

test("a missing settings object does not throw", () => {
  assert.strictEqual(R.heroState(null, null).state, "blocked");
  assert.strictEqual(R.heroState(undefined, undefined).state, "blocked");
});

// ── The delivery log ────────────────────────────────────────────────────────

test("a failure's detail is its reason, not its subject", () => {
  // The reason is the most useful thing in a failed row, and the subject of a
  // mail that never left tells the reader nothing.
  assert.strictEqual(
    R.logDetail({ status: "failed", subject: "Sale-wise Profit — Mon",
                  error_message: "SMTPAuthenticationError: 535" }),
    "SMTPAuthenticationError: 535");
  assert.strictEqual(
    R.logDetail({ status: "sent", subject: "Sale-wise Profit — Mon",
                  error_message: "" }),
    "Sale-wise Profit — Mon");
});

test("a skipped row still explains itself", () => {
  assert.strictEqual(
    R.logDetail({ status: "skipped", error_message: "There are no active recipients." }),
    "There are no active recipients.");
  assert.strictEqual(R.logDetail(null), "");
});

test("money is formatted, and a missing figure is a dash rather than zero", () => {
  // A failed run has no profit; printing AED 0.00 would read as a day that
  // made nothing rather than a mail that never went.
  assert.ok(R.formatMoney(616.65).includes("616.65"));
  assert.strictEqual(R.formatMoney(null), "—");
  assert.strictEqual(R.formatMoney(""), "—");
  assert.strictEqual(R.formatMoney(undefined), "—");
  assert.strictEqual(R.formatMoney("not a number"), "—");
  assert.ok(R.formatMoney(0).includes("0.00"));
});

test("the business day is shown with its weekday", () => {
  // "Mon 03 Aug" is checkable against a memory; "2026-08-03" is not.
  const shown = R.formatDay("2026-07-03");
  assert.ok(/Fri/.test(shown), shown);
  assert.ok(/2026/.test(shown), shown);
  assert.strictEqual(R.formatDay(null), "—");
});

test("the log column contract is stable and complete", () => {
  assert.deepStrictEqual(
    R.LOG_COLUMNS.map(c => c.key),
    ["created_at", "report_date", "status", "trigger_source", "recipients",
     "unit_count", "total_profit", "detail"]);
});

// ── Recipient avatars ───────────────────────────────────────────────────────

test("initials come from the local part, however it is punctuated", () => {
  assert.strictEqual(R.recipientInitials("owner@example.com"), "OW");
  assert.strictEqual(R.recipientInitials("maaz.rehan@example.com"), "MR");
  assert.strictEqual(R.recipientInitials("finance_team@example.com"), "FT");
  assert.strictEqual(R.recipientInitials("a-b@example.com"), "AB");
});

test("a degenerate address still produces something to draw", () => {
  assert.strictEqual(R.recipientInitials(""), "?");
  assert.strictEqual(R.recipientInitials(null), "?");
  assert.strictEqual(R.recipientInitials("x@y.com"), "X");
});

// ── Escaping ────────────────────────────────────────────────────────────────

test("everything rendered into the page is escaped", () => {
  // Recipient labels and database error messages both reach innerHTML.
  assert.strictEqual(R.escapeHtml('<img src=x onerror="alert(1)">'),
                     "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;");
  assert.strictEqual(R.escapeHtml("O'Brien & Sons"), "O&#39;Brien &amp; Sons");
  assert.strictEqual(R.escapeHtml(null), "");
});


test("company currency replaces the source system's AED default", () => {
  assert.ok(R.formatMoney(12.5, "PKR").includes("PKR"));
  assert.ok(R.formatMoney(12.5, "AED").includes("AED"));
});
test("unknown and in-progress outcomes do not claim delivery or exhausted retries", () => {
  const settings = {configured:true,has_password:true,is_enabled:true,authorization_valid:true};
  const recipients = [{email:"a@example.test",is_active:true}];
  assert.strictEqual(R.heroState(settings,recipients,{unknown:true}).label,"Check the inbox");
  assert.strictEqual(R.heroState(settings,recipients,{in_progress:true}).label,"Delivery in progress");
  assert.strictEqual(R.heroState(settings,recipients,{due:false,attempts:1}).label,"Waiting to retry");
  settings.authorization_valid=false;
  assert.strictEqual(R.heroState(settings,recipients,{}).label,"Authorization required");
});

test("an overdue report waits for the worker rather than counting down to tomorrow", () => {
  const state = R.heroState({configured:true,has_password:true,is_enabled:true}, [{is_active:true}],
      {due:true,time_reached:true,report_date:"2026-10-22"});
  assert.strictEqual(state.label,"Delivery due");
  assert.strictEqual(state.showNext,false);
});

if (process.exitCode) {
  console.error(`\n${passed} passed, some failed.`);
} else {
  console.log(`report_email.test.js: ${passed} passed, 0 failed.`);
}
