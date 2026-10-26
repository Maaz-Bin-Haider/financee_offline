/*
 * Pending Drafts report screen.
 *
 * Ported from the sibling Accounting-Plus-Inventory-System (feature commit
 * 80e8f8a, plus its later escaping fix). Thin by design: what a column says,
 * what the warning reads and how the CSV or PDF is shaped all live in
 * draft_reports.js. This file only wires that to the DOM and the export
 * buttons. Alerts (static/js/alerts.js) loads after this file, so it is only
 * touched inside handlers and DOMContentLoaded.
 */

/* global Alerts, DraftReports, FinanceePdf */

const PENDING_URL = "/draft/pending/";

let pendingPayload = { rows: [], summary: {} };
/* The range the table on screen was actually built for -- not whatever the
   date boxes hold now -- so the PDF's context line cannot describe a
   different report from the one it prints. */
let pendingRange = {};

function csrfToken() {
  const match = document.cookie.match(/(^|;\s*)csrftoken=([^;]*)/);
  return match ? decodeURIComponent(match[2]) : "";
}

/* Server text reaches HTML only through this: a customer name is text, never
   markup. */
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/* The company's DRAFT_AGE_WARNING_DAYS, rendered by the template; the server
   applies the same setting and marks each row is_aged. */
function ageWarningDays() {
  const days = Number(window.DRAFT_AGE_WARNING_DAYS);
  return Number.isFinite(days) && days > 0 ? days : 30;
}

async function fetchPending(body) {
  try {
    const response = await fetch(PENDING_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(body),
    });
    let data = null;
    try { data = await response.json(); } catch (error) { data = null; }
    /* The report answers {rows, summary}; anything else -- a refusal
       ({success: false} or the middleware's {status: "denied"}), an error
       page -- is a failure with whatever message it carried. */
    if (data && Array.isArray(data.rows) && data.success !== false) { return data; }
    return {
      success: false,
      message: (data && data.message)
        || `The report could not be built (${response.status}). Reload the page and try again.`,
    };
  } catch (error) {
    return { success: false, message: "Could not reach the server. Check the connection and try again." };
  }
}

async function runPendingReport(event, all) {
  if (event) { event.preventDefault(); }
  let range = {};
  if (!all) {
    const from = document.getElementById("from_date").value;
    const to = document.getElementById("to_date").value;
    if (from || to) {
      if (!from || !to) {
        Alerts.warning("Pick both dates, or use All Open Drafts.", { title: "Date range" });
        return;
      }
      if (from > to) {
        Alerts.warning("The From date is after the To date.", { title: "Date range" });
        return;
      }
      range = { start_date: from, end_date: to };
    }
  }

  const data = await fetchPending(range);
  if (data.success === false) {
    Alerts.error(data.message, { title: "Could not run" });
    return;
  }
  pendingPayload = data;
  pendingRange = range;
  render();
}

function render() {
  const head = document.getElementById("reportHead");
  const body = document.getElementById("reportBody");
  const labels = DraftReports.pendingHead();
  head.innerHTML = "<tr>" + labels.map((label) => `<th>${escapeHtml(label)}</th>`).join("") + "</tr>";

  const sourceRows = pendingPayload.rows || [];
  const cells = DraftReports.pendingRows(pendingPayload);
  const agedAt = ageWarningDays();
  const daysColumn = DraftReports.PENDING_COLUMNS.findIndex((c) => c.key === "days_outstanding");
  body.innerHTML = cells.length
    ? cells.map((row, index) => {
      const source = sourceRows[index] || {};
      /* The server's own is_aged flag; the page's threshold only when a row
         does not carry one. */
      const aged = typeof source.is_aged === "boolean"
        ? source.is_aged
        : Number(source.days_outstanding || 0) >= agedAt;
      return "<tr>" + row.map((cell, column) => {
        const cls = aged && column === daysColumn ? ' class="draft-aged-cell"' : "";
        return `<td${cls}>${escapeHtml(cell)}</td>`;
      }).join("") + "</tr>";
    }).join("")
    : `<tr><td colspan="${labels.length}" class="no-data">No draft has serials reserved for this range.</td></tr>`;

  /* The warning survives onto the screen, into the CSV and into the PDF. */
  const notes = DraftReports.pendingNotes(pendingPayload.summary);
  const banner = document.getElementById("pendingWarning");
  banner.hidden = notes.length === 0;
  banner.innerHTML = notes.map((n) => `<div>${escapeHtml(n)}</div>`).join("");

  const chips = document.getElementById("summaryChips");
  const pairs = DraftReports.pendingSummaryChips(pendingPayload.summary);
  chips.hidden = pairs.length === 0;
  chips.innerHTML = pairs.map(([label, value]) =>
    `<span class="draft-chip"><span class="draft-chip-label">${escapeHtml(label)}</span>`
    + `<span class="draft-chip-value">${escapeHtml(value)}</span></span>`).join("");

  injectToolbar();
}

/* The CSV button follows the company's excel_export switch and the PDF
   button its pdf_export.reports switch, as every other report toolbar does. */
function csvAllowed() {
  return !(typeof window.financeeFeatureEnabled === "function"
           && !window.financeeFeatureEnabled("excel_export"));
}

function pdfAllowed() {
  return !(typeof window.financeeFeatureEnabled === "function"
           && !window.financeeFeatureEnabled("pdf_export", "reports"));
}

function injectToolbar() {
  if (document.getElementById("pendingToolbar")) { return; }
  const bar = document.createElement("div");
  bar.id = "pendingToolbar";
  bar.className = "report-toolbar";
  bar.innerHTML = `
    <div class="table-actions">
      ${pdfAllowed() ? `
      <button type="button" class="btn-download" id="pendingPdfBtn">
        <i class="fa-solid fa-file-pdf"></i> PDF
      </button>` : ""}
      ${csvAllowed() ? `
      <button type="button" class="btn-download btn-csv" id="pendingCsvBtn">
        <i class="fa-solid fa-file-csv"></i> CSV
      </button>` : ""}
    </div>`;
  const container = document.querySelector(".table-container");
  container.parentNode.insertBefore(bar, container);
  const pdf = bar.querySelector("#pendingPdfBtn");
  if (pdf) { pdf.addEventListener("click", downloadPendingPdf); }
  const csv = bar.querySelector("#pendingCsvBtn");
  if (csv) { csv.addEventListener("click", downloadPendingCsv); }
}

function downloadPendingCsv() {
  const text = DraftReports.pendingCsv(pendingPayload);
  const blob = new Blob([text], { type: "text/csv;charset=utf-8;" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "pending-drafts.csv";
  document.body.appendChild(link);
  link.click();
  if (globalThis.FinanceeActivity) globalThis.FinanceeActivity.exported("csv");
  link.remove();
  URL.revokeObjectURL(link.href);
}

function downloadPendingPdf() {
  if (!pdfAllowed()) { return; }
  if (!window.jspdf || !window.jspdf.jsPDF || typeof FinanceePdf === "undefined") {
    Alerts.error("The PDF library did not load. Check the connection and reload the page.",
                 { title: "PDF unavailable" });
    return;
  }
  const options = DraftReports.pendingPdfOptions(pendingPayload, {
    jsPDF: window.jspdf.jsPDF,
    context: reportContext(),
  });
  try {
    /* FinanceePdf.save builds and saves through the shared theme. */
    FinanceePdf.save(Object.assign(options, { filename: "Pending_Drafts.pdf" }));
  } catch (error) {
    Alerts.error("The PDF could not be built. Reload the page and try again.",
                 { title: "PDF failed" });
  }
}

function reportContext() {
  if (!pendingRange.start_date || !pendingRange.end_date) { return "All open drafts"; }
  return `${DraftReports.formatDate(pendingRange.start_date)} to `
    + `${DraftReports.formatDate(pendingRange.end_date)}`;
}

document.addEventListener("DOMContentLoaded", () => { runPendingReport(null, true); });
