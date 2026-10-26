/*
 * Confirmed Draft Return screen.
 *
 * Ported from the sibling Accounting-Plus-Inventory-System (feature commit
 * 80e8f8a, plus its later "a number that is not there" wording). Every alert
 * goes through the project's Alerts helper, which base.html loads after this
 * file -- so Alerts is only touched inside event handlers and DOMContentLoaded.
 * One addition to the source: the Description box is now saved (sent as
 * `description`) and shown again when a return is loaded; the source screen
 * had the box but never sent it.
 *
 * Returns goods that were sold from a draft invoice. Its own document with its
 * own number series -- but the accounting underneath is an ordinary sale
 * return, so every ledger and report that reads SalesReturns sees it.
 *
 * Two behaviours are the point of this screen:
 *
 *   - THE CUSTOMER IS LOCKED, filled from the first serial rather than typed.
 *     A serial's active sale decides the only party that may return it, so
 *     asking the operator to type it too would only be a chance to get it
 *     wrong.
 *   - A SERIAL FROM AN ORDINARY SALE IS REFUSED, and pointed at the Sale
 *     Return screen. The database refuses it either way; saying so before the
 *     attempt is better than surfacing the refusal afterwards.
 */

/* global Alerts, DraftReports, FinanceePdf, SmartDescriptions */

const DR_URLS = {
  save:    "/draft/return/save/",
  del:     "/draft/return/delete/",
  get:     "/draft/return/get/",
  summary: "/draft/return/summary/",
  lookup:  "/draft/return/serial/lookup/",
};

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
  return Number(value || 0).toLocaleString("en-AE",
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

/* ?open=<number>: read once, then taken out of the address bar, so a refresh
   shows the blank screen rather than reopening the return the link named. */
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

/* ── serial rows ──────────────────────────────────────────────────────── */

function addSerialRow(autoFocus = true, prefill) {
  const data = prefill || {};
  const row = document.createElement("div");
  row.className = "dr-serial-row";
  row.innerHTML = `
    <input type="text" class="dr-serial" placeholder="Enter serial number"
           value="${escapeHtml(data.serial_number || "")}" autocomplete="off"
           spellcheck="false" aria-label="Serial number">
    <input type="text" class="dr-item" readonly placeholder="—"
           value="${escapeHtml(data.item_name || "")}" aria-label="Item name">
    <input type="text" class="dr-price" readonly placeholder="—"
           value="${data.sold_price != null ? escapeHtml(money(data.sold_price)) : ""}" aria-label="Sold price">
    <input type="text" class="dr-draft" readonly placeholder="—"
           value="${data.draft_invoice_id ? "#" + escapeHtml(data.draft_invoice_id) : ""}" aria-label="From draft">
    <button type="button" class="custom-btn remove-serial" title="Remove this serial">
      <i class="fa-solid fa-xmark"></i>
    </button>`;
  if (data.sold_price != null) { row.dataset.soldPrice = String(data.sold_price); }

  const serialInput = row.querySelector(".dr-serial");
  serialInput.addEventListener("change", () => lookupSerial(serialInput, row));
  serialInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.isComposing) { return; }
    event.preventDefault();
    /* Enter commits and moves on to the next empty serial row (or a new one),
       so a scanner's next serial lands in a box rather than nowhere. Leaving
       the box fires its change event, which runs the lookup. */
    if (!serialInput.value.trim()) { return; }
    nextEmptySerialInput(serialInput).focus();
  });
  row.querySelector(".remove-serial").onclick = () => { row.remove(); recalc(); };

  document.getElementById("serials").appendChild(row);
  recalc();
  if (autoFocus) { serialInput.focus(); }
  return row;
}

function nextEmptySerialInput(after) {
  const boxes = Array.from(document.querySelectorAll("#serials .dr-serial"));
  const later = boxes.slice(boxes.indexOf(after) + 1).find((box) => !box.value.trim());
  return later || addSerialRow(false).querySelector(".dr-serial");
}

async function lookupSerial(input, row) {
  const serial = input.value.trim();
  if (!serial) { clearRow(row); recalc(); return false; }

  const already = allSerials().filter((s) => s === serial);
  if (already.length > 1) {
    Alerts.warning(`Serial "${serial}" is already on this return.`,
                   { title: "Already on this return" });
    input.value = "";
    clearRow(row);
    recalc();
    return false;
  }

  const result = await postJSON(DR_URLS.lookup, { serial });
  /* The box may have been edited while the lookup was out: an answer about a
     serial it no longer holds is dropped (the newer value has its own). */
  if (input.value.trim() !== serial) { return false; }

  if (!result.success) {
    Alerts.error(result.message, { title: "Cannot return this serial" });
    input.value = "";
    clearRow(row);
    recalc();
    return false;
  }

  /* The customer is decided by the serial's sale, not by the operator. The
     first serial fixes it; a later serial belonging to somebody else is
     refused here rather than by a confusing database message. */
  const partyField = document.getElementById("party_name");
  if (partyField.value && result.customer_name && partyField.value !== result.customer_name) {
    Alerts.error(`Serial "${serial}" was sold to ${result.customer_name}, but this `
                 + `return is for ${partyField.value}. Return it on its own document.`,
                 { title: "Different customer" });
    input.value = "";
    clearRow(row);
    recalc();
    return false;
  }
  if (!partyField.value) { partyField.value = result.customer_name || ""; }

  row.querySelector(".dr-item").value = result.item_name || "";
  row.querySelector(".dr-price").value = money(result.sold_price);
  row.querySelector(".dr-draft").value = result.draft_invoice_id
    ? `#${result.draft_invoice_id}` : "";
  row.dataset.soldPrice = result.sold_price == null ? "" : String(result.sold_price);
  recalc();
  return true;
}

function clearRow(row) {
  ["dr-item", "dr-price", "dr-draft"].forEach((cls) => {
    const field = row.querySelector(`.${cls}`);
    if (field) { field.value = ""; }
  });
  delete row.dataset.soldPrice;
}

function allSerials() {
  return Array.from(document.querySelectorAll("#serials .dr-serial"))
    .map((input) => input.value.trim()).filter(Boolean);
}

function recalc() {
  let count = 0;
  let total = 0;
  document.querySelectorAll("#serials .dr-serial-row").forEach((row) => {
    const serial = row.querySelector(".dr-serial").value.trim();
    if (!serial) { return; }
    count += 1;
    if (row.dataset.soldPrice) { total += Number(row.dataset.soldPrice); }
  });
  document.getElementById("totalSerials").textContent = String(count);
  document.getElementById("totalReturnAmount").textContent = money(total);

  /* The customer field only stays filled while a serial justifies it. */
  if (!count) { document.getElementById("party_name").value = ""; }
}

/* ── save and delete ──────────────────────────────────────────────────── */

let savingReturn = false;

async function submitReturn(event) {
  event.preventDefault();
  if (savingReturn) { return; }
  const serials = allSerials();
  if (!serials.length) {
    Alerts.warning("Enter at least one serial number.", { title: "Nothing to return" });
    return;
  }
  const returnDate = document.getElementById("return_date").value;
  if (!returnDate) {
    Alerts.warning("Pick the date of this return.", { title: "Return date required" });
    return;
  }

  const existingId = document.getElementById("current_return_id").value;
  savingReturn = true;
  let result;
  try {
    result = await postJSON(DR_URLS.save, {
      draft_return_id: existingId || null,
      party_name: document.getElementById("party_name").value.trim(),
      return_date: returnDate,
      description: document.getElementById("return_description").value,
      serials,
    });
  } finally {
    savingReturn = false;
  }
  /* The server says which it did; the local id is only the fallback. */
  const wasUpdate = typeof result.created === "boolean"
    ? !result.created
    : Boolean(existingId);

  if (!result.success) {
    Alerts.error(result.message, { title: wasUpdate ? "Return not updated" : "Return not saved" });
    return;
  }

  /* Back to a blank screen, as the draft screen does after a save. The number
     is in the message and Previous still reaches it. */
  newReturn();
  Alerts.success(result.message, { title: wasUpdate ? "Return updated" : "Return saved" });
}

async function deleteReturn() {
  const id = document.getElementById("current_return_id").value;
  if (!id) { Alerts.notify("This return has not been saved yet.", { title: "Nothing to delete" }); return; }
  const confirmed = await Alerts.confirm({
    title: "Delete this return?",
    text: "The serials go back to the customer's sale and leave free stock again.",
    confirmText: "Delete",
    danger: true,
  });
  if (!confirmed) { return; }
  const result = await postJSON(DR_URLS.del, { draft_return_id: id });
  if (!result.success) { Alerts.error(result.message, { title: "Not deleted" }); return; }
  newReturn();
  Alerts.success(result.message, { title: "Return deleted" });
}

/* ── navigation ───────────────────────────────────────────────────────── */

/* The action word has to match what pressing it does. */
function setSaveLabel(isExisting) {
  const button = document.getElementById("saveBtn");
  if (!button) { return; }
  button.innerHTML = isExisting
    ? '<i class="fa-solid fa-pen-to-square"></i> Update Return'
    : '<i class="fa-solid fa-floppy-disk"></i> Save Return';
}

function refreshDescriptions() {
  if (window.SmartDescriptions) { SmartDescriptions.refreshAll(); }
}

function newReturn() {
  setSaveLabel(false);
  document.getElementById("serials").innerHTML = "";
  document.getElementById("current_return_id").value = "";
  document.getElementById("returnIdBadge").textContent = "#NEW";
  document.getElementById("entryByName").textContent = "—";
  document.getElementById("party_name").value = "";
  document.getElementById("return_description").value = "";
  document.getElementById("return_date").value = todayISO();
  setDisabled(false);
  addSerialRow(false);
  recalc();
  refreshDescriptions();
}

async function navigateReturn(direction) {
  const id = document.getElementById("current_return_id").value;
  if (!id) { await loadReturn("last"); return; }
  await loadReturn(direction, id);
}

/* Returns true when a return was shown. A number that is not there leaves the
   screen exactly as it was: the hidden id is only written once a return
   arrives. */
async function loadReturn(nav, id) {
  const params = new URLSearchParams({ nav });
  if (id) { params.set("draft_return_id", id); }
  const result = await getJSON(`${DR_URLS.get}?${params.toString()}`);
  if (!result.success) { Alerts.error(result.message, { title: "Could not load" }); return false; }
  if (!result.draft_return) {
    /* "current" asks for one number (a History pick, a ?open= link); the
       others walk the list. */
    if (nav === "current") {
      Alerts.notify(`There is no return #${id}.`, { title: "Not found" });
    } else if (nav !== "last") {
      Alerts.notify("There is no return that way.", { title: "End of the list" });
    } else {
      Alerts.notify("There is no confirmed draft return yet.", { title: "No returns" });
    }
    return false;
  }
  renderReturn(result.draft_return);
  return true;
}

function renderReturn(data) {
  document.getElementById("current_return_id").value = data.draft_return_id;
  document.getElementById("returnIdBadge").textContent = `#${data.draft_return_id}`;
  document.getElementById("party_name").value = data.Party || "";
  document.getElementById("return_date").value = data.return_date || "";
  document.getElementById("return_description").value = data.description || "";
  document.getElementById("entryByName").textContent = data.created_by || "—";

  document.getElementById("serials").innerHTML = "";
  (data.items || []).forEach((item) => addSerialRow(false, {
    serial_number: item.serial_number,
    item_name: item.item_name,
    sold_price: item.sold_price,
    draft_invoice_id: data.draft_invoice_id,
  }));
  recalc();
  /* recalc() empties the customer when no serial is on screen; a saved return
     always names its customer, so it is shown whatever its rows hold. */
  document.getElementById("party_name").value = data.Party || "";
  refreshDescriptions();
  setDisabled(false);
  setSaveLabel(true);
}

function setDisabled(value) {
  ["saveBtn", "deleteBtn"].forEach((id) => {
    const element = document.getElementById(id);
    if (element) { element.disabled = value; }
  });
}

/* ── history ──────────────────────────────────────────────────────────── */

async function returnHistory() { await showSummary({}); }

async function returnDateWise() {
  const today = todayISO();
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
    confirmButtonText: "Fetch Returns",
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

/* The rows behind the open popup, so the PDF says what is on screen rather
   than asking the server a second question that could answer differently. */
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

function returnHistoryPdf() {
  if (!documentPdfAllowed() || !historyRows.length) { return; }
  const ranged = historyRange.start_date && historyRange.end_date;
  const options = DraftReports.returnHistoryPdfOptions(historyRows, {
    from: historyRange.start_date,
    to: historyRange.end_date,
  });
  savePdf(options, ranged
    ? `Draft_Returns_${historyRange.start_date}_to_${historyRange.end_date}.pdf`
    : "Draft_Returns.pdf");
}

async function showSummary(range) {
  const result = await postJSON(DR_URLS.summary, range);
  if (!result.success) { Alerts.error(result.message, { title: "Could not load" }); return; }
  const rows = result.returns || [];
  if (!rows.length) { Alerts.notify("Nothing to show for that range.", { title: "No returns" }); return; }

  historyRows = rows;
  historyRange = range || {};

  const body = rows.map((row, index) => `
    <tr class="dr-row" data-return-id="${escapeHtml(row.draft_return_id)}"
        data-customer="${escapeHtml(String(row.customer == null ? "" : row.customer).toLowerCase())}">
      <td>${index + 1}</td>
      <td><b>#${escapeHtml(row.draft_return_id)}</b></td>
      <td>${escapeHtml(DraftReports.formatDate(row.return_date))}</td>
      <td>${escapeHtml(row.customer)}</td>
      <td>${row.draft_invoice_id ? "#" + escapeHtml(row.draft_invoice_id) : "—"}</td>
      <td class="num mono">${escapeHtml(money(row.total_amount))}</td>
    </tr>`).join("");

  /* The draft screen's popup shape on purpose: two documents, one thing to
     learn. */
  const html = `
    <div class="draft-history">
      <div class="sh-bar">
        <input type="text" class="sh-search" placeholder="🔍 Search by customer…"
               aria-label="Search by customer">
        ${documentPdfAllowed() ? `<button type="button" class="sh-pdf"><i class="fa-solid fa-file-pdf"></i> Export PDF</button>` : ""}
      </div>
      <div class="sh-wrap">
        <table class="sh-table">
          <thead><tr><th>#</th><th>Return</th><th>Date</th><th>Customer</th>
            <th>From Draft</th><th class="num">Amount (${escapeHtml(currencyCode())})</th></tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </div>`;

  Alerts.dialog({
    title: "📜 Return History",
    html,
    width: "780px",
    focusConfirm: false,
    allowOutsideClick: false,
    allowEscapeKey: true,
    didOpen: (popup) => {
      const search = popup.querySelector(".sh-search");
      const lines = Array.from(popup.querySelectorAll("tr.dr-row"));
      search.addEventListener("input", () => {
        const needle = search.value.toLowerCase().trim();
        lines.forEach((line) => { line.hidden = !line.dataset.customer.includes(needle); });
      });
      popup.querySelector(".sh-pdf")?.addEventListener("click", returnHistoryPdf);
      popup.querySelector(".sh-table tbody").addEventListener("click", (event) => {
        const line = event.target.closest("tr.dr-row");
        if (line) { pickReturn(line.dataset.returnId); }
      });
      setTimeout(() => search.focus(), 80);
    },
  });
}

function pickReturn(id) {
  Alerts.close();
  loadReturn("current", id);
}

/* ── boot ─────────────────────────────────────────────────────────────── */

document.addEventListener("DOMContentLoaded", () => {
  /* Open ready for a NEW return, not on the last saved one. Previous still
     reaches the most recent return, because navigateReturn() falls back to
     "last" when nothing is on screen. */
  newReturn();

  /* A link to one return (/draft/return/screen/?open=<number>) opens it, as a
     pick from History does. The screen is already blank underneath, so a
     number that is not there leaves it ready for a new return. */
  const linked = takeLinkParam("open");
  if (linked) {
    const number = recordNumber(linked);
    if (number) {
      loadReturn("current", number);
    } else {
      Alerts.notify(`There is no return #${linked.slice(0, 40)}.`, { title: "Not found" });
    }
  }
});
