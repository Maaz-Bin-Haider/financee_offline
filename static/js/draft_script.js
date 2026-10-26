/*
 * Draft invoice entry screen (Draft Invoices).
 *
 * Ported from the sibling Accounting-Plus-Inventory-System (feature commit
 * 80e8f8a, plus its later escaping and "a number that is not there" fixes).
 * Every alert goes through the project's Alerts helper (static/js/alerts.js),
 * which base.html loads after this file -- so Alerts is only ever touched
 * inside event handlers and DOMContentLoaded, never at parse time.
 *
 * A draft RESERVES serial numbers for a named customer. Nothing leaves stock,
 * no invoice is raised and no balance moves until a tranche is converted --
 * which happens on the Confirm Draft screen, not this one.
 *
 * The row markup is deliberately the Sale screen's: .item_name_field /
 * .unit_price / .qty-box / .serials / .row-actions, so the card, the rows and
 * their responsive collapse come from purchasing_styling.css.
 *
 * Two things differ from the Sale screen and both are load-bearing:
 *
 *   - the rate is OPTIONAL. A blank Expected Rate is the normal case here, not
 *     an error, and it is sent as null rather than 0: "not agreed yet" and
 *     "agreed at nothing" are different facts and the database stores them
 *     differently;
 *   - a serial that is already reserved is refused WITH the customer holding
 *     it, so the operator learns who to ask rather than only that they cannot
 *     have it.
 */

/* global Alerts, DraftReports, FinanceePdf, SmartDescriptions */

const DRAFT_URLS = {
  save:    "/draft/save/",
  del:     "/draft/delete/",
  release: "/draft/release/",
  cancel:  "/draft/cancel/",
  get:     "/draft/get/",
  summary: "/draft/summary/",
  lookup:  "/draft/serial/lookup/",
};

const SERIAL_SEPARATORS_RE = /[\n\r\t,;]/;

/* ── plumbing ─────────────────────────────────────────────────────────── */

function csrfToken() {
  const match = document.cookie.match(/(^|;\s*)csrftoken=([^;]*)/);
  return match ? decodeURIComponent(match[2]) : "";
}

/* Every request resolves to the {success, message} shape the views answer
   with -- also when the answer is not JSON (a lost session, a proxy error
   page) or the network is down -- so a failure is always told, never
   swallowed. A middleware refusal ({status: "denied", message}) has no
   `success` key and is marked as a failure here. */
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

/* Server text reaches HTML only through this: a party name, an item name, a
   serial or a description is text, never markup. */
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
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

function parseSerialList(text) {
  return Array.from(new Set(String(text || "").split(/[\s,;]+/)
    .map((s) => s.trim()).filter(Boolean)));
}

/* ?open=<number>: read once, then taken out of the address bar, so a refresh
   shows the blank screen rather than reopening the record the link named. */
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

/* A record number: a whole number from 1 to the largest integer id. */
function recordNumber(raw) {
  if (!/^[1-9][0-9]{0,9}$/.test(String(raw || ""))) { return null; }
  const number = Number(raw);
  return number <= 2147483647 ? number : null;
}

/* ── rows ─────────────────────────────────────────────────────────────── */

function addItemRow(shouldFocus = true) {
  const row = document.createElement("div");
  row.className = "item-row";
  row.innerHTML = `
    <div class="item_name_field">
      <input type="hidden" class="item_name" value="">
      <div class="item-name-display empty">— awaiting serial —</div>
    </div>
    <input type="number" class="unit_price" step="0.01" min="0" placeholder="Optional" value="">
    <input type="number" class="qty-box" readonly value="0">
    <div></div>
    <div class="serials"></div>
    <div class="row-actions">
      <button type="button" class="custom-btn add-serial">＋ Serial</button>
      <button type="button" class="custom-btn remove-serial">− Serial</button>
      <button type="button" class="custom-btn remove-item">✕ Remove</button>
    </div>`;

  row.querySelector(".add-serial").onclick = () => addSerialInput(row);
  row.querySelector(".remove-serial").onclick = () => removeSerialInput(row);
  row.querySelector(".remove-item").onclick = () => { row.remove(); recalcTotals(); };
  row.querySelector(".unit_price").oninput = () => recalcTotals();

  document.getElementById("items").appendChild(row);
  addSerialInput(row, false);
  if (shouldFocus) {
    const first = row.querySelector(".serials input");
    if (first) { first.focus(); }
  }
  return row;
}

function addSerialInput(row, autoFocus = true, value = "") {
  const serialsDiv = row.querySelector(".serials");
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "Enter serial…";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.value = value;
  input.oninput = () => recalcTotals();
  input.addEventListener("change", () => commitSerial(input, row));
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.isComposing) { return; }
    event.preventDefault();
    /* A scanner ends every serial with Enter. Moving on to the row's next
       empty box (or a new one) commits this one -- its change event fires on
       the way out -- and leaves the cursor where the next scan lands, rather
       than nowhere. An empty box stays put. */
    if (!input.value.trim() || input.readOnly) { return; }
    nextEmptySerialInput(row, input).focus();
  });
  input.addEventListener("paste", (event) => {
    /* A locked draft's boxes are read-only; a paste there must not add lines
       through the bulk path either. */
    if (input.readOnly) { return; }
    const text = (event.clipboardData || window.clipboardData).getData("text");
    if (text && SERIAL_SEPARATORS_RE.test(text)) {
      event.preventDefault();
      /* Deliberately NOT cleared. preventDefault already stopped the browser
         writing the pasted text here, so the box still holds whatever it held:
         empty, and placeSerial fills it; already committed, and that serial
         survives instead of being destroyed by a paste aimed at the row. */
      processBulkSerialsText(text, row);
    }
  });
  serialsDiv.appendChild(input);
  recalcTotals();
  if (autoFocus) { input.focus(); }
  return input;
}

function nextEmptySerialInput(row, after) {
  const boxes = Array.from(row.querySelectorAll(".serials input"));
  const later = boxes.slice(boxes.indexOf(after) + 1).find((box) => !box.value.trim());
  return later || addSerialInput(row, false);
}

/* Put a serial in the row's first EMPTY box, and only add a box when they are
   all full. A serial copied from a spreadsheet carries a trailing newline,
   which routes it through the bulk path, and that path must reuse the box the
   operator pasted into rather than leave it empty beside a new one. */
function firstEmptySerialInput(row) {
  return Array.from(row.querySelectorAll(".serials input"))
    .find((input) => !input.value.trim()) || null;
}

function placeSerial(row, serial) {
  const input = firstEmptySerialInput(row) || addSerialInput(row, false);
  input.value = serial;
  recalcTotals();
  return input;
}

function removeSerialInput(row) {
  const serialsDiv = row.querySelector(".serials");
  if (serialsDiv.lastChild) {
    serialsDiv.removeChild(serialsDiv.lastChild);
    recalcTotals();
  }
}

function rowSerials(row) {
  return Array.from(row.querySelectorAll(".serials input"))
    .map((input) => input.value.trim()).filter(Boolean);
}

function allSerials() {
  return Array.from(document.querySelectorAll("#items .serials input"))
    .map((input) => input.value.trim()).filter(Boolean);
}

function setItemName(row, name) {
  row.querySelector(".item_name").value = name;
  const display = row.querySelector(".item-name-display");
  display.classList.remove("empty");
  display.textContent = name;
}

/* ── serial validation ────────────────────────────────────────────────── */

async function commitSerial(input, row) {
  const serial = input.value.trim();
  if (!serial) { recalcTotals(); return false; }

  const duplicates = allSerials().filter((s) => s === serial);
  if (duplicates.length > 1) {
    Alerts.warning(`Serial "${serial}" is already on this draft.`,
                   { title: "Already on this draft" });
    input.value = "";
    recalcTotals();
    return false;
  }

  const result = await postJSON(DRAFT_URLS.lookup, { serial });
  /* The box may have been edited while the lookup was out. An answer about a
     serial it no longer holds is dropped rather than written over the newer
     one (the newer value has its own lookup on the way). */
  if (input.value.trim() !== serial) { return "stale"; }

  if (!result.success) {
    if (result.reserved) {
      Alerts.warning(result.message, { title: "Reserved for another customer" });
    } else {
      Alerts.error(result.message, { title: "Serial unavailable" });
    }
    input.value = "";
    recalcTotals();
    return false;
  }

  const existing = row.querySelector(".item_name").value.trim();
  if (!existing) {
    setItemName(row, result.item_name);
  } else if (existing !== result.item_name) {
    /* Not an error. Scanning a bin of mixed stock is the normal way this
       screen is used. File it on the right line instead and say where it went.

       Exactly one existing line for that item -- use it. Zero, or MORE than
       one -- start a fresh line. Two lines of one item is legitimate here (the
       same phone agreed at two different rates), and silently guessing which
       of them a serial belongs to would put it on the wrong rate. */
    input.value = "";
    const matches = rowsForItem(result.item_name);
    const target = matches.length === 1
      ? matches[0]
      : newRowForItem(result.item_name);
    placeSerial(target, serial);
    recalcTotals();
    Alerts.notify(`${serial} is a ${result.item_name}, not a ${existing}.`,
                  { title: "Filed on its own line" });
    return "moved";
  }
  recalcTotals();
  return true;
}

function rowsForItem(name) {
  return Array.from(document.querySelectorAll("#items .item-row"))
    .filter((row) => row.querySelector(".item_name").value.trim() === name);
}

function newRowForItem(name) {
  const row = addItemRow(false);
  setItemName(row, name);
  return row;
}

async function processBulkSerialsText(text, preferRow) {
  const serials = String(text || "").split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean);
  if (!serials.length) { return; }
  const row = preferRow || document.querySelector("#items .item-row:last-child") || addItemRow(false);

  const rejected = [];
  for (const serial of serials) {
    /* Sequential on purpose: each lookup may bind this row's item name, and
       firing them in parallel would race over it. */
    const reused = firstEmptySerialInput(row);
    const input = reused || addSerialInput(row, false);
    input.value = serial;
    // eslint-disable-next-line no-await-in-loop
    const ok = await commitSerial(input, row);
    if (ok === "moved") {
      /* commitSerial emptied this box and put the serial on the right line.
         A box we added for it is now spare; a box the operator was already
         typing in is theirs, so it stays. */
      if (!reused) { input.remove(); }
    } else if (!ok) {
      if (reused) { input.value = ""; } else { input.remove(); }
      rejected.push(serial);
    }
  }
  recalcTotals();
  if (rejected.length) {
    Alerts.warning(rejected.slice(0, 12).join(", ") + (rejected.length > 12 ? "…" : ""),
                   { title: `${rejected.length} serial(s) not added` });
  }
}

async function openBulkSerialsDialog() {
  const answer = await Alerts.dialog({
    title: "📋 Bulk Paste Serials",
    input: "textarea",
    inputPlaceholder: "Paste one serial per line, or straight from an Excel column…",
    showCancelButton: true,
    confirmButtonText: "Add",
    confirmButtonColor: Alerts.PALETTE.primary,
  });
  if (answer.isConfirmed && answer.value) { await processBulkSerialsText(answer.value, null); }
}

/* ── totals ───────────────────────────────────────────────────────────── */

function recalcTotals() {
  let units = 0;
  let unpriced = 0;
  let value = 0;

  document.querySelectorAll("#items .item-row").forEach((row) => {
    const qty = rowSerials(row).length;
    row.querySelector(".qty-box").value = qty;
    units += qty;

    const raw = row.querySelector(".unit_price").value.trim();
    if (raw === "") {
      if (qty > 0) { unpriced += 1; }
    } else {
      value += Number(raw) * qty;
    }
  });

  document.getElementById("totalQtyCount").textContent = String(units);
  document.getElementById("unpricedLines").textContent = String(unpriced);
  document.getElementById("indicativeValue").textContent =
    value.toLocaleString("en-AE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/* ── save ─────────────────────────────────────────────────────────────── */

function collectItems() {
  const items = [];
  document.querySelectorAll("#items .item-row").forEach((row) => {
    const serials = rowSerials(row);
    if (!serials.length) { return; }
    const raw = row.querySelector(".unit_price").value.trim();
    items.push({
      item_name: row.querySelector(".item_name").value.trim(),
      qty: serials.length,
      unit_price: raw === "" ? null : raw,
      serials,
    });
  });
  return items;
}

let savingDraft = false;

async function submitDraft(event) {
  event.preventDefault();
  if (savingDraft) { return; }
  const items = collectItems();
  if (!items.length) {
    Alerts.warning("Add at least one serial number.", { title: "Nothing to reserve" });
    return;
  }
  const existingId = currentDraftId();
  savingDraft = true;
  let result;
  try {
    result = await postJSON(DRAFT_URLS.save, {
      draft_invoice_id: existingId || null,
      party_name: document.getElementById("search_name").value.trim(),
      draft_date: document.getElementById("draft_date").value,
      description: document.getElementById("draft_description").value,
      items,
    });
  } finally {
    savingDraft = false;
  }

  /* The server says which it did; the local id is only the fallback, because
     the two can disagree -- a draft deleted in another tab comes back created
     rather than updated, and the message should say what actually happened. */
  const wasUpdate = typeof result.created === "boolean"
    ? !result.created
    : Boolean(existingId);

  if (!result.success) {
    Alerts.error(result.message, { title: wasUpdate ? "Draft not updated" : "Draft not saved" });
    return;
  }

  /* Straight back to a blank screen, so the next draft does not begin by
     hand-clearing a form that still holds the last customer's serials. The
     draft number is in the message, and Previous still reaches it. */
  newDraft();
  Alerts.success(result.message, { title: wasUpdate ? "Draft updated" : "Draft saved" });
}

/* ── lifecycle ────────────────────────────────────────────────────────── */

function currentDraftId() {
  return document.getElementById("current_draft_id").value;
}

async function deleteDraft() {
  const id = currentDraftId();
  if (!id) { Alerts.notify("This draft has not been saved yet.", { title: "Nothing to delete" }); return; }
  const confirmed = await Alerts.confirm({
    title: "Delete this draft?",
    text: "Every reserved serial returns to free stock. This cannot be undone.",
    confirmText: "Delete",
    danger: true,
  });
  if (!confirmed) { return; }
  const result = await postJSON(DRAFT_URLS.del, { draft_invoice_id: id });
  if (!result.success) { Alerts.error(result.message, { title: "Not deleted" }); return; }
  newDraft();
  Alerts.success(result.message, { title: "Draft deleted" });
}

async function cancelDraft() {
  const id = currentDraftId();
  if (!id) { Alerts.notify("This draft has not been saved yet.", { title: "Nothing to cancel" }); return; }
  const confirmed = await Alerts.confirm({
    title: "Cancel this draft?",
    text: "Everything still reserved is released to free stock. Any tranche already "
      + "invoiced stays exactly as it is.",
    confirmText: "Cancel draft",
    cancelText: "Keep it",
    danger: true,
  });
  if (!confirmed) { return; }
  const result = await postJSON(DRAFT_URLS.cancel, { draft_invoice_id: id });
  if (!result.success) { Alerts.error(result.message, { title: "Not cancelled" }); return; }
  await loadDraft("current", id, { quiet: true });
  Alerts.success(result.message, { title: "Draft cancelled" });
}

async function releaseSerials() {
  const id = currentDraftId();
  if (!id) { Alerts.notify("This draft has not been saved yet.", { title: "Nothing to release" }); return; }
  const answer = await Alerts.dialog({
    title: "Release serials",
    text: "These return to free stock and can then be sold to anyone.",
    input: "textarea",
    inputPlaceholder: "One serial per line…",
    showCancelButton: true,
    confirmButtonText: "Release",
    confirmButtonColor: Alerts.PALETTE.error,
  });
  if (!answer.isConfirmed || !answer.value) { return; }
  const serials = parseSerialList(answer.value);
  if (!serials.length) { return; }

  const shown = serials.slice(0, 12).join(", ") + (serials.length > 12 ? "…" : "");
  const confirmed = await Alerts.confirm({
    title: `Release ${serials.length} serial(s)?`,
    text: `${shown} will leave draft #${id} and go back to free stock, where anyone can sell them.`,
    confirmText: "Release",
    danger: true,
  });
  if (!confirmed) { return; }

  const result = await postJSON(DRAFT_URLS.release, { draft_invoice_id: id, serials });
  if (!result.success) { Alerts.error(result.message, { title: "Not released" }); return; }
  await loadDraft("current", id, { quiet: true });
  Alerts.success(result.message, { title: "Released" });
}

/* ── navigation ───────────────────────────────────────────────────────── */

/* The action word has to match what pressing it does: editing a saved draft
   must not still offer "Save Draft". */
function setSaveLabel(isExisting) {
  const button = document.getElementById("saveBtn");
  if (!button) { return; }
  button.innerHTML = isExisting
    ? '<i class="fa-solid fa-pen-to-square"></i> Update Draft'
    : '<i class="fa-solid fa-floppy-disk"></i> Save Draft';
}

function refreshDescriptions() {
  if (window.SmartDescriptions) { SmartDescriptions.refreshAll(); }
}

function newDraft() {
  document.getElementById("items").innerHTML = "";
  document.getElementById("current_draft_id").value = "";
  document.getElementById("draftIdBadge").textContent = "#NEW";
  document.getElementById("entryByName").textContent = "—";
  document.getElementById("search_name").value = "";
  document.getElementById("draft_description").value = "";
  document.getElementById("draft_date").value = todayISO();
  setStatus("Open");
  setSaveLabel(false);
  unlock();
  /* Ready for the first scan: a blank draft always offers one empty line. */
  addItemRow(false);
  recalcTotals();
  refreshDescriptions();
}

function setStatus(label) {
  const badge = document.getElementById("draftStatusBadge");
  badge.textContent = label;
  badge.className = "draft-status-badge status-"
    + String(label).toLowerCase().replace(/[^a-z]+/g, "-");
}

async function navigateDraft(direction) {
  const id = currentDraftId();
  if (!id) { await loadDraft("last"); return; }
  await loadDraft(direction, id);
}

/* Returns true when a draft was shown. A number that is not there leaves the
   screen exactly as it was: the hidden id is only written once a draft
   arrives. `quiet` skips the not-found notice, for a reload after an action
   whose own message is about to be shown. */
async function loadDraft(nav, id, options = {}) {
  const params = new URLSearchParams({ nav });
  if (id) { params.set("draft_invoice_id", id); }
  const result = await getJSON(`${DRAFT_URLS.get}?${params.toString()}`);
  if (!result.success) { Alerts.error(result.message, { title: "Could not load" }); return false; }
  if (!result.draft) {
    if (!options.quiet) {
      /* "current" asks for one number (a History pick, a ?open= link); the
         others walk the list. */
      if (nav === "current") {
        Alerts.notify(`There is no draft #${id}.`, { title: "Not found" });
      } else if (nav !== "last") {
        Alerts.notify("There is no draft that way.", { title: "End of the list" });
      } else {
        Alerts.notify("There is no open draft yet.", { title: "No drafts" });
      }
    }
    return false;
  }
  renderDraft(result.draft);
  return true;
}

function renderDraft(draft) {
  document.getElementById("current_draft_id").value = draft.draft_invoice_id;
  document.getElementById("draftIdBadge").textContent = `#${draft.draft_invoice_id}`;
  document.getElementById("search_name").value = draft.Party || "";
  document.getElementById("draft_date").value = draft.draft_date || "";
  document.getElementById("draft_description").value = draft.description || "";
  document.getElementById("entryByName").textContent = draft.created_by || "—";
  setStatus(draft.status_label || draft.status || "Open");
  setSaveLabel(true);

  document.getElementById("items").innerHTML = "";
  (draft.items || []).forEach((item) => {
    if (!item.serials || !item.serials.length) { return; }
    const row = addItemRow(false);
    row.querySelector(".serials").innerHTML = "";
    setItemName(row, item.item_name);
    if (item.unit_price != null) { row.querySelector(".unit_price").value = item.unit_price; }
    item.serials.forEach((serial) => addSerialInput(row, false, serial));
  });
  recalcTotals();
  refreshDescriptions();
  applyLock(draft);
}

/* A draft stops being editable the moment a tranche is invoiced. The database
   enforces it either way; disabling the controls means the operator is not
   invited to try and then told no. Release and Cancel stay available while
   the draft is open. */
function applyLock(draft) {
  const converted = Number(draft.converted_units || 0) > 0;
  const closed = draft.status !== "Open";
  const locked = closed || converted;

  setDisabled("saveBtn", locked);
  setDisabled("deleteBtn", locked);
  setDisabled("releaseBtn", closed);
  setDisabled("cancelBtn", closed);
  setDisabled("addItemBtn", locked);
  setDisabled("bulkPasteBtn", locked);

  document.querySelectorAll("#items input, #search_name, #draft_date, #draft_description")
    .forEach((el) => { el.readOnly = locked; });
  document.querySelectorAll("#items .custom-btn")
    .forEach((el) => { el.disabled = locked; });
}

function unlock() {
  ["saveBtn", "deleteBtn", "releaseBtn", "cancelBtn", "addItemBtn", "bulkPasteBtn"]
    .forEach((id) => setDisabled(id, false));
  document.querySelectorAll("#items input, #search_name, #draft_date, #draft_description")
    .forEach((el) => { el.readOnly = false; });
}

function setDisabled(id, value) {
  const element = document.getElementById(id);
  if (element) { element.disabled = value; }
}

/* ── history ──────────────────────────────────────────────────────────── */

async function draftHistory() { await showSummary({}); }

async function draftDateWise() {
  const today = todayISO();
  /* Laid out like the Sale screen's range picker -- labelled fields and a
     verb on the button -- rather than two bare date boxes. */
  const answer = await Alerts.dialog({
    title: "📅 Select Date Range",
    html: `
      <div class="draft-range">
        <label for="fromDate">From Date</label>
        <input type="date" id="fromDate" class="swal2-input">
        <label for="toDate">To Date</label>
        <input type="date" id="toDate" class="swal2-input" value="${today}">
      </div>`,
    focusConfirm: false,
    showCancelButton: true,
    confirmButtonText: "Fetch Drafts",
    confirmButtonColor: Alerts.PALETTE.primary,
    preConfirm: () => {
      const from = document.getElementById("fromDate").value;
      const to = document.getElementById("toDate").value;
      if (!from || !to) {
        Alerts.raw.showValidationMessage("Pick both dates.");
        return false;
      }
      if (from > to) {
        Alerts.raw.showValidationMessage("The From date is after the To date.");
        return false;
      }
      return { start_date: from, end_date: to };
    },
  });
  if (answer.isConfirmed && answer.value) { await showSummary(answer.value); }
}

/* The rows behind the open history popup. The PDF export reads THIS rather
   than re-querying or scraping the table back out of the DOM, so the sheet and
   the page can never disagree about what was listed. */
let historyRows = [];
let historyRange = {};

function savePdf(options, filename) {
  if (!window.jspdf || !window.jspdf.jsPDF || typeof FinanceePdf === "undefined") {
    Alerts.error("The PDF library did not load. Check the connection and reload the page.",
                 { title: "PDF unavailable" });
    return;
  }
  try {
    FinanceePdf.save(Object.assign(options, { jsPDF: window.jspdf.jsPDF, filename }));
  } catch (error) {
    Alerts.error("The PDF could not be built. Reload the page and try again.",
                 { title: "PDF failed" });
  }
}

/* Document PDFs (proforma, history export) follow the company's
   pdf_export.documents switch. */
function documentPdfAllowed() {
  return !(typeof window.financeeFeatureEnabled === "function"
           && !window.financeeFeatureEnabled("pdf_export", "documents"));
}

function draftHistoryPdf() {
  if (!documentPdfAllowed() || !historyRows.length) { return; }
  const ranged = historyRange.start_date && historyRange.end_date;
  const options = DraftReports.historyPdfOptions(historyRows, {
    from: historyRange.start_date,
    to: historyRange.end_date,
  });
  savePdf(options, ranged
    ? `Draft_History_${historyRange.start_date}_to_${historyRange.end_date}.pdf`
    : "Draft_History.pdf");
}

async function showSummary(range) {
  const result = await postJSON(DRAFT_URLS.summary, range);
  if (!result.success) { Alerts.error(result.message, { title: "Could not load" }); return; }
  const rows = result.drafts || [];
  if (!rows.length) { Alerts.notify("Nothing to show for that range.", { title: "No drafts" }); return; }

  historyRows = rows;
  historyRange = range || {};

  /* The date reads the way the PDFs read it; every value from the server is
     escaped, including the customer copied into the row's search key. */
  const body = rows.map((row, index) => `
    <tr class="draft-row" data-draft-id="${escapeHtml(row.draft_invoice_id)}"
        data-customer="${escapeHtml(String(row.customer == null ? "" : row.customer).toLowerCase())}">
      <td>${index + 1}</td>
      <td><b>#${escapeHtml(row.draft_invoice_id)}</b></td>
      <td>${escapeHtml(DraftReports.formatDate(row.draft_date))}</td>
      <td>${escapeHtml(row.customer)}</td>
      <td>${escapeHtml(row.status_label)}</td>
      <td class="num">${escapeHtml(row.reserved_units)}</td>
      <td class="num mono">${Number(row.unpriced_lines) > 0
        ? "—" : escapeHtml(DraftReports.formatMoney(row.indicative_value))}</td>
    </tr>`).join("");

  const html = `
    <div class="draft-history">
      <div class="sh-bar">
        <input type="text" class="sh-search" placeholder="🔍 Search by customer…"
               aria-label="Search by customer">
        ${documentPdfAllowed() ? `<button type="button" class="sh-pdf"><i class="fa-solid fa-file-pdf"></i> Export PDF</button>` : ""}
      </div>
      <div class="sh-wrap">
        <table class="sh-table">
          <thead><tr><th>#</th><th>Draft</th><th>Date</th><th>Customer</th>
            <th>Status</th><th class="num">Reserved</th>
            <th class="num">Indicative (${escapeHtml(currencyCode())})</th></tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </div>`;

  Alerts.dialog({
    title: "📜 Draft History",
    html,
    width: "780px",
    focusConfirm: false,
    allowOutsideClick: false,
    allowEscapeKey: true,
    didOpen: (popup) => {
      const search = popup.querySelector(".sh-search");
      const lines = Array.from(popup.querySelectorAll("tr.draft-row"));
      search.addEventListener("input", () => {
        const needle = search.value.toLowerCase().trim();
        lines.forEach((line) => { line.hidden = !line.dataset.customer.includes(needle); });
      });
      popup.querySelector(".sh-pdf")?.addEventListener("click", draftHistoryPdf);
      popup.querySelector(".sh-table tbody").addEventListener("click", (event) => {
        const line = event.target.closest("tr.draft-row");
        if (line) { pickDraft(line.dataset.draftId); }
      });
      setTimeout(() => search.focus(), 80);
    },
  });
}

function pickDraft(id) {
  Alerts.close();
  loadDraft("current", id);
}

/* ── Customer autocomplete ────────────────────────────────────────────── */

/* The Sale screen's #suggestions box with .suggestion-item rows, on the
   ?receivable=1 list (Customer and Both parties, never a cash account): a
   draft always reserves for a named customer who can be invoiced on credit. */
function initPartyAutocomplete() {
  const field = document.getElementById("search_name");
  const box = document.getElementById("suggestions");
  if (!field || !box) { return; }

  const baseUrl = field.dataset.autocompleteUrl;
  let highlighted = -1;
  let asked = 0;

  function hide() { box.style.display = "none"; highlighted = -1; }

  function choose(name) {
    field.value = name;
    hide();
    /* Straight on to the first serial: the customer is the only thing typed
       on this screen, everything else is scanned. */
    const serial = document.querySelector("#items .item-row .serials input");
    if (serial) { serial.focus(); }
  }

  function highlight(items, index) {
    items.forEach((el, i) => el.classList.toggle("highlight", i === index));
    if (items[index]) { items[index].scrollIntoView({ block: "nearest" }); }
  }

  field.addEventListener("input", async () => {
    const query = field.value.trim();
    const ticket = ++asked;
    if (!query || field.readOnly) { hide(); return; }
    let names = [];
    try {
      const url = new URL(baseUrl, window.location.origin);
      url.searchParams.set("term", query);
      const response = await fetch(url.toString(),
        { headers: { "X-Requested-With": "XMLHttpRequest" } });
      names = response.ok ? await response.json() : [];
    } catch (error) {
      names = [];
    }
    /* A later keystroke has asked since: its answer is the one to show. */
    if (ticket !== asked) { return; }
    box.innerHTML = "";
    if (!Array.isArray(names) || !names.length) { hide(); return; }
    names.forEach((name) => {
      const row = document.createElement("div");
      row.className = "suggestion-item";
      row.textContent = name;
      row.addEventListener("click", () => choose(name));
      box.appendChild(row);
    });
    box.style.display = "block";
    highlighted = -1;
  });

  field.addEventListener("keydown", (event) => {
    const items = Array.from(box.querySelectorAll(".suggestion-item"));
    if (!items.length || box.style.display === "none") { return; }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      highlighted = (highlighted + 1) % items.length;
      highlight(items, highlighted);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      highlighted = (highlighted - 1 + items.length) % items.length;
      highlight(items, highlighted);
    } else if (event.key === "Enter") {
      if (highlighted >= 0 || items.length === 1) {
        event.preventDefault();
        choose(items[Math.max(highlighted, 0)].textContent);
      }
    } else if (event.key === "Escape") {
      hide();
    }
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest("#search_name, #suggestions")) { hide(); }
  });
}

/* ── Proforma Invoice ─────────────────────────────────────────────────── */

/* Goes through the shared PDF theme (report_pdf.js), slate rather than the
   sale's blue, deliberately: a proforma that looks like the invoice invites
   being paid against, and the notice on it says in words that no payment is
   due. It prints what is on screen, so save first. */
function downloadProforma() {
  if (!documentPdfAllowed()) { return; }
  const id = currentDraftId();
  if (!id) {
    Alerts.notify("Save the draft first.", { title: "Nothing to print" });
    return;
  }
  const draft = {
    draft_invoice_id: id,
    Party: document.getElementById("search_name").value,
    draft_date: document.getElementById("draft_date").value,
    status_label: document.getElementById("draftStatusBadge").textContent,
    items: collectItems(),
  };
  savePdf(DraftReports.proformaPdfOptions(draft, {}), `Proforma_${id}.pdf`);
}

/* ── boot ─────────────────────────────────────────────────────────────── */

document.addEventListener("DOMContentLoaded", () => {
  /* Open ready for a NEW draft, not on the last saved one. Previous or Next
     from this blank state still loads the most recent open draft --
     navigateDraft() falls back to "last" when no draft is on screen. */
  newDraft();
  initPartyAutocomplete();

  /* A link to one draft (/draft/?open=<number>) opens it, as a pick from
     History does. The screen is already blank underneath, so a number that is
     not there leaves it ready for a new draft. */
  const linked = takeLinkParam("open");
  if (linked) {
    const number = recordNumber(linked);
    if (number) {
      loadDraft("current", number);
    } else {
      Alerts.notify(`There is no draft #${linked.slice(0, 40)}.`, { title: "Not found" });
    }
  }
});
