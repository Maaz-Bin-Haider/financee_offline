/* ============================================================
   team_activity.js — the manager's Team Activity page
   (TEAM_ACTIVITY_PLAN.md, Phase 4)

   A year of one user's work as a grid of days, GitHub's way:
   one column a week, Monday at the top, each square as dark as
   the day was busy. The scale is the same for every user
   (decision 3): 1-4 actions, 5-10, 11-25, 26 or more. Days the
   log did not yet exist are filled from "Entry By" in the same
   greens; the square's hover text and the day's list say
   "approximate" (decision 2).

   Pick a square -- click it, or reach it with the arrow keys and
   press Enter -- and the day's actions are listed in order, each
   opening its record.

   ── Node and the browser ────────────────────────────────────
   The pure half -- levels, the week layout, the words -- is
   exported for system_tests/js/team_activity.test.js; the page
   half runs when the page's data is present.
   ============================================================ */

(function (root, factory) {
  const api = factory(root);
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.FinanceeTeamActivity = api;
  if (root && root.document && root.document.getElementById) {
    root.document.addEventListener("DOMContentLoaded", () => api.start(root.document));
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
  "use strict";

  const THRESHOLDS = [1, 5, 11, 26];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const DAY_MS = 86400000;

  /* ── Pure ─────────────────────────────────────────────────── */

  function level(count) {
    return THRESHOLDS.filter((step) => count >= step).length;
  }

  // Days are calendar dates, handled at UTC midnight so no time zone of the
  // browser's can move one.
  function parse(iso) { return new Date(`${iso}T00:00:00Z`); }
  function isoOf(date) { return date.toISOString().slice(0, 10); }
  function addDays(iso, n) { return isoOf(new Date(parse(iso).getTime() + n * DAY_MS)); }
  function weekday(iso) { return (parse(iso).getUTCDay() + 6) % 7; }   // Monday 0

  function dayLabel(iso) {
    const d = parse(iso);
    return `${WEEKDAYS[weekday(iso)]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  }

  /* Columns of seven days, Monday first, from the week holding `start` to
     the week holding `end`; a day outside [start, end] is null. */
  function weeks(start, end) {
    const columns = [];
    let monday = addDays(start, -weekday(start));
    while (monday <= end) {
      const cells = [];
      for (let i = 0; i < 7; i++) {
        const day = addDays(monday, i);
        cells.push(day >= start && day <= end ? day : null);
      }
      columns.push({ monday, cells });
      monday = addDays(monday, 7);
    }
    return columns;
  }

  /* A month's name over the first column whose first day lies in it --
     unless the next month's begins within three columns, as a grid that
     opens on the last days of a month does: the two would overlap, so the
     sliver's is left out, as GitHub does. */
  function monthMarks(columns) {
    const marks = [];
    let last = null;
    columns.forEach((column, index) => {
      const first = column.cells.find(Boolean);
      if (!first) return;
      const month = parse(first).getUTCMonth();
      if (month !== last) {
        marks.push({ column: index, label: MONTHS[month] });
        last = month;
      }
    });
    return marks.filter((mark, i) => !marks[i + 1] || marks[i + 1].column - mark.column >= 3);
  }

  const NOUNS = {
    sale: ["sale", "sales"], purchase: ["purchase", "purchases"],
    sale_return: ["sale return", "sale returns"], purchase_return: ["purchase return", "purchase returns"],
    payment: ["payment", "payments"], receipt: ["receipt", "receipts"],
    contra: ["contra entry", "contra entries"], draft: ["draft", "drafts"],
    draft_return: ["draft return", "draft returns"], party: ["party", "parties"],
    item: ["item", "items"], opening_stock: ["opening stock action", "opening stock actions"],
    opening_cash: ["opening cash action", "opening cash actions"], owner_equity: ["equity action", "equity actions"], month_close: ["period close action", "period close actions"],
    run: ["report run", "report runs"], export: ["download", "downloads"],
  };

  function counted(n, what) {
    const noun = NOUNS[what] || [what, what];
    return `${n} ${n === 1 ? noun[0] : noun[1]}`;
  }

  /* A square's words: "Thu 14 Aug 2026 · 23 actions: 9 receipts, 8 payments,
     6 sales", or "no activity". */
  function tooltip(iso, day) {
    if (!day || !day.work) return `${dayLabel(iso)} · no activity`;
    const parts = Object.entries(day.what || {})
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([what, n]) => counted(n, what));
    const head = `${dayLabel(iso)} · ${day.work} action${day.work === 1 ? "" : "s"}`;
    return `${head}${parts.length ? ": " + parts.join(", ") : ""}${day.approximate ? " (approximate)" : ""}`;
  }

  const VERBS = {
    create: "Created", update: "Edited", delete: "Deleted", cancel: "Cancelled",
    release: "Released", convert: "Converted", run: "Ran", export: "Downloaded",
  };

  /* One line of a day's list: what was done, in words. */
  function eventText(event) {
    const verb = VERBS[event.action];
    return verb ? `${verb} ${event.label}` : String(event.label || event.action);
  }

  function plural(n, one, many) { return `${n} ${n === 1 ? one : many}`; }

  /* "2026-08-15T21:14" -> "Today 21:14", "Yesterday 09:03", "15 Aug 2026 21:14". */
  function whenText(local, today) {
    if (!local) return "Never";
    const [day, time] = local.split("T");
    if (today && day === today) return `Today ${time}`;
    if (today && day === addDays(today, -1)) return `Yesterday ${time}`;
    const d = parse(day);
    return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()} ${time}`;
  }

  /* A share of the busiest cell, on the same five shades: the hours grid and
     the team's week strips sum many days, so their scale is their own. */
  function relativeLevel(n, max) {
    if (!n || !max) return 0;
    return Math.min(4, Math.ceil((4 * n) / max));
  }

  const WATCH_TYPES = {
    delete: "Deleted",
    old_edit: "Edited an old document",
    late: "Before opening time",
    failed_sign_in: "Failed sign-ins",
  };

  /* A watch-list row's words. */
  function watchText(item) {
    if (item.type === "old_edit" && item.dated) return `${item.label} (dated ${dayLabel(item.dated)})`;
    if (item.type === "failed_sign_in") return `${item.label} (${item.attempts} in ten minutes)`;
    return String(item.label || "");
  }

  /* Rows as CSV text: every cell quoted, quotes doubled. The quote is made,
     not written: a quote inside a regex or a nested template literal throws
     scripts/check_js_identifiers.py's string stripper off the whole file. */
  const QUOTE = String.fromCharCode(34);
  function csv(rows) {
    const quoted = (cell) => {
      let value = String(cell == null ? "" : cell);
      if (typeof cell === "string" && /^[\s]*[=+@\-\t\r]/.test(value)) value = "'" + value;
      return QUOTE + value.split(QUOTE).join(QUOTE + QUOTE) + QUOTE;
    };
    return rows.map((row) => row.map(quoted).join(",")).join("\n");
  }

  /* Text a PDF can print. jsPDF's Helvetica knows Windows-1252 only, and one
     character outside it makes jsPDF write the whole line as two-byte text
     (the ledger's "IÄ  C o n t r a" of 2026-09-28): anything else becomes "?". */
  const CP1252_EXTRA = "\u20ac\u201a\u0192\u201e\u2026\u2020\u2021\u02c6\u2030\u0160\u2039\u0152\u017d" +
    "\u2018\u2019\u201c\u201d\u2022\u2013\u2014\u02dc\u2122\u0161\u203a\u0153\u017e\u0178";
  function pdfSafe(text) {
    return Array.from(String(text == null ? "" : text), (ch) => {
      const code = ch.codePointAt(0);
      if ((code >= 0x20 && code <= 0x7e) || (code >= 0xa0 && code <= 0xff) || CP1252_EXTRA.includes(ch)) return ch;
      return ch === "\u2192" ? "to" : "?";
    }).join("");
  }

  /* ── The page ─────────────────────────────────────────────── */

  function start(doc) {
    const dataNode = doc.getElementById("activity-page");
    if (!dataNode) return;
    const data = JSON.parse(dataNode.textContent);
    let invalidated = false;
    root.addEventListener("financee:activity-session-changed", () => {
      invalidated = true;
      const page = doc.querySelector(".ta-page");
      if (page) page.textContent = "Your session changed. Reload this page to view activity.";
    });
    const $ = (id) => doc.getElementById(id);
    const userBox = $("taUser");
    const yearBox = $("taYear");
    const grid = $("taGrid");
    const months = $("taMonths");
    const dayPanel = $("taDay");
    const scroller = grid.closest(".ta-grid-scroll");
    // The newest weeks stay in view -- after a draw, and when the window
    // changes size -- until the manager scrolls back to older ones.
    let pinned = true;
    if (scroller) {
      scroller.addEventListener("scroll", () => {
        pinned = scroller.scrollLeft + scroller.clientWidth >= scroller.scrollWidth - 2;
      });
      root.addEventListener("resize", () => { if (pinned) scroller.scrollLeft = scroller.scrollWidth; });
    }
    const state = { user: data.user, year: "", days: {}, cells: [], selected: null, answer: null,
                    dayAnswer: null, team: null, watch: null, watchType: "" };

    const linked = root.FinanceeRecordLink ? root.FinanceeRecordLink.number(root.FinanceeRecordLink.take("user").user) : null;
    const link = linked ? Number(linked) : null;
    if (link && data.users.some((u) => u.id === link)) state.user = link;

    data.users.forEach((user) => {
      const option = doc.createElement("option");
      option.value = String(user.id);
      option.textContent = user.active ? user.username : `${user.username} (inactive)`;
      userBox.appendChild(option);
    });
    userBox.value = String(state.user || "");
    const last12 = doc.createElement("option");
    last12.value = "";
    last12.textContent = "Last 12 months";
    yearBox.appendChild(last12);
    data.years.forEach((year) => {
      const option = doc.createElement("option");
      option.value = String(year);
      option.textContent = String(year);
      yearBox.appendChild(option);
    });

    userBox.addEventListener("change", () => { state.user = Number(userBox.value); load(); });
    yearBox.addEventListener("change", () => { state.year = yearBox.value; load(); });
    grid.addEventListener("keydown", onKey);
    const on = (id, name, fn) => { const node = $(id); if (node) node.addEventListener(name, fn); };
    on("taWatchDays", "change", loadWatch);
    on("taWatchTypes", "click", (event) => {
      const chip = event.target.closest("[data-type]");
      if (!chip) return;
      state.watchType = chip.dataset.type;
      $("taWatchTypes").querySelectorAll("[data-type]").forEach((c) =>
        c.setAttribute("aria-pressed", String(c === chip)));
      drawWatch();
    });
    on("taTeam", "click", (event) => {
      const pick = event.target.closest("[data-user]");
      if (!pick) return;
      state.user = Number(pick.dataset.user);
      userBox.value = String(state.user);
      load();
      // Focus goes where the view goes: the next Tab starts at the picker,
      // not back in the table.
      userBox.scrollIntoView({ block: "center" });
      userBox.focus({ preventScroll: true });
    });
    on("taTeamPdf", "click", () => exportTeam("pdf"));
    on("taTeamCsv", "click", () => exportTeam("csv"));
    on("taDayPdf", "click", () => exportDay("pdf"));
    on("taDayCsv", "click", () => exportDay("csv"));
    on("taWatchPdf", "click", () => exportWatch("pdf"));
    on("taWatchCsv", "click", () => exportWatch("csv"));
    grid.addEventListener("click", (event) => {
      const cell = event.target.closest("[data-day]");
      if (cell) select(cell.dataset.day, true);
    });

    function get(url, params) {
      const query = new URLSearchParams(params).toString();
      return root.fetch(`${url}?${query}`, { credentials: "same-origin", headers: { Accept: "application/json", "X-Activity-Scope": data.scope } })
        .then((response) => response.json().then((body) => {
          if (invalidated) throw new Error("Your session changed. Reload this page.");
          if (response.status === 409 || response.status === 401) {
            root.dispatchEvent(new root.CustomEvent("financee:activity-session-changed"));
          }
          if (!response.ok) throw new Error(body.error || "The page could not load this.");
          return body;
        }));
    }

    function load() {
      if (!state.user) return;
      grid.setAttribute("aria-busy", "true");
      const asked = { user: state.user, year: state.year };
      state.answer = null; state.dayAnswer = null; state.selected = null;
      dayPanel.textContent = "Loading activity…";
      grid.textContent = "Loading activity…";
      state.cells = [];
      get(data.urls.year, asked).then((answer) => {
        if (asked.user !== state.user || asked.year !== state.year) return;   // a newer ask won
        state.answer = answer;
        state.days = Object.fromEntries(answer.days.map((day) => [day.day, day]));
        drawFigures(answer);
        drawGrid(answer);
        drawMix(answer);
        drawHours(answer);
        const busiest = answer.days.filter((d) => d.work).map((d) => d.day).pop();
        select(busiest || answer.end, false);
      }).catch((error) => {
        grid.textContent = error.message;
      }).finally(() => grid.removeAttribute("aria-busy"));
    }

    function drawFigures(answer) {
      const s = answer.summary;
      $("taActions").textContent = s.actions.toLocaleString("en-US");
      $("taActiveDays").textContent = String(s.active_days);
      $("taStreak").textContent = plural(s.current_streak, "day", "days");
      $("taLongest").textContent = plural(s.longest_streak, "day", "days");
      $("taPerDay").textContent = String(s.per_active_day);
      $("taLastWork").textContent = whenText(s.last_work, answer.today);
      $("taLastSignIn").textContent = whenText(s.last_sign_in, answer.today);
      $("taPeriod").textContent = `${dayLabel(answer.start)} to ${dayLabel(answer.end)}`;
      $("taApprox").hidden = !s.approximate;
    }

    function drawGrid(answer) {
      const columns = weeks(answer.start, answer.end);
      grid.textContent = "";
      months.textContent = "";
      grid.style.setProperty("--ta-weeks", String(columns.length));
      months.style.setProperty("--ta-weeks", String(columns.length));
      state.cells = [];
      columns.forEach((column) => column.cells.forEach((iso) => {
        if (!iso) {
          const blank = doc.createElement("span");
          blank.className = "ta-cell is-out";
          blank.setAttribute("aria-hidden", "true");
          grid.appendChild(blank);
          return;
        }
        const day = state.days[iso];
        const cell = doc.createElement("button");
        cell.type = "button";
        cell.className = `ta-cell ta-l${day ? day.level : 0}`;
        if (day && day.approximate) cell.classList.add("is-approx");
        cell.dataset.day = iso;
        cell.tabIndex = -1;
        const words = tooltip(iso, day);
        cell.title = words;
        cell.setAttribute("aria-label", words);
        grid.appendChild(cell);
        state.cells.push(iso);
      }));
      monthMarks(columns).forEach((mark) => {
        const label = doc.createElement("span");
        label.className = "ta-month";
        label.style.gridColumn = String(mark.column + 1);
        label.textContent = mark.label;
        months.appendChild(label);
      });
      if (scroller) {
        scroller.scrollLeft = scroller.scrollWidth;              // the newest weeks
        pinned = true;
      }
    }

    function cellFor(iso) { return grid.querySelector(`[data-day="${iso}"]`); }

    function select(iso, focus) {
      const cell = cellFor(iso);
      if (!cell) return;
      grid.querySelectorAll(".ta-cell.is-selected").forEach((c) => {
        c.classList.remove("is-selected");
        c.setAttribute("aria-pressed", "false");
        c.tabIndex = -1;
      });
      cell.classList.add("is-selected");
      cell.setAttribute("aria-pressed", "true");
      cell.tabIndex = 0;
      if (focus) cell.focus();
      state.selected = iso;
      loadDay(iso);
    }

    function onKey(event) {
      const iso = event.target.dataset && event.target.dataset.day;
      if (!iso) return;
      const moves = { ArrowUp: -1, ArrowDown: 1, ArrowLeft: -7, ArrowRight: 7 };
      let next = null;
      if (event.key in moves) next = addDays(iso, moves[event.key]);
      else if (event.key === "Home") next = state.cells[0];
      else if (event.key === "End") next = state.cells[state.cells.length - 1];
      if (!next) return;
      event.preventDefault();
      if (state.cells.includes(next)) select(next, true);
    }

    function loadDay(iso) {
      dayPanel.setAttribute("aria-busy", "true");
      const askedUser = state.user;
      state.dayAnswer = null;
      get(data.urls.day, { user: askedUser, date: iso }).then((answer) => {
        if (state.selected !== iso || state.user !== askedUser) return;
        state.dayAnswer = answer;
        drawDay(answer);
      }).catch((error) => {
        dayPanel.textContent = error.message;
      }).finally(() => dayPanel.removeAttribute("aria-busy"));
    }

    function drawDay(answer) {
      dayPanel.textContent = "";
      const head = doc.createElement("h3");
      head.className = "ta-day-head";
      const count = answer.work.length;
      head.textContent = `${dayLabel(answer.day)} · ${plural(count, "action", "actions")}` +
        (answer.first ? ` · ${answer.first} to ${answer.last}` : "");
      dayPanel.appendChild(head);
      if (answer.truncated) {
        const note = doc.createElement("p"); note.className = "ta-note";
        note.textContent = "Showing the first 1,000 events for this day."; dayPanel.appendChild(note);
      }
      if (answer.approximate) {
        const note = doc.createElement("p");
        note.className = "ta-note";
        note.textContent = "Approximate: from the old Entry By data. An edit used to move a document's author and time, and deletes were not kept.";
        dayPanel.appendChild(note);
      }
      if (!count && !answer.sessions.length) {
        const none = doc.createElement("p");
        none.className = "ta-empty";
        none.textContent = "Nothing recorded on this day.";
        dayPanel.appendChild(none);
        return;
      }
      if (count) dayPanel.appendChild(list(answer.work, "ta-events"));
      if (answer.sessions.length) {
        const sub = doc.createElement("h4");
        sub.className = "ta-sub";
        sub.textContent = "Sign-ins";
        dayPanel.appendChild(sub);
        dayPanel.appendChild(list(answer.sessions, "ta-events ta-sessions"));
      }
    }

    function list(events, className) {
      const ol = doc.createElement("ol");
      ol.className = className;
      events.forEach((event) => {
        const li = doc.createElement("li");
        li.className = `ta-event ta-${event.action}`;
        const time = doc.createElement("span");
        time.className = "ta-time";
        time.textContent = event.time;
        li.appendChild(time);
        const words = event.href ? doc.createElement("a") : doc.createElement("span");
        words.className = "ta-what";
        words.textContent = eventText(event);
        if (event.href) words.href = event.href;
        li.appendChild(words);
        if (event.ip) {
          const ip = doc.createElement("span");
          ip.className = "ta-ip";
          ip.textContent = event.ip;
          li.appendChild(ip);
        }
        if (event.source === "backfill") li.classList.add("is-approx");
        ol.appendChild(li);
      });
      return ol;
    }

    function drawMix(answer) {
      const box = $("taMix");
      if (!box) return;
      box.textContent = "";
      const total = answer.mix.reduce((sum, row) => sum + row.n, 0);
      if (!total) {
        const none = doc.createElement("p");
        none.className = "ta-empty";
        none.textContent = "No work in this period.";
        box.appendChild(none);
        return;
      }
      answer.mix.forEach((row) => {
        const line = doc.createElement("div");
        line.className = "ta-mix-row";
        const name = doc.createElement("span");
        name.className = "ta-mix-name";
        name.textContent = counted(row.n, row.what);
        const bar = doc.createElement("span");
        bar.className = "ta-mix-bar";
        const fill = doc.createElement("span");
        fill.className = "ta-mix-fill";
        fill.style.width = `${Math.max(1, Math.round((100 * row.n) / answer.mix[0].n))}%`;
        bar.appendChild(fill);
        const share = doc.createElement("span");
        share.className = "ta-mix-share";
        share.textContent = `${Math.round((100 * row.n) / total)}%`;
        line.append(name, bar, share);
        box.appendChild(line);
      });
    }

    function drawHours(answer) {
      const box = $("taHours");
      if (!box) return;
      box.textContent = "";
      const cells = {};
      let max = 0;
      answer.hours.forEach(([weekday, hour, n]) => {
        cells[`${weekday}:${hour}`] = n;
        max = Math.max(max, n);
      });
      const corner = doc.createElement("span");
      corner.className = "ta-hours-label";
      box.appendChild(corner);
      for (let hour = 0; hour < 24; hour++) {
        const label = doc.createElement("span");
        label.className = "ta-hours-label ta-hours-hour";
        label.textContent = hour % 3 === 0 ? String(hour).padStart(2, "0") : "";
        box.appendChild(label);
      }
      WEEKDAYS.forEach((dayName, weekday) => {
        const label = doc.createElement("span");
        label.className = "ta-hours-label";
        label.textContent = dayName;
        box.appendChild(label);
        for (let hour = 0; hour < 24; hour++) {
          const n = cells[`${weekday}:${hour}`] || 0;
          const cell = doc.createElement("span");
          cell.className = `ta-cell ta-hour ta-l${relativeLevel(n, max)}`;
          cell.title = `${dayName} ${String(hour).padStart(2, "0")}:00 - ${plural(n, "action", "actions")}`;
          box.appendChild(cell);
        }
      });
    }

    function loadTeam() {
      if (!data.urls.team || !$("taTeam")) return;
      get(data.urls.team, {}).then((answer) => {
        state.team = answer;
        drawTeam();
      }).catch((error) => { $("taTeam").textContent = error.message; });
    }

    function drawTeam() {
      const answer = state.team;
      const body = $("taTeam");
      body.textContent = "";
      const max = Math.max(0, ...answer.users.flatMap((u) => u.weeks));
      answer.users.forEach((user) => {
        const tr = doc.createElement("tr");
        if (!user.active) tr.classList.add("is-inactive");
        const who = doc.createElement("td");
        const pick = doc.createElement("button");
        pick.type = "button";
        pick.className = "ta-user-link";
        pick.dataset.user = String(user.id);
        pick.textContent = user.username;
        who.appendChild(pick);
        if (user.idle) {
          const tag = doc.createElement("span");
          tag.className = "ta-tag";
          tag.textContent = "Idle";
          tag.title = `Nothing in the last ${answer.idle_days} days`;
          who.appendChild(tag);
        }
        if (!user.active) {
          const tag = doc.createElement("span");
          tag.className = "ta-tag ta-tag-muted";
          tag.textContent = "Inactive";
          who.appendChild(tag);
        }
        const strip = doc.createElement("td");
        const cells = doc.createElement("span");
        cells.className = "ta-strip";
        user.weeks.forEach((n, i) => {
          const cell = doc.createElement("span");
          cell.className = `ta-cell ta-l${relativeLevel(n, max)}`;
          cell.title = `Week of ${dayLabel(answer.weeks[i])}: ${plural(n, "action", "actions")}`;
          cells.appendChild(cell);
        });
        strip.appendChild(cells);
        const cellsText = [String(user.last7), String(user.last30), String(user.days30),
                           whenText(user.last_work, answer.today), whenText(user.last_sign_in, answer.today)];
        tr.appendChild(who);
        cellsText.forEach((text, i) => {
          const td = doc.createElement("td");
          td.textContent = text;
          if (i < 3) td.className = "ta-num";
          tr.appendChild(td);
        });
        tr.appendChild(strip);
        body.appendChild(tr);
      });
    }

    function loadWatch() {
      if (!data.urls.watch || !$("taWatch")) return;
      const days = $("taWatchDays") ? $("taWatchDays").value : "30";
      state.watch = null;
      get(data.urls.watch, { days }).then((answer) => {
        if ($("taWatchDays") && $("taWatchDays").value !== days) return;
        state.watch = answer;
        drawWatch();
      }).catch((error) => { $("taWatch").textContent = error.message; });
    }

    function watchItems() {
      const items = state.watch ? state.watch.items : [];
      return state.watchType ? items.filter((item) => item.type === state.watchType) : items;
    }

    function drawWatch() {
      const body = $("taWatch");
      body.textContent = "";
      const items = watchItems();
      const counts = {};
      (state.watch ? state.watch.items : []).forEach((item) => { counts[item.type] = (counts[item.type] || 0) + 1; });
      $("taWatchTypes").querySelectorAll("[data-type]").forEach((chip) => {
        const type = chip.dataset.type;
        const count = type ? counts[type] || 0 : (state.watch ? state.watch.items.length : 0);
        chip.querySelector(".ta-chip-count").textContent = String(count);
      });
      if (!items.length) {
        const tr = doc.createElement("tr");
        const td = doc.createElement("td");
        td.colSpan = 4;
        td.className = "ta-empty";
        td.textContent = "Nothing to watch in this period.";
        tr.appendChild(td);
        body.appendChild(tr);
        return;
      }
      items.forEach((item) => {
        const tr = doc.createElement("tr");
        tr.className = `ta-watch-${item.type}`;
        const when = doc.createElement("td");
        when.textContent = whenText(item.at, state.watch.today);
        const who = doc.createElement("td");
        who.textContent = item.username;
        const type = doc.createElement("td");
        type.textContent = WATCH_TYPES[item.type] || item.type;
        const what = doc.createElement("td");
        const words = item.href ? doc.createElement("a") : doc.createElement("span");
        words.textContent = watchText(item);
        if (item.href) words.href = item.href;
        what.appendChild(words);
        if (item.ip) {
          const ip = doc.createElement("span");
          ip.className = "ta-ip";
          ip.textContent = ` ${item.ip}`;
          what.appendChild(ip);
        }
        tr.append(when, who, type, what);
        body.appendChild(tr);
      });
    }

    /* ── Exports: the report theme's PDF, or CSV ── */
    /* A file is named for the day it covers: a day's list for that day,
       everything else for today. */
    function downloadCsv(title, rows, day) {
      if (invalidated || (root.financeeFeatureEnabled && !root.financeeFeatureEnabled("excel_export"))) return;
      const header = [["Company", `${data.company} (#${data.company_id})`], ["Time zone", data.timezone]];
      const blob = new Blob([csv(header.concat(rows))], { type: "text/csv;charset=utf-8;" });
      const a = doc.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${title.replace(/[^\w]+/g, "_")}_${day || (state.answer ? state.answer.today : "")}.csv`;
      doc.body.appendChild(a); a.click(); doc.body.removeChild(a);
      URL.revokeObjectURL(a.href);
      if (root.FinanceeActivity) root.FinanceeActivity.exported("csv", title);
    }

    function savePdf(title, context, head, body, orient) {
      if (invalidated || (root.financeeFeatureEnabled && !root.financeeFeatureEnabled("pdf_export", "reports"))) return;
      if (!root.FinanceePdf || !root.jspdf) return;
      root.FinanceePdf.save({
        jsPDF: root.jspdf.jsPDF, module: "activity", title,
        context: pdfSafe(`${data.company} (#${data.company_id}) · ${data.timezone} · ${context}`),
        orient: orient || "p", head, body: body.map((row) => row.map(pdfSafe)),
      });
    }

    function exportTeam(format) {
      if (!state.team) return;
      const head = ["User", "Last 7 days", "Last 30 days", "Days worked (30)", "Last activity", "Last sign-in", "Status"];
      // Dates in full: a file read tomorrow has no "Today".
      const rows = state.team.users.map((u) => [
        u.username, u.last7, u.last30, u.days30, whenText(u.last_work), whenText(u.last_sign_in),
        [u.active ? "" : "Inactive", u.idle ? "Idle" : ""].filter(Boolean).join(", "),
      ]);
      if (format === "csv") downloadCsv("Team Activity", [head].concat(rows));
      else savePdf("Team Activity", `As of ${dayLabel(state.team.today)}`, head, rows, "l");
    }

    function exportDay(format) {
      const answer = state.dayAnswer;
      if (!answer) return;
      // The work and the sign-ins in one list, in time order.
      const head = ["Time", "What", "Note"];
      const note = (e) => (e.source === "backfill" ? "approximate" : e.ip ? `from ${e.ip}` : "");
      const rows = answer.work.concat(answer.sessions)
        .sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0))
        .map((e) => [e.time, eventText(e), note(e)]);
      const title = `Activity of ${answer.user.username}`;
      if (format === "csv") downloadCsv(title, [head].concat(rows), answer.day);
      else savePdf(title, `${dayLabel(answer.day)} · ${plural(answer.work.length, "action", "actions")}`, head, rows);
    }

    function exportWatch(format) {
      if (!state.watch) return;
      const head = ["When", "Who", "What happened", "Detail", "Address"];
      const rows = watchItems().map((item) => [
        whenText(item.at), item.username, WATCH_TYPES[item.type] || item.type, watchText(item), item.ip,
      ]);
      const title = "Activity Watch List";
      if (format === "csv") downloadCsv(title, [head].concat(rows));
      else savePdf(title, `${dayLabel(state.watch.from)} to ${dayLabel(state.watch.today)}`, head, rows, "l");
    }

    load();
    loadTeam();
    loadWatch();
  }

  return {
    THRESHOLDS, MONTHS, WEEKDAYS,
    level, parse, isoOf, addDays, weekday, dayLabel, weeks, monthMarks,
    counted, tooltip, eventText, plural, whenText, start,
    relativeLevel, WATCH_TYPES, watchText, csv, pdfSafe,
  };
});
