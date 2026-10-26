/*
 * Draft conversion screen (Confirm Draft).
 *
 * Ported from the sibling Accounting-Plus-Inventory-System (feature commit
 * 80e8f8a). Every alert goes through the project's Alerts helper, which
 * base.html loads after this file -- so Alerts is only touched inside event
 * handlers and DOMContentLoaded.
 *
 * This is where a reservation becomes money. Everything before it moved
 * nothing: the draft held serials, the books were untouched. Pressing the
 * button here calls convert_draft_tranche, which flips the chosen units to
 * Converted and then delegates to create_sale -- so stock goes out, the
 * journal posts and the customer's balance moves.
 *
 * Three rules the screen exists to enforce before that happens:
 *
 *   1. A RATE IS REQUIRED. The draft's expected rate was an expectation; the
 *      database refuses a conversion without a real one, and so does this.
 *   2. ONE RATE PER ITEM LINE, exactly as a sale invoice works. Not per
 *      serial -- SalesItems stores one unit_price per line.
 *   3. BELOW COST IS CONFIRMED, NOT BLOCKED. Sometimes stock genuinely sells
 *      at a loss. The check is per serial rather than against a line average,
 *      because units on one line may have been bought on different invoices
 *      and an average hides the one that actually loses money.
 */

/* global Alerts */

const CONVERT_URLS = {
  get:     "/draft/get/",
  summary: "/draft/summary/",
  convert: "/draft/convert/",
};

let loadedDraft = null;

/* ── plumbing ─────────────────────────────────────────────────────────── */

function csrfToken() {
  const match = document.cookie.match(/(^|;\s*)csrftoken=([^;]*)/);
  return match ? decodeURIComponent(match[2]) : "";
}

/* Every request resolves to the {success, message} shape the views answer
   with, also for a non-JSON answer or a network failure; a middleware refusal
   ({status: "denied", message}) is marked as a failure. */
async function readJSON(response) {
  let data = null;
  try { data = await response.json(); } catch (error) { data = null; }
  if (data && typeof data === "object" && !Array.isArray(data)) {
    if (!response.ok && data.success === undefined) { data.success = false; }
    return data;
  }
  return {
    success: false,
    message: response.ok
      ? "The server sent an unexpected answer. Reload the page and try again."
      : `The server refused the request (${response.status}). Reload the page and try again.`,
  };
}

async function requestJSON(url, options) {
  try {
    return await readJSON(await fetch(url, options));
  } catch (error) {
    return { success: false, message: "Could not reach the server. Check the connection and try again." };
  }
}

function postJSON(url, payload) {
  return requestJSON(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify(payload || {}),
  });
}

function getJSON(url) {
  return requestJSON(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
}

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function money(value) {
  return Number(value).toLocaleString("en-AE",
    { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function todayISO() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 10);
}

function currencyCode() {
  const code = String(window.FINANCEE_CURRENCY || "").trim();
  return code || "PKR";
}

/* The company's DRAFT_AGE_WARNING_DAYS, rendered by the template; the
   documented default of 30 when a page does not set it. */
function ageWarningDays() {
  const days = Number(window.DRAFT_AGE_WARNING_DAYS);
  return Number.isFinite(days) && days > 0 ? days : 30;
}

/* ?draft=<number>: read once, then taken out of the address bar, so a refresh
   shows the blank screen rather than reopening the draft the link named. */
function takeLinkParam(name) {
  const params = new URLSearchParams(window.location.search);
  if (!params.has(name)) { return null; }
  const raw = (params.get(name) || "").trim();
  params.delete(name);
  const rest = params.toString();
  try {
    window.history.replaceState(window.history.state, "",
      window.location.pathname + (rest ? `?${rest}` : "") + window.location.hash);
  } catch (error) { /* the address bar is cosmetic */ }
  return raw;
}

function recordNumber(raw) {
  if (!/^[1-9][0-9]{0,9}$/.test(String(raw || ""))) { return null; }
  const number = Number(raw);
  return number <= 2147483647 ? number : null;
}

/* ── loading a draft ──────────────────────────────────────────────────── */

/* A number that is not there leaves the screen as it was. `quiet` skips the
   "not open" notice, for the reload right after a conversion, whose own
   success message must not be replaced by it. */
async function loadDraft(id, options = {}) {
  if (!id) { return false; }
  const result = await getJSON(
    `${CONVERT_URLS.get}?nav=current&draft_invoice_id=${encodeURIComponent(id)}`);
  if (!result.success) { Alerts.error(result.message, { title: "Could not load" }); return false; }
  if (!result.draft) {
    Alerts.notify(`There is no draft #${id}.`, { title: "Not found" });
    return false;
  }

  const draft = result.draft;
  if (draft.status !== "Open" && !options.quiet) {
    Alerts.warning(`Draft #${draft.draft_invoice_id} is ${draft.status_label || draft.status}. `
                   + "Only an open draft can be converted.", { title: "Nothing to convert" });
  }
  loadedDraft = draft;
  renderDraft(draft);
  return true;
}

function renderDraft(draft) {
  document.getElementById("draft_picker").value = `#${draft.draft_invoice_id}`;
  document.getElementById("draftIdBadge").textContent = `#${draft.draft_invoice_id}`;
  document.getElementById("draftCustomer").textContent = draft.Party || "—";
  const badge = document.getElementById("draftStatusBadge");
  const label = draft.status_label || draft.status || "—";
  badge.textContent = label;
  badge.className = "draft-status-badge status-"
    + String(label).toLowerCase().replace(/[^a-z]+/g, "-");

  const container = document.getElementById("convertItems");
  container.innerHTML = "";

  const lines = (draft.items || []).filter((item) => item.serials && item.serials.length);
  if (!lines.length) {
    container.innerHTML = '<p class="draft-hint">'
      + '<i class="fa-solid fa-circle-check"></i> '
      + '<span>Nothing is still reserved on this draft.</span></p>';
    recalc();
    return;
  }

  lines.forEach((item, index) => container.appendChild(buildLine(item, index)));
  recalc();
}

function buildLine(item, index) {
  /* Cost per serial, keyed by serial. reserved_details is a separate key from
     serials precisely so the draft entry screen can keep reading serials as a
     plain array of strings. */
  const costs = {};
  (item.reserved_details || []).forEach((detail) => {
    costs[detail.serial] = Number(detail.unit_cost);
  });
  const hasCost = (serial) => costs[serial] != null && Number.isFinite(costs[serial]);

  const line = document.createElement("div");
  line.className = "convert-line";
  line.dataset.index = String(index);
  line.dataset.itemName = item.item_name;

  const serials = item.serials.map((serial) => `
    <label class="convert-serial">
      <input type="checkbox" class="serial-tick" value="${escapeHtml(serial)}"
             data-cost="${hasCost(serial) ? escapeHtml(costs[serial]) : ""}" checked>
      <span class="convert-serial-no">${escapeHtml(serial)}</span>
      <span class="convert-serial-cost">cost ${hasCost(serial) ? escapeHtml(money(costs[serial])) : "—"}</span>
    </label>`).join("");

  const expected = item.unit_price != null && item.unit_price !== "";
  line.innerHTML = `
    <div class="convert-line-head">
      <div class="convert-line-item">
        <i class="fa-solid fa-box"></i> ${escapeHtml(item.item_name)}
        <span class="convert-line-count"><span class="tick-count">0</span> of ${item.serials.length} selected</span>
      </div>
      <div class="convert-line-rate">
        <label class="sale-field-label" for="rate-${index}">Agreed Rate (${escapeHtml(currencyCode())})</label>
        <input type="number" id="rate-${index}" class="sale-input line-rate"
               step="0.01" min="0" placeholder="Required"
               value="${expected ? escapeHtml(item.unit_price) : ""}">
        ${expected
          ? `<span class="convert-rate-hint">expected ${escapeHtml(money(item.unit_price))}</span>`
          : '<span class="convert-rate-hint">no expected rate was set</span>'}
      </div>
    </div>
    <div class="convert-serials">${serials}</div>
    <p class="convert-below-cost" hidden></p>`;

  line.querySelectorAll(".serial-tick").forEach((tick) => tick.addEventListener("change", recalc));
  line.querySelector(".line-rate").addEventListener("input", recalc);
  return line;
}

/* ── selection and totals ─────────────────────────────────────────────── */

function selectAll(value) {
  document.querySelectorAll("#convertItems .serial-tick").forEach((tick) => { tick.checked = value; });
  recalc();
}

let converting = false;

function recalc() {
  let selected = 0;
  let remaining = 0;
  let total = 0;
  let priced = true;

  document.querySelectorAll("#convertItems .convert-line").forEach((line) => {
    const ticks = Array.from(line.querySelectorAll(".serial-tick"));
    const chosen = ticks.filter((tick) => tick.checked);
    const rateRaw = line.querySelector(".line-rate").value.trim();
    const rate = rateRaw === "" ? null : Number(rateRaw);

    line.querySelector(".tick-count").textContent = String(chosen.length);
    selected += chosen.length;
    remaining += ticks.length - chosen.length;

    if (chosen.length) {
      if (rate === null || Number.isNaN(rate)) {
        priced = false;
      } else {
        total += rate * chosen.length;
      }
    }
    flagBelowCost(line, chosen, rate);
  });

  document.getElementById("selectedUnits").textContent = String(selected);
  document.getElementById("remainingUnits").textContent = String(remaining);
  document.getElementById("trancheTotal").textContent = money(total);

  const open = loadedDraft && loadedDraft.status === "Open";
  document.getElementById("convertBtn").disabled = converting || !(open && selected > 0 && priced);
}

/* Per serial, not against a line average: units on one line may have been
   bought on different invoices at different prices, and an average would hide
   the one that actually loses money. */
function flagBelowCost(line, chosen, rate) {
  const warning = line.querySelector(".convert-below-cost");
  if (rate === null || Number.isNaN(rate) || !chosen.length) {
    warning.hidden = true;
    return;
  }
  const losers = chosen.filter((tick) => {
    const cost = tick.dataset.cost === "" ? null : Number(tick.dataset.cost);
    return cost !== null && rate < cost;
  });
  if (!losers.length) { warning.hidden = true; return; }

  warning.hidden = false;
  warning.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> '
    + `${losers.length} serial(s) would sell below cost at ${escapeHtml(money(rate))}: `
    + losers.slice(0, 6).map((tick) => escapeHtml(tick.value)).join(", ")
    + (losers.length > 6 ? "…" : "");
}

function belowCostSerials() {
  const out = [];
  document.querySelectorAll("#convertItems .convert-line").forEach((line) => {
    const rateRaw = line.querySelector(".line-rate").value.trim();
    if (rateRaw === "") { return; }
    const rate = Number(rateRaw);
    line.querySelectorAll(".serial-tick").forEach((tick) => {
      if (!tick.checked) { return; }
      const cost = tick.dataset.cost === "" ? null : Number(tick.dataset.cost);
      if (cost !== null && rate < cost) { out.push({ serial: tick.value, rate, cost }); }
    });
  });
  return out;
}

/* ── conversion ───────────────────────────────────────────────────────── */

function collectTranche() {
  const items = [];
  document.querySelectorAll("#convertItems .convert-line").forEach((line) => {
    const serials = Array.from(line.querySelectorAll(".serial-tick"))
      .filter((tick) => tick.checked).map((tick) => tick.value);
    if (!serials.length) { return; }
    items.push({
      item_name: line.dataset.itemName,
      qty: serials.length,
      unit_price: line.querySelector(".line-rate").value.trim(),
      serials,
    });
  });
  return items;
}

async function convertTranche() {
  if (!loadedDraft || converting) { return; }
  const items = collectTranche();
  if (!items.length) {
    Alerts.warning("Tick the serials you are invoicing now.", { title: "Nothing selected" });
    return;
  }
  const invoiceDate = document.getElementById("invoice_date").value;
  if (!invoiceDate) {
    Alerts.warning("Pick the date of this sale.", { title: "Sale date required" });
    return;
  }

  /* Below cost is confirmed, never blocked: stock does sometimes sell at a
     loss, and the operator is the one who knows whether this is that. */
  const losers = belowCostSerials();
  if (losers.length) {
    const rows = losers.slice(0, 8)
      .map((l) => `${escapeHtml(l.serial)} — cost ${escapeHtml(money(l.cost))}, `
                + `selling ${escapeHtml(money(l.rate))}`)
      .join("<br>");
    const proceed = await Alerts.confirm({
      title: `${losers.length} serial(s) below cost`,
      html: `${rows}${losers.length > 8 ? "<br>…" : ""}<br><br>Raise the invoice anyway?`,
      confirmText: "Yes, invoice it",
      danger: true,
    });
    if (!proceed) { return; }
  }

  const selected = items.reduce((sum, item) => sum + item.serials.length, 0);
  const remaining = Number(document.getElementById("remainingUnits").textContent);
  const amount = document.getElementById("trancheTotal").textContent;
  const go = await Alerts.confirm({
    icon: "question",
    title: "Raise this sale invoice?",
    html: `<b>${selected}</b> unit(s) will be invoiced and leave stock.<br>`
        + `<b>${remaining}</b> unit(s) stay reserved for later.<br>`
        + `Invoice amount <b>${escapeHtml(currencyCode())} ${escapeHtml(amount)}</b>.`,
    confirmText: "Raise invoice",
  });
  if (!go) { return; }

  converting = true;
  recalc();
  let result;
  try {
    result = await postJSON(CONVERT_URLS.convert, {
      draft_invoice_id: loadedDraft.draft_invoice_id,
      invoice_date: invoiceDate,
      items,
    });
  } finally {
    converting = false;
    recalc();
  }
  if (!result.success) { Alerts.error(result.message, { title: "Not converted" }); return; }

  invalidateDraftCache();
  await loadDraft(loadedDraft.draft_invoice_id, { quiet: true });
  Alerts.success(result.message, { title: "Sale invoice created" });
}

/* ── choosing a draft ─────────────────────────────────────────────────── */

/* One cached list behind both the search box and the popup, so they can never
   show different drafts. Only drafts with something still reserved appear --
   a draft with nothing left to price is not a thing you can convert. */
let convertibleCache = null;

async function convertibleDrafts() {
  if (convertibleCache) { return convertibleCache; }
  const result = await postJSON(CONVERT_URLS.summary, {});
  if (!result.success) { Alerts.error(result.message, { title: "Could not load" }); return []; }
  convertibleCache = (result.drafts || []).filter((row) => Number(row.reserved_units) > 0);
  return convertibleCache;
}

/* Converting changes what is convertible, so the cache cannot outlive it. */
function invalidateDraftCache() { convertibleCache = null; }

function draftRowHtml(row, cls) {
  const aged = Number(row.days_outstanding || 0) >= ageWarningDays() ? " is-aged" : "";
  return `<div class="${cls}${aged}" data-draft="${escapeHtml(row.draft_invoice_id)}">
      <span class="draft-picker-id">#${escapeHtml(row.draft_invoice_id)}</span>
      <span class="draft-picker-customer">${escapeHtml(row.customer)}</span>
      <span class="draft-picker-meta">${escapeHtml(row.reserved_units)} reserved</span>
      <span class="draft-picker-meta">${escapeHtml(row.days_outstanding)}d old</span>
    </div>`;
}

async function openDraftPicker() {
  const rows = await convertibleDrafts();
  if (!rows.length) {
    Alerts.notify("No draft has anything still reserved.", { title: "Nothing to confirm" });
    return;
  }
  const head = `<div class="draft-picker-row draft-picker-head">
      <span>Draft</span><span>Customer</span><span>Reserved</span><span>Age</span>
    </div>`;
  Alerts.dialog({
    title: "Open Drafts",
    width: "40rem",
    html: `<div class="draft-picker">${head}`
        + rows.map((r) => draftRowHtml(r, "draft-picker-row")).join("")
        + "</div>",
    showConfirmButton: false,
    showCloseButton: true,
    didOpen: (popup) => {
      popup.querySelectorAll(".draft-picker-row[data-draft]").forEach((row) => {
        row.addEventListener("click", () => {
          Alerts.close();
          loadDraft(row.dataset.draft);
        });
      });
    },
  });
}

/* The search box. Matches a draft number or any part of a customer name,
   because nobody remembers draft numbers and everybody remembers the customer.
   A number typed whole puts that draft first, so "12" followed by Enter opens
   #12, not #112. */
function initDraftSearch() {
  const field = document.getElementById("draft_picker");
  const box = document.getElementById("draftSuggestions");
  if (!field || !box) { return; }
  let highlighted = -1;

  function hide() { box.style.display = "none"; highlighted = -1; }

  function pick(id) {
    hide();
    field.value = `#${id}`;
    loadDraft(id);
  }

  async function search() {
    const query = field.value.trim().replace(/^#/, "").toLowerCase();
    const rows = await convertibleDrafts();
    const matches = !query ? rows : rows.filter((row) =>
      String(row.draft_invoice_id).includes(query)
      || String(row.customer || "").toLowerCase().includes(query));
    const exact = matches.findIndex((row) => String(row.draft_invoice_id) === query);
    if (exact > 0) { matches.unshift(matches.splice(exact, 1)[0]); }

    if (!matches.length) {
      box.innerHTML = '<div class="draft-picker-empty">No open draft matches that.</div>';
      box.style.display = "block";
      highlighted = -1;
      return;
    }
    box.innerHTML = matches.map((r) => draftRowHtml(r, "draft-suggestion")).join("");
    box.querySelectorAll(".draft-suggestion").forEach((row) => {
      row.addEventListener("click", () => pick(row.dataset.draft));
    });
    box.style.display = "block";
    highlighted = -1;
  }

  field.addEventListener("input", search);
  field.addEventListener("focus", search);

  field.addEventListener("keydown", (event) => {
    const items = Array.from(box.querySelectorAll(".draft-suggestion"));
    if (!items.length || box.style.display === "none") { return; }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      highlighted = (highlighted + step + items.length) % items.length;
      items.forEach((el, i) => el.classList.toggle("active", i === highlighted));
      items[highlighted].scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter") {
      event.preventDefault();
      pick(items[highlighted >= 0 ? highlighted : 0].dataset.draft);
    } else if (event.key === "Escape") {
      hide();
    }
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest("#draft_picker, #draftSuggestions")) { hide(); }
  });
}

/* ── boot ─────────────────────────────────────────────────────────────── */

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("invoice_date").value = todayISO();
  initDraftSearch();

  /* /draft/convert/screen/?draft=<number> opens that draft. A number that is
     not there says so and leaves the screen ready to choose one. */
  const linked = takeLinkParam("draft");
  if (linked) {
    const number = recordNumber(linked);
    if (number) {
      loadDraft(number);
    } else {
      Alerts.notify(`There is no draft #${linked.slice(0, 40)}.`, { title: "Not found" });
    }
  }
});
