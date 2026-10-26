/* ============================================================
   MONTHLY REPORTS — monthly_reports.js  (Pakistan environment)
   Two reports:
     1. mprSelectReport('position') — Company Position (Balance Sheet)
        Assets, Liabilities, Net Position = Assets − Liabilities
     2. mprSelectReport('income')   — Income Statement (Profit & Loss)
        Profit/Loss = Sales − Purchases − Expenses (auto-calculated)
   ============================================================ */
'use strict';

let _mprCurrentReport = 'position';
let _mprLastData      = null;   // raw JSON from server, for PDF/print

function mprCSRF() {
  for (const c of decodeURIComponent(document.cookie).split(';')) {
    const t = c.trim();
    if (t.startsWith('csrftoken=')) return t.slice('csrftoken='.length);
  }
  return '';
}

function mprFmt(num) {
  if (num === null || num === undefined || num === '') return '—';
  return new Intl.NumberFormat('en-PK', {
    minimumFractionDigits: 2, maximumFractionDigits: 2
  }).format(num);
}

function mprFmtDate(str) {
  if (!str) return '—';
  return new Date(str).toLocaleDateString('en-PK', {
    day: '2-digit', month: 'short', year: 'numeric'
  });
}

function mprLoader(msg = 'Generating report…') {
  // Swal.fire({ title: msg, didOpen: () => Swal.showLoading(), allowOutsideClick: false });
  Alerts.loading(msg);
}

/* ─────────────────────────── Report switcher ─────────────────────────── */
function mprSelectReport(type) {
  _mprCurrentReport = type;
  document.querySelectorAll('.report-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('mpr-btn-' + type).classList.add('active');
  document.getElementById('mpr-output').innerHTML = '';

  if (type === 'position') mprRenderPositionForm();
  else                     mprRenderIncomeForm();
}

/* ════════════════════════════════════════════════════════════════════════
   1. COMPANY POSITION (Balance Sheet)
   ════════════════════════════════════════════════════════════════════════ */
function mprRenderPositionForm() {
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('mpr-form-container').innerHTML = `
    <div class="mpr-filter-card">
      <div class="filter-field">
        <label for="mpr-as-of-date">As of date</label>
        <input type="date" id="mpr-as-of-date" value="${today}">
      </div>
      <button class="mpr-generate-btn" onclick="mprFetchPosition()">
        <i class="fa-solid fa-scale-balanced"></i> Generate Position
      </button>
    </div>`;
}

async function mprFetchPosition() {
  const asOf = document.getElementById('mpr-as-of-date')?.value;
  // if (!asOf) { Swal.fire('Missing date', 'Please choose an as-of date.', 'warning'); return; }
  if (!asOf) { Alerts.warning('Please choose an as-of date.', { title: 'Missing date' }); return; }

  mprLoader('Fetching company position…');
  try {
    const res = await fetch('/accountsReports/monthly-position/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': mprCSRF() },
      body: JSON.stringify({ as_of_date: asOf })
    });
    const data = await res.json();
    Swal.close();
    // if (!res.ok || data.error) { Swal.fire('Error', data.error || 'Request failed.', 'error'); return; }
    if (!res.ok || data.error) { Alerts.error(data.error || 'Request failed.'); return; }
    _mprLastData = { ...data, report_type: 'position' };
    mprRenderPosition(data);
  } catch (e) {
    Swal.close();
    // Swal.fire('Error', 'Could not fetch data. ' + e.message, 'error');
    Alerts.error('Could not fetch data. ' + e.message);
  }
}

function mprRenderPosition(data) {
  const assetRows = (data.assets || []).map(r =>
    `<tr><td>${r.name}</td><td>${mprFmt(r.amount)}</td></tr>`
  ).join('') || `<tr><td colspan="2" style="text-align:center;color:#94a3b8;">No assets</td></tr>`;

  const liabRows = (data.liabilities || []).map(r =>
    `<tr><td>${r.name}</td><td>${mprFmt(r.amount)}</td></tr>`
  ).join('') || `<tr><td colspan="2" style="text-align:center;color:#94a3b8;">No liabilities</td></tr>`;

  const positive = (data.net_position || 0) >= 0;

  document.getElementById('mpr-output').innerHTML = `
    <div class="mpr-toolbar">
      ${window.financeeFeatureEnabled && !financeeFeatureEnabled("pdf_export", "reports") ? "" : `
      <button class="mpr-toolbar-btn mpr-btn-print" onclick="mprPrintPosition()"><i class="fa-solid fa-print"></i> Print</button>
      <button class="mpr-toolbar-btn mpr-btn-pdf" onclick="mprPdfPosition()"><i class="fa-solid fa-file-pdf"></i> PDF</button>`}
    </div>

    <div class="mpr-report-card" id="mpr-position-card">
      <p class="mpr-report-title">Company Position</p>
      <p class="mpr-report-subtitle">As of ${mprFmtDate(data.as_of_date)}</p>

      <div class="mpr-position-grid">
        <div>
          <div class="mpr-col-header mpr-assets">Assets</div>
          <table class="mpr-breakdown-table">
            ${assetRows}
            <tr class="mpr-total-row"><td>Total Assets</td><td>${mprFmt(data.total_assets)}</td></tr>
          </table>
        </div>
        <div>
          <div class="mpr-col-header mpr-liab">Liabilities</div>
          <table class="mpr-breakdown-table">
            ${liabRows}
            <tr class="mpr-total-row"><td>Total Liabilities</td><td>${mprFmt(data.total_liabilities)}</td></tr>
          </table>
        </div>
      </div>

      <div class="mpr-net-bar ${positive ? '' : 'mpr-loss'}">
        <span class="mpr-net-label">Net Position (Assets − Liabilities)</span>
        <span class="mpr-net-value">${mprFmt(data.net_position)}</span>
      </div>
    </div>`;
}

/* ════════════════════════════════════════════════════════════════════════
   2. INCOME STATEMENT (Profit & Loss)  — auto-calculated
   ════════════════════════════════════════════════════════════════════════ */
function mprRenderIncomeForm() {
  const today = new Date().toISOString().slice(0, 10);
  const first = today.slice(0, 8) + '01';
  document.getElementById('mpr-form-container').innerHTML = `
    <div class="mpr-filter-card">
      <div class="filter-field">
        <label for="mpr-from-date">From date</label>
        <input type="date" id="mpr-from-date" value="${first}">
      </div>
      <div class="filter-field">
        <label for="mpr-to-date">To date</label>
        <input type="date" id="mpr-to-date" value="${today}">
      </div>
      <button class="mpr-generate-btn" onclick="mprFetchIncome()">
        <i class="fa-solid fa-chart-line"></i> Generate Statement
      </button>
    </div>`;
}

async function mprFetchIncome() {
  const from = document.getElementById('mpr-from-date')?.value;
  const to   = document.getElementById('mpr-to-date')?.value;
  // if (!from || !to) { Swal.fire('Missing dates', 'Please choose both dates.', 'warning'); return; }
  // if (from > to)    { Swal.fire('Invalid range', 'From date must be before To date.', 'warning'); return; }
  if (!from || !to) { Alerts.warning('Please choose both dates.', { title: 'Missing dates' }); return; }
  if (from > to)    { Alerts.warning('From date must be before To date.', { title: 'Invalid range' }); return; }

  mprLoader('Fetching income statement…');
  try {
    const res = await fetch('/accountsReports/monthly-income/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': mprCSRF() },
      body: JSON.stringify({ from_date: from, to_date: to })
    });
    const data = await res.json();
    Swal.close();
    // if (!res.ok || data.error) { Swal.fire('Error', data.error || 'Request failed.', 'error'); return; }
    if (!res.ok || data.error) { Alerts.error(data.error || 'Request failed.'); return; }
    _mprLastData = { ...data, report_type: 'income' };
    mprRenderIncome(data);
  } catch (e) {
    Swal.close();
    // Swal.fire('Error', 'Could not fetch data. ' + e.message, 'error');
    Alerts.error('Could not fetch data. ' + e.message);
  }
}

function mprRenderIncome(data) {
  const isProfit = (data.profit_loss || 0) >= 0;
  const rangeLabel = mprFmtDate(data.from_date) + ' – ' + mprFmtDate(data.to_date);

  const expRows = (data.expenses || []).map(r =>
    `<tr><td>${r.category}</td><td>${mprFmt(r.amount)}</td></tr>`
  ).join('') || `<tr><td colspan="2" style="text-align:center;color:#94a3b8;">No expenses</td></tr>`;

  document.getElementById('mpr-output').innerHTML = `
    <div class="mpr-toolbar">
      ${window.financeeFeatureEnabled && !financeeFeatureEnabled("pdf_export", "reports") ? "" : `
      <button class="mpr-toolbar-btn mpr-btn-print" onclick="mprPrintIncome()"><i class="fa-solid fa-print"></i> Print</button>
      <button class="mpr-toolbar-btn mpr-btn-pdf" onclick="mprPdfIncome()"><i class="fa-solid fa-file-pdf"></i> PDF</button>`}
    </div>

    <div class="mpr-report-card" id="mpr-income-card">
      <p class="mpr-report-title">Income Statement</p>
      <p class="mpr-report-subtitle">${rangeLabel}</p>

      <div class="mpr-income-block">

        <div class="mpr-income-section">
          <div class="mpr-income-section-title">Sales</div>
          <table class="mpr-income-table">
            <tr><td>Gross Sales</td><td>${mprFmt(data.sales_gross)}</td></tr>
            <tr><td>Less: Sales Returns</td><td>(${mprFmt(data.sales_returns)})</td></tr>
            <tr class="mpr-subtotal"><td>Total Sales</td><td>${mprFmt(data.total_sales)}</td></tr>
          </table>
        </div>

        <div class="mpr-income-section">
          <div class="mpr-income-section-title">Purchases</div>
          <table class="mpr-income-table">
            <tr><td>Gross Purchases</td><td>${mprFmt(data.purchases_gross)}</td></tr>
            <tr><td>Less: Purchase Returns</td><td>(${mprFmt(data.purchase_returns)})</td></tr>
            <tr class="mpr-subtotal"><td>Total Purchases</td><td>${mprFmt(data.total_purchases)}</td></tr>
          </table>
        </div>

        <div class="mpr-income-section">
          <div class="mpr-income-section-title">Expenses</div>
          <table class="mpr-income-table">
            ${expRows}
            <tr class="mpr-subtotal"><td>Total Expenses</td><td>${mprFmt(data.total_expenses)}</td></tr>
          </table>
        </div>

        <div class="mpr-income-banner ${isProfit ? '' : 'mpr-loss'}">
          <span class="mpr-income-banner-label">${isProfit ? 'Net Profit' : 'Net Loss'} (Sales − Purchases − Expenses)</span>
          <span class="mpr-income-banner-value">${mprFmt(data.profit_loss)}</span>
        </div>

      </div>
    </div>`;
}

/* ─────────────────────────── PDF export ─────────────────────────── */
function mprPdfPosition() {
  if (window.financeeFeatureEnabled && !financeeFeatureEnabled("pdf_export", "reports")) return;
  const d = _mprLastData; if (!d) return;
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF();
  doc.setFontSize(15); doc.text('Company Position', 14, 18);
  doc.setFontSize(10); doc.text('As of ' + mprFmtDate(d.as_of_date), 14, 25);

  doc.autoTable({
    startY: 32, head: [['Assets', 'Amount']],
    body: (d.assets || []).map(r => [r.name, mprFmt(r.amount)])
          .concat([['Total Assets', mprFmt(d.total_assets)]]),
    theme: 'grid', headStyles: { fillColor: [5, 150, 105] }
  });
  doc.autoTable({
    startY: doc.lastAutoTable.finalY + 6, head: [['Liabilities', 'Amount']],
    body: (d.liabilities || []).map(r => [r.name, mprFmt(r.amount)])
          .concat([['Total Liabilities', mprFmt(d.total_liabilities)]]),
    theme: 'grid', headStyles: { fillColor: [220, 38, 38] }
  });
  doc.autoTable({
    startY: doc.lastAutoTable.finalY + 6,
    body: [['Net Position (Assets − Liabilities)', mprFmt(d.net_position)]],
    theme: 'plain', styles: { fontStyle: 'bold', fontSize: 12 }
  });
  doc.save('company_position_' + d.as_of_date + '.pdf');
  if (globalThis.FinanceeActivity) globalThis.FinanceeActivity.exported("pdf");
}

function mprPdfIncome() {
  if (window.financeeFeatureEnabled && !financeeFeatureEnabled("pdf_export", "reports")) return;
  const d = _mprLastData; if (!d) return;
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF();
  doc.setFontSize(15); doc.text('Income Statement', 14, 18);
  doc.setFontSize(10);
  doc.text(mprFmtDate(d.from_date) + ' to ' + mprFmtDate(d.to_date), 14, 25);

  doc.autoTable({
    startY: 32,
    body: [
      ['Gross Sales', mprFmt(d.sales_gross)],
      ['Less: Sales Returns', '(' + mprFmt(d.sales_returns) + ')'],
      ['Total Sales', mprFmt(d.total_sales)],
      ['Gross Purchases', mprFmt(d.purchases_gross)],
      ['Less: Purchase Returns', '(' + mprFmt(d.purchase_returns) + ')'],
      ['Total Purchases', mprFmt(d.total_purchases)]
    ],
    theme: 'grid'
  });
  doc.autoTable({
    startY: doc.lastAutoTable.finalY + 6, head: [['Expense', 'Amount']],
    body: (d.expenses || []).map(r => [r.category, mprFmt(r.amount)])
          .concat([['Total Expenses', mprFmt(d.total_expenses)]]),
    theme: 'grid', headStyles: { fillColor: [100, 116, 139] }
  });
  doc.autoTable({
    startY: doc.lastAutoTable.finalY + 6,
    body: [[((d.profit_loss || 0) >= 0 ? 'Net Profit' : 'Net Loss') +
            ' (Sales − Purchases − Expenses)', mprFmt(d.profit_loss)]],
    theme: 'plain', styles: { fontStyle: 'bold', fontSize: 12 }
  });
  doc.save('income_statement_' + d.from_date + '_' + d.to_date + '.pdf');
  if (globalThis.FinanceeActivity) globalThis.FinanceeActivity.exported("pdf");
}

/* ─────────────────────────── Print ─────────────────────────── */
function mprPrintElement(elId, title) {
  if (window.financeeFeatureEnabled && !financeeFeatureEnabled("pdf_export", "reports")) return;
  const el = document.getElementById(elId);
  if (!el) return;
  const w = window.open('', '', 'width=900,height=650');
  w.document.write(`<html><head><title>${title}</title>
    <style>body{font-family:Arial,sans-serif;padding:24px;}
    table{width:100%;border-collapse:collapse;margin:8px 0;}
    td{border:1px solid #ddd;padding:6px 10px;font-size:13px;}
    .mpr-report-title{font-size:18px;font-weight:700;margin:0;}
    .mpr-report-subtitle{color:#666;margin:2px 0 14px;}
    .mpr-total-row td,.mpr-subtotal td{font-weight:700;background:#f5f5f5;}
    .mpr-net-bar,.mpr-income-banner{margin-top:12px;padding:10px;font-weight:700;
      display:flex;justify-content:space-between;background:#ecfdf5;}
    .mpr-loss{background:#fef2f2;}</style></head>
    <body>${el.innerHTML}</body></html>`);
  w.document.close(); w.focus(); setTimeout(() => { w.print(); w.close(); }, 250);
}
function mprPrintPosition() { mprPrintElement('mpr-position-card', 'Company Position'); }
function mprPrintIncome()   { mprPrintElement('mpr-income-card', 'Income Statement'); }

/* ─────────────────────────── Init ─────────────────────────── */
// document.addEventListener('DOMContentLoaded', () => mprSelectReport('position'));
// Feature flags can hide either report button per company, so start on
// Company Position when present, otherwise on the first button that is.
document.addEventListener('DOMContentLoaded', () => {
  const firstBtn = document.getElementById('mpr-btn-position')
    || document.querySelector('.report-btn[data-report]');
  const linked = window.FinanceeRecordLink.report(Array.from(document.querySelectorAll('.report-btn[data-report]')).map(b => b.dataset.report), firstBtn && firstBtn.dataset.report);
  if (linked) mprSelectReport(linked);
});
