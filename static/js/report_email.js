/* ============================================================
   REPORT EMAIL MODULE — JavaScript

   Three panels over one module: the sending mailbox, the recipient list and
   the delivery log. Every write goes to a stored procedure through a JSON
   endpoint, and the curated database message is what the toast shows, so the
   screen never invents its own wording for a rule the database owns.

   The pure helpers at the top are exported for Node-based tests
   (system_tests/js/report_email.test.js); the browser wiring is guarded so
   requiring this file under Node never touches the DOM.
   ============================================================ */

// ═══════════════════════════════════════════
// PURE HELPERS  (browser + Node)
// ═══════════════════════════════════════════

function escapeHtml(value) {
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  return String(value == null ? "" : value).replace(/[&<>"']/g, ch => map[ch]);
}

// Where the business day is decided when nothing says otherwise. Mirrors
// DEFAULT_TIMEZONE in reportmailer/mailer.py and the column default in
// production_fixes.sql section 19; all three have to agree.
const DEFAULT_TIMEZONE = "Asia/Karachi";

function pad2(n) {
  return String(n).padStart(2, "0");
}

// The schedule is stored as an hour and a minute; the form edits one field.
function timeToParts(value) {
  const match = /^(\d{1,2}):(\d{2})$/.exec(String(value || "").trim());
  if (!match) return { hour: 0, minute: 0 };
  const hour = Math.min(23, Math.max(0, parseInt(match[1], 10)));
  const minute = Math.min(59, Math.max(0, parseInt(match[2], 10)));
  return { hour, minute };
}

function partsToTime(hour, minute) {
  return `${pad2(Math.min(23, Math.max(0, Number(hour) || 0)))}:` +
         `${pad2(Math.min(59, Math.max(0, Number(minute) || 0)))}`;
}

// A deliberately forgiving check, and deliberately not the only one: the
// stored procedure validates the same address and its message is what the
// person actually sees. This only exists to catch a typo before a round trip.
function looksLikeEmail(value) {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(String(value || "").trim());
}

// The wall clock in the business time zone, as plain numbers. Intl is the only
// thing in the browser that can answer "what time is it in Dubai" without
// shipping a timezone database.
function zoneNow(timeZone, now) {
  const when = now || new Date();
  let parts;
  try {
    parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: timeZone || "UTC",
      hour12: false,
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }).formatToParts(when);
  } catch (e) {
    // An unknown zone must not break the screen; the server falls back the
    // same way, and the countdown is the only thing that suffers.
    parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: "UTC", hour12: false,
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }).formatToParts(when);
  }
  const get = type => parseInt(parts.find(p => p.type === type).value, 10);
  // Intl renders midnight as 24 in some engines; 24:00 today is 00:00 today.
  const hour = get("hour") % 24;
  return { year: get("year"), month: get("month"), day: get("day"),
           hour, minute: get("minute"), second: get("second") };
}

// Seconds until the next occurrence of hour:minute in that zone. Same-day if
// it has not passed yet, otherwise tomorrow.
function secondsUntilNextSend(settings, now) {
  const zone = zoneNow(settings.timezone, now);
  const target = (Number(settings.send_hour) || 0) * 3600 +
                 (Number(settings.send_minute) || 0) * 60;
  const current = zone.hour * 3600 + zone.minute * 60 + zone.second;
  const delta = target - current;
  return delta > 0 ? delta : delta + 86400;
}

function formatCountdown(totalSeconds) {
  const s = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  return `${pad2(Math.floor(s / 3600))}:${pad2(Math.floor((s % 3600) / 60))}:${pad2(s % 60)}`;
}

// A stamp like "16:45" in whatever zone the business runs in, for saying when
// today's delivery actually went out.
function timeInZone(value, timeZone) {
  if (!value) return "";
  const d = new Date(value);
  if (isNaN(d.getTime())) return "";
  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: timeZone || "UTC", hour12: false,
      hour: "2-digit", minute: "2-digit",
    }).format(d);
  } catch (e) {
    return "";
  }
}

// What the hero says, and why. Returned as data rather than markup so the
// wording can be asserted without a DOM.
//
// `schedule` is what the delivery loop will actually do next, straight from
// report_email_due(). Without it the hero said "Armed" with a countdown
// whether or not the day had already been delivered, so a second scheduled
// send that the once-a-day guard correctly refused looked like a module that
// had quietly stopped: no mail, and no log row either, because nothing was
// attempted.
function heroState(settings, recipients, schedule) {
  const active = (recipients || []).filter(r => r && r.is_active).length;
  if (!settings || !settings.configured) {
    return { state: "blocked", label: "Not configured",
             line: "No sending mailbox yet. Add one below and the daily report can start going out.",
             showNext: false };
  }
  if (settings.authorization_valid === false) {
    return { state: "blocked", label: "Authorization required", line: "An authorized company member must save this mailbox again.", showNext: false };
  }
  if (schedule && schedule.unknown) {
    return { state: "blocked", label: "Check the inbox", line: "The last delivery outcome is unknown. Reconcile the inbox before re-arming to avoid a duplicate.", showNext: false };
  }
  if (schedule && schedule.in_progress) {
    return { state: "armed", label: "Delivery in progress", line: "The worker has reserved this day's delivery. Refresh shortly.", showNext: false };
  }
  if (!settings.has_password) {
    return { state: "blocked", label: "No app password",
             line: `${settings.sender_email} has no app password stored, so nothing can be sent.`,
             showNext: false };
  }
  if (!active) {
    return { state: "blocked", label: "No recipients",
             line: "The mailbox is ready, but there is nobody to send to yet.",
             showNext: false };
  }
  if (!settings.is_enabled) {
    return { state: "paused", label: "Paused",
             line: `Daily delivery is switched off. ${active} recipient` +
                   `${active !== 1 ? "s are" : " is"} waiting.`,
             showNext: false };
  }
  const at = `${partsToTime(settings.send_hour, settings.send_minute)} ${settings.timezone}`;
  const to = `${active} recipient${active !== 1 ? "s" : ""}`;

  if (schedule && schedule.due === false) {
    // The day is settled. Say which day and when, so a silent scheduler reads
    // as finished rather than broken.
    if (schedule.last_sent_at) {
      const when = timeInZone(schedule.last_sent_at, settings.timezone);
      return {
        state: "delivered", label: "Delivered",
        line: `${formatDay(schedule.report_date)} went out to ${to}` +
              `${when ? ` at ${when}` : ""}. Nothing more is due today — the next ` +
              `report is tomorrow's at ${at}.`,
        showNext: true,
      };
    }
    if ((schedule.attempts || 0) < 12) {
      return { state: "paused", label: "Waiting to retry", line: "Delivery will retry after the 30-minute gap, at or after the configured time. Check the log for the last result.", showNext: false };
    }
    // The retry budget for this day is spent.
    return {
      state: "paused", label: "Retries spent",
      line: `${formatDay(schedule.report_date)} could not be delivered after ` +
            `${schedule.attempts || 0} attempt${schedule.attempts === 1 ? "" : "s"}. ` +
            `Check the delivery log, then use Send now — the schedule resumes tomorrow.`,
      showNext: true,
    };
  }

  if (schedule && schedule.due && schedule.time_reached) {
    return { state: "armed", label: "Delivery due", line: `${formatDay(schedule.report_date)} is due for ${to}. The worker sends it on its next check.`, showNext: false };
  }
  return {
    state: "armed", label: "Armed",
    line: `${schedule && schedule.report_date
             ? formatDay(schedule.report_date) + " is due"
             : "Yesterday's Sale-wise Profit report"} and goes to ${to} at ${at}.`,
    showNext: true,
  };
}

// The log table's shape. Percentages and money are formatted, never summed.
const LOG_COLUMNS = [
  { key: "created_at", label: "When" },
  { key: "report_date", label: "Business Day" },
  { key: "status", label: "Result" },
  { key: "trigger_source", label: "Trigger" },
  { key: "recipients", label: "Recipients" },
  { key: "unit_count", label: "Units" },
  { key: "total_profit", label: "Profit" },
  { key: "detail", label: "Detail" },
];

function formatMoney(value, currency = "PKR") {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (isNaN(n)) return "—";
  return new Intl.NumberFormat("en-AE", {
    style: "currency", currency,
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(n);
}

function formatStamp(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (isNaN(d.getTime())) return String(value);
  return d.toLocaleString("en-AE", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

function formatDay(value) {
  if (!value) return "—";
  const d = new Date(`${value}T00:00:00`);
  if (isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString("en-AE", { weekday: "short", day: "2-digit",
                                         month: "short", year: "numeric" });
}

// A failure's reason is the most useful thing in the row, so it is the row's
// detail; a success shows what it actually sent.
function logDetail(row) {
  if (!row) return "";
  if (row.status === "sent") return row.subject || "";
  return row.error_message || row.subject || "";
}

function recipientInitials(email) {
  const local = String(email || "").split("@")[0] || "?";
  const parts = local.split(/[._-]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return local.slice(0, 2).toUpperCase();
}

// ═══════════════════════════════════════════
// Node export (system_tests/js/report_email.test.js)
// ═══════════════════════════════════════════
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    DEFAULT_TIMEZONE, escapeHtml, pad2, timeToParts, timeInZone, partsToTime, looksLikeEmail,
    zoneNow, secondsUntilNextSend, formatCountdown, heroState,
    LOG_COLUMNS, formatMoney, formatStamp, formatDay, logDetail,
    recipientInitials,
  };
}

// ═══════════════════════════════════════════
// BROWSER-ONLY CODE
// ═══════════════════════════════════════════
if (typeof window !== "undefined" && typeof document !== "undefined") {

  const BASE = "/report-email/";
  let _settings = {};
  let _recipients = [];
  let _schedule = null;
  let _logOffset = 0;
  // Refresh status without replacing unsaved form fields or password input.
  setInterval(async () => {
    if (document.hidden) return;
    try {
      const data = await api("settings/");
      _settings = data.settings || {}; _schedule = data.schedule || null; renderHero();
    } catch (_) { /* Keep the last status; explicit actions report failures. */ }
  }, 30000);
  let _countdownTimer = null;

  function csrf() {
    for (let c of decodeURIComponent(document.cookie).split(";")) {
      c = c.trim();
      if (c.startsWith("csrftoken=")) return c.slice("csrftoken=".length);
    }
    return "";
  }

  async function api(path, options) {
    const opts = Object.assign({ headers: {} }, options || {});
    opts.headers["X-CSRFToken"] = csrf();
    if (opts.body !== undefined) {
      opts.method = opts.method || "POST";
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    const response = await fetch(BASE + path, opts);
    let data = {};
    try { data = await response.json(); } catch (e) { /* non-JSON error page */ }
    if (!response.ok) {
      throw new Error(data.message || `Request failed (${response.status}).`);
    }
    return data;
  }

  // ── Toasts ───────────────────────────────────────────────
  const TOAST_ICON = { ok: "fa-circle-check", bad: "fa-circle-exclamation",
                       info: "fa-circle-info" };

  function toast(kind, message) {
    if (kind === "bad") Alerts.error(message);
    else if (kind === "ok") Alerts.success(message);
    else Alerts.notify(message);
  }

  function busy(button, on) {
    if (!button) return;
    button.classList.toggle("is-busy", !!on);
    button.disabled = !!on;
  }

  // ── Tabs ─────────────────────────────────────────────────
  function moveMarker(tab) {
    const marker = document.getElementById("reTabMarker");
    if (!marker || !tab) return;
    marker.style.width = `${tab.offsetWidth}px`;
    marker.style.transform = `translateX(${tab.offsetLeft}px)`;
  }

  function selectTab(name) {
    document.querySelectorAll(".re-tab").forEach(tab => {
      const on = tab.dataset.panel === name;
      tab.classList.toggle("is-active", on);
      tab.setAttribute("aria-selected", String(on));
      if (on) moveMarker(tab);
    });
    document.querySelectorAll(".re-panel").forEach(panel => {
      const on = panel.id === `panel-${name}`;
      panel.classList.toggle("is-active", on);
      panel.hidden = !on;
    });
    if (name === "log") loadLog();
  }

  // ── Hero ─────────────────────────────────────────────────
  function renderHero() {
    const hero = document.getElementById("reHero");
    const state = heroState(_settings, _recipients, _schedule);
    hero.classList.remove("is-armed", "is-paused", "is-blocked", "is-delivered");
    hero.classList.add(`is-${state.state}`);
    document.getElementById("reStatusText").textContent = state.label;
    document.getElementById("reHeroLine").textContent = state.line;

    // Offered only where it means something: a day the schedule has finished
    // with. In every other state there is nothing to re-arm.
    const rearm = document.getElementById("reRearm");
    if (rearm) rearm.hidden = !(_schedule && !_schedule.in_progress && _schedule.due === false && (_schedule.unknown || _schedule.last_sent_at || _schedule.attempts));

    const wrap = document.getElementById("reNextWrap");
    wrap.hidden = !state.showNext;
    clearInterval(_countdownTimer);
    if (!state.showNext) return;

    document.getElementById("reNextAt").textContent =
      `${partsToTime(_settings.send_hour, _settings.send_minute)} · ${_settings.timezone}`;

    const tick = () => {
      document.getElementById("reCountdown").textContent =
        formatCountdown(secondsUntilNextSend(_settings));
    };
    tick();
    _countdownTimer = setInterval(tick, 1000);
  }

  // ── Mailbox ──────────────────────────────────────────────
  function fillMailbox(settings) {
    _settings = settings || {};
    document.getElementById("reSenderEmail").value = _settings.sender_email || "";
    document.getElementById("reSenderName").value = _settings.sender_name || "";
    document.getElementById("reSmtpHost").value = _settings.smtp_host || "smtp.gmail.com";
    document.getElementById("reSmtpPort").value = _settings.smtp_port || 587;
    document.getElementById("reUseTls").checked = _settings.use_tls !== false;
    document.getElementById("reEnabled").checked = !!_settings.is_enabled;
    document.getElementById("reSendTime").value =
      partsToTime(_settings.send_hour, _settings.send_minute);
    document.getElementById("reTimezone").value = _settings.timezone || DEFAULT_TIMEZONE;

    const password = document.getElementById("reAppPassword");
    const hint = document.getElementById("rePasswordHint");
    password.value = "";
    document.getElementById("reClearPassword").checked = false;
    if (_settings.has_password) {
      password.disabled = false;
      password.placeholder = "•••••••••••••••• — stored. Type to replace it.";
      hint.innerHTML = "An app password is stored. Leave this empty to keep it, " +
                       "or type a new one to replace it.";
    } else {
      password.disabled = false;
      password.placeholder = "Enter the 16-character app password";
      hint.innerHTML = "For Gmail this is an <strong>app password</strong>, " +
                       "not the account password.";
    }

    const advanced = document.getElementById("reAdvancedSummary");
    if (advanced) {
      advanced.textContent =
        `${_settings.smtp_host || "smtp.gmail.com"} : ${_settings.smtp_port || 587}` +
        ` · ${_settings.use_tls === false ? "implicit TLS" : "TLS"}`;
    }

    const note = document.getElementById("reMailboxNote");
    note.textContent = _settings.updated_at
      ? `Last changed by ${_settings.updated_by || "someone"} on ${formatStamp(_settings.updated_at)}.`
      : "";
  }

  function mailboxPayload() {
    const time = timeToParts(document.getElementById("reSendTime").value);
    const payload = {
      sender_email: document.getElementById("reSenderEmail").value.trim(),
      sender_name: document.getElementById("reSenderName").value.trim(),
      smtp_host: document.getElementById("reSmtpHost").value.trim(),
      smtp_port: document.getElementById("reSmtpPort").value,
      use_tls: document.getElementById("reUseTls").checked,
      is_enabled: document.getElementById("reEnabled").checked,
      send_hour: time.hour,
      send_minute: time.minute,
      timezone: document.getElementById("reTimezone").value.trim(),
    };
    // An untouched password field means "leave what is stored alone", which is
    // why the key is omitted rather than sent empty: an empty string clears it.
    const password = document.getElementById("reAppPassword");
    if (password.value) payload.app_password = password.value;
    if (document.getElementById("reClearPassword").checked) payload.app_password = "";
    return payload;
  }

  function flagInvalid(input) {
    input.classList.add("is-invalid");
    input.focus();
    setTimeout(() => input.classList.remove("is-invalid"), 1200);
  }

  async function saveMailbox(event) {
    event.preventDefault();
    const sender = document.getElementById("reSenderEmail");
    if (!looksLikeEmail(sender.value)) {
      flagInvalid(sender);
      toast("bad", "That does not look like an email address.");
      return;
    }
    const button = document.getElementById("reSaveMailbox");
    busy(button, true);
    try {
      const data = await api("settings/save/", { body: mailboxPayload() });
      await refreshSettings();
      toast("ok", data.message || "Saved.");
    } catch (err) {
      toast("bad", err.message);
    } finally {
      busy(button, false);
    }
  }

  // ── Recipients ───────────────────────────────────────────
  function renderRecipients() {
    const list = document.getElementById("reRecipientList");
    const empty = document.getElementById("reRecipientEmpty");
    const count = document.getElementById("reRecipientCount");

    const active = _recipients.filter(r => r.is_active).length;
    count.hidden = !_recipients.length;
    count.textContent = String(active);

    empty.hidden = _recipients.length > 0;
    list.innerHTML = _recipients.map((r, i) => `
      <li class="re-item${r.is_active ? "" : " is-inactive"}"
          data-id="${r.recipient_id}" style="animation-delay:${Math.min(i * 40, 240)}ms">
        <span class="re-avatar" aria-hidden="true">${escapeHtml(recipientInitials(r.email))}</span>
        <span class="re-item-body">
          <span class="re-item-email">${escapeHtml(r.email)}</span>
          <span class="re-item-meta">
            ${r.label ? escapeHtml(r.label) + " · " : ""}
            ${r.is_active ? "receiving the daily report" : "paused"}
          </span>
        </span>
        <span class="re-item-actions">
          <button type="button" class="re-btn re-btn-ghost re-btn-sm re-toggle"
                  data-id="${r.recipient_id}">
            <i class="fa-solid ${r.is_active ? "fa-pause" : "fa-play"}"></i>
            <span>${r.is_active ? "Pause" : "Resume"}</span>
          </button>
          <button type="button" class="re-btn re-btn-danger re-btn-sm re-remove"
                  data-id="${r.recipient_id}" aria-label="Remove ${escapeHtml(r.email)}">
            <i class="fa-solid fa-trash-can"></i>
          </button>
        </span>
      </li>`).join("");
  }

  async function addRecipient(event) {
    event.preventDefault();
    const email = document.getElementById("reNewEmail");
    if (!looksLikeEmail(email.value)) {
      flagInvalid(email);
      toast("bad", "That does not look like an email address.");
      return;
    }
    const button = document.getElementById("reAddRecipient");
    busy(button, true);
    try {
      const data = await api("recipients/add/", {
        body: { email: email.value.trim(),
                label: document.getElementById("reNewLabel").value.trim() },
      });
      _recipients = data.recipients || [];
      email.value = "";
      document.getElementById("reNewLabel").value = "";
      renderRecipients();
      renderHero();
      toast("ok", data.message);
    } catch (err) {
      toast("bad", err.message);
    } finally {
      busy(button, false);
    }
  }

  async function toggleRecipient(id) {
    const current = _recipients.find(r => String(r.recipient_id) === String(id));
    if (!current) return;
    try {
      const data = await api("recipients/update/", {
        body: { recipient_id: current.recipient_id, email: current.email,
                label: current.label, is_active: !current.is_active },
      });
      _recipients = data.recipients || [];
      renderRecipients();
      renderHero();
      toast("ok", current.is_active ? "Recipient paused." : "Recipient resumed.");
    } catch (err) {
      toast("bad", err.message);
    }
  }

  async function removeRecipient(id, element) {
    const current = _recipients.find(r => String(r.recipient_id) === String(id));
    if (!current) return;
    const confirmed = await Alerts.confirm({
      title: "Remove recipient?",
      html: `<strong>${escapeHtml(current.email)}</strong> will stop receiving the daily report.`,
      icon: "warning", showCancelButton: true,
      confirmButtonText: "Remove", cancelButtonText: "Keep",
    });
    if (!confirmed) return;

    if (element) element.classList.add("is-leaving");
    try {
      const data = await api("recipients/delete/", { body: { recipient_id: current.recipient_id } });
      _recipients = data.recipients || [];
      renderRecipients();
      renderHero();
      toast("ok", data.message);
    } catch (err) {
      if (element) element.classList.remove("is-leaving");
      toast("bad", err.message);
    }
  }

  // ── Delivery log ─────────────────────────────────────────
  function renderLogStats(summary) {
    const box = document.getElementById("reLogStats");
    summary = summary || {};
    const stat = (label, value, cls) =>
      `<div class="re-stat${cls ? " " + cls : ""}">
         <span class="re-stat-label">${escapeHtml(label)}</span>
         <span class="re-stat-value">${escapeHtml(value)}</span>
       </div>`;
    box.innerHTML =
      stat("Delivered", String(summary.sent || 0), "is-sent") +
      stat("Failed", String(summary.failed || 0), "is-failed") +
      stat("Unknown", String(summary.unknown || 0), "is-failed") +
      stat("Last delivery", summary.last_sent_at ? formatStamp(summary.last_sent_at) : "never");
  }

  function renderLogRows(rows) {
    const head = document.getElementById("reLogHead");
    const body = document.getElementById("reLogBody");
    head.innerHTML = `<tr>${LOG_COLUMNS.map(c => `<th>${escapeHtml(c.label)}</th>`).join("")}</tr>`;

    if (!rows.length) {
      body.innerHTML = `<tr><td class="no-data" colspan="${LOG_COLUMNS.length}">
        Nothing has been sent yet. Use <strong>Send test email</strong> to prove the mailbox works.
      </td></tr>`;
      return;
    }

    body.innerHTML = rows.map(row => {
      const recipients = (row.recipients || []);
      const detail = logDetail(row);
      return `<tr>
        <td>${escapeHtml(formatStamp(row.created_at))}</td>
        <td>${escapeHtml(formatDay(row.report_date))}</td>
        <td><span class="re-pill re-pill-${escapeHtml(row.status)}">${escapeHtml(row.status)}</span></td>
        <td><span class="re-trigger">${escapeHtml(row.trigger_source)}</span></td>
        <td>${recipients.length
              ? escapeHtml(recipients.join(", "))
              : "<span style=\"color:var(--text-tertiary)\">none</span>"}</td>
        <td>${row.unit_count == null ? "—" : escapeHtml(String(row.unit_count))}</td>
        <td>${escapeHtml(formatMoney(row.total_profit, row.currency_code || _settings.currency_code || "PKR"))}</td>
        <td>${row.status === "sent"
              ? escapeHtml(detail)
              : `<span class="re-error">${escapeHtml(detail)}</span>`}</td>
      </tr>`;
    }).join("");
  }

  async function loadLog() {
    try {
      const data = await api(`log/?limit=50&offset=${_logOffset}`);
      document.getElementById("reLogPrev").disabled = _logOffset === 0;
      document.getElementById("reLogNext").disabled = _logOffset + 50 >= data.log.total;
      document.getElementById("reLogPage").textContent = data.log.total ? `${_logOffset + 1}–${Math.min(_logOffset + 50, data.log.total)} of ${data.log.total}` : "0 of 0";
      renderLogStats((data.log || {}).summary);
      renderLogRows(((data.log || {}).rows) || []);
    } catch (err) {
      document.getElementById("reLogBody").innerHTML =
        `<tr><td class="no-data" colspan="${LOG_COLUMNS.length}">${escapeHtml(err.message)}</td></tr>`;
    }
  }

  // ── Sending by hand ──────────────────────────────────────
  async function sendNow() {
    const button = document.getElementById("reSendNow");
    const day = document.getElementById("reManualDate").value;
    busy(button, true);
    try {
      const data = await api("send-now/", { body: { report_date: day || "" } });
      toast("ok", `${data.message} (${formatDay(data.report_date)})`);
      loadLog();
      refreshSettings();
    } catch (err) {
      toast("bad", err.message);
      loadLog();
    } finally {
      busy(button, false);
    }
  }

  async function rearmDay() {
    const button = document.getElementById("reRearm");
    const day = (_schedule && _schedule.report_date) || "";
    const confirmed = await Alerts.confirm({
      title: "Re-arm after checking the inbox?",
      html: `The schedule will deliver <strong>${escapeHtml(formatDay(day))}</strong> once more.` +
            "<br><br>Check the inbox first, especially after an unknown result. Earlier attempts remain in the log. Delivery still waits for the configured time.",
      icon: "question", showCancelButton: true,
      confirmButtonText: "Re-arm", cancelButtonText: "Leave it",
    });
    if (!confirmed) return;

    busy(button, true);
    try {
      const data = await api("rearm/", { body: { report_date: day } });
      toast("ok", data.message);
      await refreshSettings();
      loadLog();
    } catch (err) {
      toast("bad", err.message);
    } finally {
      busy(button, false);
    }
  }

  async function sendTest() {
    const button = document.getElementById("reSendTest");
    busy(button, true);
    try {
      const data = await api("send-test/", { body: {} });
      toast("ok", data.message);
      loadLog();
    } catch (err) {
      toast("bad", err.message);
      loadLog();
    } finally {
      busy(button, false);
    }
  }

  // ── Boot ─────────────────────────────────────────────────
  async function refreshSettings() {
    const data = await api("settings/");
    _schedule = data.schedule || null;
    fillMailbox(data.settings);
    renderHero();
  }

  function fillZoneList() {
    const list = document.getElementById("reZoneList");
    if (!list) return;
    let zones = [];
    try {
      zones = (Intl.supportedValuesOf ? Intl.supportedValuesOf("timeZone") : []) || [];
    } catch (e) { zones = []; }
    if (!zones.length) {
      zones = ["Asia/Karachi", "Asia/Dubai", "Asia/Kolkata", "Europe/London", "UTC"];
    }
    list.innerHTML = zones.map(z => `<option value="${escapeHtml(z)}"></option>`).join("");
  }

  document.addEventListener("DOMContentLoaded", async () => {
    fillZoneList();

    document.querySelectorAll(".re-tab").forEach(tab => {
      tab.addEventListener("click", () => selectTab(tab.dataset.panel));
    });
    window.addEventListener("resize", () => {
      moveMarker(document.querySelector(".re-tab.is-active"));
    });

    ["reSmtpHost", "reSmtpPort", "reUseTls"].forEach(id => {
      document.getElementById(id).addEventListener("input", () => {
        document.getElementById("reAdvancedSummary").textContent =
          `${document.getElementById("reSmtpHost").value || "smtp.gmail.com"} : ` +
          `${document.getElementById("reSmtpPort").value || 587} · ` +
          `${document.getElementById("reUseTls").checked ? "TLS" : "implicit TLS"}`;
      });
    });

    document.getElementById("reMailboxForm").addEventListener("submit", saveMailbox);
    document.getElementById("reAddForm").addEventListener("submit", addRecipient);
    document.getElementById("reSendNow").addEventListener("click", sendNow);
    document.getElementById("reRearm").addEventListener("click", rearmDay);
    document.getElementById("reSendTest").addEventListener("click", sendTest);
    document.getElementById("reRefreshLog").addEventListener("click", loadLog);

    document.getElementById("reLogPrev").addEventListener("click", () => { _logOffset = Math.max(0, _logOffset - 50); loadLog(); });
    document.getElementById("reLogNext").addEventListener("click", () => { _logOffset += 50; loadLog(); });
    document.querySelectorAll(".re-tab").forEach(tab => tab.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const tabs = [...document.querySelectorAll(".re-tab")];
      let index = tabs.indexOf(tab);
      index = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      tabs[index].click(); tabs[index].focus();
    }));
    document.getElementById("reReveal").addEventListener("click", function () {
      const field = document.getElementById("reAppPassword");
      const shown = field.type === "text";
      field.type = shown ? "password" : "text";
      this.setAttribute("aria-pressed", String(!shown));
      this.innerHTML = `<i class="fa-solid ${shown ? "fa-eye" : "fa-eye-slash"}"></i>`;
    });

    document.getElementById("reRecipientList").addEventListener("click", event => {
      const toggle = event.target.closest(".re-toggle");
      if (toggle) { toggleRecipient(toggle.dataset.id); return; }
      const remove = event.target.closest(".re-remove");
      if (remove) removeRecipient(remove.dataset.id, remove.closest(".re-item"));
    });

    // The switch saves on its own, because a toggle that needs a separate
    // Save is a toggle people believe they have already used.
    document.getElementById("reEnabled").addEventListener("change", async function () {
      try {
        await api("settings/save/", { body: mailboxPayload() });
        await refreshSettings();
        toast("ok", this.checked ? "Daily delivery switched on." : "Daily delivery paused.");
      } catch (err) {
        this.checked = !this.checked;
        toast("bad", err.message);
      }
    });

    try {
      const [settings, recipients] = await Promise.all([
        api("settings/"), api("recipients/"),
      ]);
      _schedule = settings.schedule || null;
      fillMailbox(settings.settings);
      _recipients = recipients.recipients || [];
      renderRecipients();
      renderHero();
      moveMarker(document.querySelector(".re-tab.is-active"));
    } catch (err) {
      toast("bad", err.message);
    }
  });
}
