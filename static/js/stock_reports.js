/* ============================================================
   STOCK REPORTS  —  JavaScript  (v3-final)
   • Compact filter forms for all report types
   • Post-render table search/filter with row count
   • Professional branded PDF (green header)
   • CSV exports visible rows only
   ============================================================ */

let _rMeta = { title: "Stock Report", subtitle: "", filters: {} };

// ═══════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════
function getCSRFToken() {
  for (let c of decodeURIComponent(document.cookie).split(";")) {
    c = c.trim();
    if (c.startsWith("csrftoken=")) return c.slice("csrftoken=".length);
  }
  return "";
}

function showLoader(msg = "Loading…") {
  // Swal.fire({ title: msg, didOpen: () => Swal.showLoading(), allowOutsideClick: false });
  Alerts.loading(msg);
}

function fmt(date) {
  if (!date) return "—";
  return new Date(date).toLocaleDateString("en-PK", { day: "2-digit", month: "short", year: "numeric" });
}

// ═══════════════════════════════════════════
// REPORT SELECTOR
// ═══════════════════════════════════════════
function selectReport(type) {
  $(".report-btn").removeClass("active");
  $(`#btn-${type}`).addClass("active");
  $("#reportHeader").empty();
  $("#reportBody").html(`<tr><td class="no-data">Loading…</td></tr>`);
  $("#reportToolbar").remove();
  $("#report-form-container").empty();

  const map = {
    "history":                    () => renderHistoryForm(),
    "serial":                     () => renderSerialForm("fetchSerialLedger", "Serial Ledger"),
    "seril-ledger-with-sold-flag":() => renderSerialForm("fetchSerialLedgerWithSoldFlag", "Serial Ledger — Sold Flag"),
    "serial-purchase-only":       () => renderSerialForm("fetchSerialLedgerPurchaseOnly", "Serial Ledger — Purchase"),
    "serial-sale-only":           () => renderSerialForm("fetchSerialLedgerSaleOnly", "Serial Ledger — Sale"),
    "summary":                    () => _fetchDirect("/accountsReports/stock-summary/", "Stock Summary", "All items current stock"),
    "item-detail":                () => renderItemDetailForm(),
    "item-last-purchase":         () => _fetchDirect("/accountsReports/item-last-purchase/", "Item Last Purchase", "Most recent purchase per item"),
    "item-last-sale":             () => _fetchDirect("/accountsReports/item-last-sale/", "Item Last Sale", "Most recent sale per item"),
    "stock":                      () => _fetchDirect("/accountsReports/stock-report/", "Stock Serial Wise", "All serials and their status"),
    "worth":                      () => _fetchDirect("/accountsReports/stock-worth-report/", "Stock Worth Report", "Valuation of current stock"),
  };

  (map[type] || map["summary"])();
}

// ═══════════════════════════════════════════
// FORM RENDERERS
// ═══════════════════════════════════════════

function renderHistoryForm() {
  const today = new Date().toISOString().split("T")[0];
  $("#report-form-container").html(`
    <div class="filter-form">
      <div class="filter-field autocomplete-container">
        <label><i class="fa-solid fa-box"></i>&nbsp;Item Name</label>
        <input type="text" id="item_name" placeholder="Type to search item…"
               autocomplete="off" data-autocomplete-url="${window.ITEM_AUTOCOMPLETE_URL}">
        <div id="suggestions" style="display:none;"></div>
      </div>
      <div class="filter-field">
        <label><i class="fa-regular fa-calendar"></i>&nbsp;From Date</label>
        <input type="date" id="from_date" value="2000-01-01">
      </div>
      <div class="filter-field">
        <label><i class="fa-regular fa-calendar"></i>&nbsp;To Date</label>
        <input type="date" id="to_date" value="${today}" max="${today}">
      </div>
      <button class="generate-btn" onclick="fetchItemHistory()">
        <i class="fa-solid fa-bolt"></i> Generate
      </button>
    </div>
  `);
  $("#reportHeader").empty();
  $("#reportBody").html(`<tr><td class="no-data">Enter item name and date range, then click Generate</td></tr>`);
  initAutocomplete();
}

function renderSerialForm(fetchFn, label) {
  $("#report-form-container").html(`
    <div class="filter-form">
      <div class="filter-field">
        <label><i class="fa-solid fa-barcode"></i>&nbsp;Serial No.</label>
        <input type="text" id="serial_input" placeholder="e.g. IP15-001" style="width:200px;">
      </div>
      <button class="generate-btn" onclick="${fetchFn}()">
        <i class="fa-solid fa-bolt"></i> Generate
      </button>
    </div>
  `);
  $("#reportHeader").empty();
  $("#reportBody").html(`<tr><td class="no-data">Enter serial number and click Generate</td></tr>`);
}

function renderItemDetailForm() {
  $("#report-form-container").html(`
    <div class="filter-form">
      <div class="filter-field autocomplete-container">
        <label><i class="fa-solid fa-box"></i>&nbsp;Item Name</label>
        <input type="text" id="item_detail_name" placeholder="Type to search item…"
               autocomplete="off" data-autocomplete-url="${window.ITEM_AUTOCOMPLETE_URL}">
        <div id="suggestions_detail" style="display:none;"></div>
      </div>
      <button class="generate-btn" onclick="fetchItemDetail()">
        <i class="fa-solid fa-bolt"></i> Generate
      </button>
    </div>
  `);
  $("#reportHeader").empty();
  $("#reportBody").html(`<tr><td class="no-data">Enter item name and click Generate</td></tr>`);
  initAutocompleteDetail();
}

// ═══════════════════════════════════════════
// FETCH HELPERS
// ═══════════════════════════════════════════

function _fetchDirect(url, title, subtitle = "") {
  _rMeta = { title, subtitle, filters: {} };
  showLoader(`Loading ${title}…`);
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() } })
  .then(r => r.json())
  // .then(data => { Swal.close(); data.error ? Swal.fire("Error", data.error, "error") : renderTable(data); })
  .then(data => { Swal.close(); data.error ? Alerts.error(data.error) : renderTable(data); })
  // .catch(() => Swal.fire("Error", "Unable to fetch data.", "error"));
  .catch(() => Alerts.error("Unable to fetch data."));
}

function fetchItemHistory() {
  const item = $("#item_name").val().trim();
  const from = $("#from_date").val();
  const to   = $("#to_date").val();
  // if (!item) { Swal.fire("Missing Item", "Please enter an item name.", "warning"); return; }
  if (!item) { Alerts.warning("Please enter an item name.", { title: "Missing Item" }); return; }

  _rMeta = { title: "Item History", subtitle: `History for: ${item}`,
             filters: { Item: item, From: fmt(from), To: fmt(to) } };
  showLoader("Loading item history…");
  fetch("/accountsReports/item-history/", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
    body: JSON.stringify({ item_name: item, from_date: from, to_date: to })
  })
  .then(r => r.json())
  // .then(data => { Swal.close(); data.error ? Swal.fire("Error", data.error, "error") : renderTable(data); })
  .then(data => { Swal.close(); data.error ? Alerts.error(data.error) : renderTable(data); })
  // .catch(() => Swal.fire("Error", "Unable to fetch item history.", "error"));
  .catch(() => Alerts.error("Unable to fetch item history."));
}

function _fetchSerial(url, title) {
  const serial = $("#serial_input").val().trim();
  // if (!serial) { Swal.fire("Missing Serial", "Please enter a serial number.", "warning"); return; }
  if (!serial) { Alerts.warning("Please enter a serial number.", { title: "Missing Serial" }); return; }
  _rMeta = { title, subtitle: `Serial: ${serial}`, filters: { Serial: serial } };
  showLoader(`Loading ${title}…`);
  fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
    body: JSON.stringify({ serial })
  })
  .then(r => r.json())
  // .then(data => { Swal.close(); data.error ? Swal.fire("Error", data.error, "error") : renderTable(data); })
  .then(data => { Swal.close(); data.error ? Alerts.error(data.error) : renderTable(data); })
  // .catch(() => Swal.fire("Error", "Unable to fetch serial ledger.", "error"));
  .catch(() => Alerts.error("Unable to fetch serial ledger."));
}

function fetchSerialLedger()             { _fetchSerial("/accountsReports/serial-ledger/",               "Serial Ledger"); }
function fetchSerialLedgerWithSoldFlag() { _fetchSerial("/accountsReports/serial-ledger-sold-flag/",     "Serial Ledger — Sold Flag"); }
function fetchSerialLedgerPurchaseOnly() { _fetchSerial("/accountsReports/serial-ledger-purchase-only/", "Serial Ledger — Purchase"); }
function fetchSerialLedgerSaleOnly()     { _fetchSerial("/accountsReports/serial-ledger-sale-only/",     "Serial Ledger — Sale"); }

function fetchItemDetail() {
  const item = $("#item_detail_name").val().trim();
  // if (!item) { Swal.fire("Missing Item", "Please enter an item name.", "warning"); return; }
  if (!item) { Alerts.warning("Please enter an item name.", { title: "Missing Item" }); return; }
  _rMeta = { title: "Item Detail", subtitle: `Detail for: ${item}`, filters: { Item: item } };
  showLoader("Loading item detail…");
  fetch("/accountsReports/item-detail/", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
    body: JSON.stringify({ item_name: item })
  })
  .then(r => r.json())
  // .then(data => { Swal.close(); data.error ? Swal.fire("Error", data.error, "error") : renderTable(data); })
  .then(data => { Swal.close(); data.error ? Alerts.error(data.error) : renderTable(data); })
  // .catch(() => Swal.fire("Error", "Unable to fetch item detail.", "error"));
  .catch(() => Alerts.error("Unable to fetch item detail."));
}

// ═══════════════════════════════════════════
// TABLE RENDERER
// ═══════════════════════════════════════════
// Cell values are free text typed by users (item names, serial comments, the
// customer a serial is reserved for), so they are escaped, never parsed as HTML.
function escapeCell(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function renderTable(data) {
  const $header = $("#reportHeader");
  const $body   = $("#reportBody");

  if (!data || !data.length) {
    $header.empty();
    $body.html(`<tr><td class="no-data">No records found</td></tr>`);
    injectToolbar(0);
    return;
  }

  const cols = Object.keys(data[0]);
  $header.html(`<tr>${cols.map(c => `<th>${escapeCell(c.replace(/_/g, " "))}</th>`).join("")}</tr>`);
  $body.html(data.map(row =>
    `<tr>${cols.map(c => `<td>${escapeCell(row[c])}</td>`).join("")}</tr>`
  ).join(""));

  injectToolbar(data.length);
}

// ═══════════════════════════════════════════
// TOOLBAR
// ═══════════════════════════════════════════
function injectToolbar(total) {
  $("#reportToolbar").remove();

  $(`<div id="reportToolbar" class="report-toolbar">
      <div class="table-filter-bar">
        <div class="table-search-wrap">
          <i class="fa-solid fa-magnifying-glass"></i>
          <input type="text" id="tableSearch" placeholder="Filter results…" autocomplete="off">
        </div>
        <span class="table-row-count" id="rowCount">${total} row${total !== 1 ? "s" : ""}</span>
      </div>
      <div class="table-actions">
        ${window.financeeFeatureEnabled && !financeeFeatureEnabled("pdf_export", "reports") ? "" : `
        <button id="download_pdf" class="btn-download">
          <i class="fa-solid fa-file-pdf"></i> PDF
        </button>`}
        ${window.financeeFeatureEnabled && !financeeFeatureEnabled("excel_export") ? "" : `
        <button id="download_csv" class="btn-download btn-csv">
          <i class="fa-solid fa-file-csv"></i> CSV
        </button>`}
      </div>
    </div>`)
    .insertBefore(".table-container");

  $("#tableSearch").on("input", function () {
    const q = this.value.toLowerCase().trim();
    let vis = 0;
    $("#reportBody tr").each(function () {
      const show = !q || $(this).text().toLowerCase().includes(q);
      $(this).toggleClass("filtered-out", !show);
      if (show) vis++;
    });
    $("#rowCount").text(`${vis} row${vis !== 1 ? "s" : ""}`);
  });
}

// ═══════════════════════════════════════════
// PDF  —  green branded header + footer
// ═══════════════════════════════════════════
$(document).on("click", "#download_pdf", function () {
  if (window.financeeFeatureEnabled && !financeeFeatureEnabled("pdf_export", "reports")) return;
  const { jsPDF } = window.jspdf;

  const colHeaders = [...document.querySelectorAll("#reportTable thead th")].map(th => th.textContent.trim());
  const rowData    = [];
  document.querySelectorAll("#reportBody tr:not(.filtered-out)").forEach(tr => {
    const cells = [...tr.querySelectorAll("td")].map(td => td.textContent.trim());
    if (cells.length && !cells[0].includes("No records")) rowData.push(cells);
  });

  // if (!rowData.length) { Swal.fire("No Data", "Nothing visible to export.", "warning"); return; }
  if (!rowData.length) { Alerts.warning("Nothing visible to export.", { title: "No Data" }); return; }

  const doc   = new jsPDF("l", "pt", "a4");   // landscape — stock tables tend to be wide
  const pW    = doc.internal.pageSize.width;
  const pH    = doc.internal.pageSize.height;
  const today = new Date().toLocaleDateString("en-PK", { day: "2-digit", month: "short", year: "numeric" });
  const m     = _rMeta;
  const fStr  = Object.entries(m.filters || {}).map(([k, v]) => `${k}: ${v}`).join("   ·   ");

  function drawHeader(pg, total) {
    doc.setFillColor(5, 150, 105);             // emerald-green brand
    doc.rect(0, 0, pW, 38, "F");
    doc.setFont("helvetica", "bold"); doc.setFontSize(13); doc.setTextColor(255, 255, 255);
    doc.text("Financee", 36, 25);
    doc.setFont("helvetica", "normal"); doc.setFontSize(10);
    doc.text(m.title, pW - 36, 25, { align: "right" });

    doc.setFillColor(236, 253, 245);
    doc.rect(0, 38, pW, 26, "F");
    doc.setFont("helvetica", "italic"); doc.setFontSize(8); doc.setTextColor(71, 85, 105);
    let sub = m.subtitle || "";
    if (fStr) sub += (sub ? "   ·   " : "") + fStr;
    doc.text(sub, 36, 55);
    doc.setFont("helvetica", "normal");
    doc.text(`Generated: ${today}   Page ${pg} of ${total}`, pW - 36, 55, { align: "right" });
    doc.setDrawColor(203, 213, 225); doc.setLineWidth(0.5); doc.line(0, 64, pW, 64);
  }

  function drawFooter(pg, total) {
    const y = pH - 18;
    doc.setDrawColor(226, 232, 240); doc.setLineWidth(0.4); doc.line(36, y - 7, pW - 36, y - 7);
    doc.setFont("helvetica", "normal"); doc.setFontSize(7.5); doc.setTextColor(148, 163, 184);
    doc.text("Financee  —  Confidential", 36, y + 2);
    doc.text(`Page ${pg} of ${total}`, pW - 36, y + 2, { align: "right" });
  }

  doc.autoTable({
    head: [colHeaders], body: rowData,
    startY: 72,
    margin: { left: 28, right: 28, top: 72, bottom: 32 },
    theme: "grid",
    headStyles:         { fillColor: [4, 120, 87], textColor: [255,255,255], fontStyle: "bold", fontSize: 7.5, cellPadding: 5 },
    bodyStyles:         { fontSize: 7.5, textColor: [30, 41, 59], cellPadding: 4, lineColor: [226, 232, 240] },
    alternateRowStyles: { fillColor: [240, 253, 250] },
    didDrawPage: d => drawHeader(d.pageNumber, "…"),
  });

  const totalPg = doc.internal.getNumberOfPages();
  for (let i = 1; i <= totalPg; i++) { doc.setPage(i); drawHeader(i, totalPg); drawFooter(i, totalPg); }

  doc.save(`${m.title.replace(/\s+/g, "_")}_${new Date().toISOString().split("T")[0]}.pdf`);
  if (globalThis.FinanceeActivity) globalThis.FinanceeActivity.exported("pdf");
});

// ═══════════════════════════════════════════
// CSV
// ═══════════════════════════════════════════
$(document).on("click", "#download_csv", function () {
  // Per-company feature flag: CSV/Excel export can be disabled from the admin.
  if (window.financeeFeatureEnabled && !financeeFeatureEnabled("excel_export")) return;
  const tbl = document.getElementById("reportTable");
  // if (!tbl) { Swal.fire("No Data", "Nothing to export.", "warning"); return; }
  if (!tbl) { Alerts.warning("Nothing to export.", { title: "No Data" }); return; }

  const m    = _rMeta;
  const rows = [];
  rows.push([`${m.title} Report`]);
  Object.entries(m.filters || {}).forEach(([k, v]) => rows.push([`${k}: ${v}`]));
  rows.push([`Generated: ${new Date().toLocaleString()}`]);
  rows.push([]);
  rows.push([...tbl.querySelectorAll("thead th")].map(th => th.textContent.trim()));

  tbl.querySelectorAll("tbody tr:not(.filtered-out)").forEach(tr => {
    const row = [...tr.querySelectorAll("td")].map(td => {
      let v = td.textContent.trim();
      if (/[,"\n]/.test(v)) v = `"${v.replace(/"/g, '""')}"`;
      return v;
    });
    if (row.length && !row[0].includes("No records")) rows.push(row);
  });

  const a = Object.assign(document.createElement("a"), {
    href: URL.createObjectURL(new Blob([rows.map(r => r.join(",")).join("\n")], { type: "text/csv;charset=utf-8;" })),
    download: `${m.title.replace(/\s+/g,"_")}_${new Date().toISOString().split("T")[0]}.csv`,
    style: "display:none",
  });
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  if (globalThis.FinanceeActivity) globalThis.FinanceeActivity.exported("csv");
});

// ═══════════════════════════════════════════
// AUTOCOMPLETE — item_name
// ═══════════════════════════════════════════
function initAutocomplete() {
  const $inp = $("#item_name"), $box = $("#suggestions");
  const url  = $inp.data("autocomplete-url");
  let idx = -1, items = [];

  $inp.off(".auto").on("input.auto", function () {
    const q = $(this).val(); idx = -1; items = []; $box.empty();
    if (!q) return $box.hide();
    $.getJSON(url, { term: q }, data => {
      items = data || []; $box.empty();
      if (!items.length) return $box.hide();
      items.forEach(t => $("<div>").addClass("suggestion-item").text(t)
        .on("click", () => { $inp.val(t); $box.hide(); }).appendTo($box));
      $box.show();
    });
  });

  $inp.on("keydown.auto", function (e) {
    const $it = $box.children(".suggestion-item");
    if (e.key === "ArrowDown") { e.preventDefault(); idx = (idx + 1) % $it.length; }
    if (e.key === "ArrowUp")   { e.preventDefault(); idx = (idx - 1 + $it.length) % $it.length; }
    $it.removeClass("highlight").eq(idx).addClass("highlight");
    if (e.key === "Enter") { e.preventDefault(); if (items.length === 1) { $inp.val(items[0]); $box.hide(); } else if (idx >= 0) { $inp.val($it.eq(idx).text()); $box.hide(); } }
    if (e.key === "Escape") $box.hide();
  });

  $(document).on("click.auto", e => { if (!$(e.target).closest("#item_name,#suggestions").length) $box.hide(); });
}

// ═══════════════════════════════════════════
// AUTOCOMPLETE — item_detail_name
// ═══════════════════════════════════════════
function initAutocompleteDetail() {
  const $inp = $("#item_detail_name"), $box = $("#suggestions_detail");
  const url  = $inp.data("autocomplete-url");
  let idx = -1, items = [];

  $inp.off(".autoD").on("input.autoD", function () {
    const q = $(this).val(); idx = -1; items = []; $box.empty();
    if (!q) return $box.hide();
    $.getJSON(url, { term: q }, data => {
      items = data || []; $box.empty();
      if (!items.length) return $box.hide();
      items.forEach(t => $("<div>").addClass("suggestion-item").text(t)
        .on("click", () => { $inp.val(t); $box.hide(); }).appendTo($box));
      $box.show();
    });
  });

  $inp.on("keydown.autoD", function (e) {
    const $it = $box.children(".suggestion-item");
    if (e.key === "ArrowDown") { e.preventDefault(); idx = (idx + 1) % $it.length; }
    if (e.key === "ArrowUp")   { e.preventDefault(); idx = (idx - 1 + $it.length) % $it.length; }
    $it.removeClass("highlight").eq(idx).addClass("highlight");
    if (e.key === "Enter") { e.preventDefault(); if (items.length === 1) { $inp.val(items[0]); $box.hide(); } else if (idx >= 0) { $inp.val($it.eq(idx).text()); $box.hide(); } }
    if (e.key === "Escape") $box.hide();
  });

  $(document).on("click.autoD", e => { if (!$(e.target).closest("#item_detail_name,#suggestions_detail").length) $box.hide(); });
}

// ═══════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════
// $(document).ready(() => selectReport("summary"));
// Feature flags can hide individual report buttons per company, so start on
// the Stock Report when present, otherwise on the first report button that is.
$(document).ready(() => {
  const first = document.getElementById("btn-summary")
    ? "summary"
    : $(".report-btn").first().data("report");
  const linked = window.FinanceeRecordLink.report(Array.from(document.querySelectorAll(".report-btn[data-report]")).map(b => b.dataset.report), first);
  if (linked) selectReport(linked);
});
