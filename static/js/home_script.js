/**
 * home_script.js — Dashboard v2
 * Accounting + Inventory Management System
 */
"use strict";

// ══════════════════════════════════════════════════════════════════════════
// CONFIG & UTILS
// ══════════════════════════════════════════════════════════════════════════
const API = {
  salesToday:          "/home/api/dash/sales/today/",
  salesChart:          "/home/api/dash/sales/chart/",
  stockKpi:            "/home/api/dash/stock/kpi/",
  lowStock:            "/home/api/dash/stock/low/",
  fastMoving:          "/home/api/dash/stock/fast/",
  staleStock:          "/home/api/dash/stock/stale/",
  topCustomers:        "/home/api/dash/customers/top/",
  topVendors:          "/home/api/dash/vendors/top/",
  receivablesAging:    "/home/api/dash/receivables/aging/",
  recentTransactions:  "/home/api/dash/transactions/recent/",
  expenseKpi:          "/home/api/dash/expenses/kpi/",
  expenseCategories:   "/home/api/dash/expenses/categories/",
  expenseDescriptions: "/home/api/dash/expenses/descriptions/",
  smartAlerts:         "/home/api/dash/alerts/",
  draftReservations:   "/home/api/dash/drafts/",
  cashBalance:         "/home/api/cash/",
  cashLedger:          "/accountsReports/cash-ledger/",
  partyBalances:       "/home/api/party-balances/",
  receivable:          "/home/api/receivable/",
  payable:             "/home/api/payable/",
  expenseParties:      "/home/api/expense-party-balances/",
  parties:             "/home/api/parties/",
  items:               "/home/api/items/",
};

const PKR = new Intl.NumberFormat("en-AE", { style:"currency", currency:"PKR", currencyDisplay:"code", minimumFractionDigits:2, maximumFractionDigits:2 });
const fmt  = n => PKR.format(parseFloat(n) || 0);
const fmtN = n => (parseFloat(n) || 0).toLocaleString("en-AE");
const esc  = s => String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
const $    = id => document.getElementById(id);
const setEl = (id, v) => { const e=$(id); if(e) e.textContent=v; };

// Per-company switches (tenancy/features.py, via base.html). A switched-off
// widget is not rendered and its endpoint refuses, so it is not loaded either.
const featureOn = (group, sub) => !window.financeeFeatureEnabled || window.financeeFeatureEnabled(group, sub);
const dashOn    = sub => featureOn("dashboard", sub);
const pdfOn     = () => featureOn("pdf_export", "reports");

function skeletonRows(r=3, c=4) {
  return Array.from({length:r},()=>`<tr>${Array.from({length:c},()=>`<td><div class="skeleton"></div></td>`).join("")}</tr>`).join("");
}
function emptyState(msg="No data available") {
  return `<div class="empty-state"><i class="fa-solid fa-inbox"></i><p>${msg}</p></div>`;
}
function rankBadge(n) {
  const cls = n===1?"rank-1":n===2?"rank-2":n===3?"rank-3":"rank-n";
  return `<span class="rank-badge ${cls}">${n}</span>`;
}
function rangeToParams(range) {
  const now=new Date(), s=d=>d.toISOString().slice(0,10);
  if(range==="today")  return {from:s(now), to:s(now)};
  if(range==="7d")  { const d=new Date(now); d.setDate(d.getDate()-7); return {from:s(d),to:s(now)}; }
  if(range==="30d") { const d=new Date(now); d.setDate(d.getDate()-30); return {from:s(d),to:s(now)}; }
  if(range==="mtd") { const d=new Date(now.getFullYear(),now.getMonth(),1); return {from:s(d),to:s(now)}; }
  if(range==="ytd") { const d=new Date(now.getFullYear(),0,1); return {from:s(d),to:s(now)}; }
  return {};
}

async function apiFetch(url, params={}, method="GET", body=null) {
  const qs = Object.keys(params).length ? "?"+new URLSearchParams(params) : "";
  const opts = { headers:{"X-Requested-With":"XMLHttpRequest"} };
  if(method==="POST") {
    opts.method="POST";
    opts.headers["Content-Type"]="application/json";
    opts.headers["X-CSRFToken"] = getCsrf();
    opts.body = JSON.stringify(body);
  }
  try {
    const r = await fetch(url+qs, opts);
    if(!r.ok) return null;
    let j = await r.json();

    // Unwrap {status, data} envelope (new dash endpoints)
    if(j && typeof j === "object" && !Array.isArray(j) && "status" in j && "data" in j) {
      j = j.data;
    }

    // Handle double-encoded JSON: legacy endpoints return JsonResponse(json_string)
    // so the browser parses the outer JSON and gets a string — parse it again.
    if(typeof j === "string") {
      try { j = JSON.parse(j); } catch { /* leave as-is */ }
    }

    return j;
  } catch { return null; }
}
function getCsrf() {
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] || "";
}

// ══════════════════════════════════════════════════════════════════════════
// INIT
// ══════════════════════════════════════════════════════════════════════════
document.addEventListener("DOMContentLoaded", () => {
  $("dash-date").textContent = new Date().toLocaleDateString("en-PK",{weekday:"long",year:"numeric",month:"long",day:"numeric"});
  initDashboard();
  bindEvents();
});

async function initDashboard() {
  // Dashboard sub-feature -> its loaders.
  const widgets = {
    smart_alerts:        [() => loadSmartAlerts()],
    sales_overview:      [() => loadSalesToday(), () => loadSalesChart("7d")],
    stock_overview:      [() => loadStockKpi(), () => loadLowStock(), () => loadFastMoving(30), () => loadStaleStock(30)],
    top_parties:         [() => loadTopCustomers(), () => loadTopVendors()],
    receivables_aging:   [() => loadReceivablesAging()],
    recent_transactions: [() => loadRecentTransactions()],
    expenses:            [() => loadExpenseKpi(), () => loadExpenseCategories(), () => loadExpenseDescriptions()],
    cash_balance:        [() => loadCashBalance()],
    balances:            [() => loadPartyBalanceSummary(), () => loadReceivableSummary(), () => loadPayableSummary(),
                          () => loadExpensePartySummary(), () => loadPartiesSummary()],
  };
  const jobs = [];
  Object.entries(widgets).forEach(([sub, loaders]) => {
    if (dashOn(sub)) loaders.forEach(load => jobs.push(load()));
  });
  // The draft card has its own switch and only renders when allowed.
  jobs.push(loadDraftCard());
  await Promise.allSettled(jobs);
}

// ══════════════════════════════════════════════════════════════════════════
// SMART ALERTS — popup, dismiss-for-today via localStorage
// ══════════════════════════════════════════════════════════════════════════
async function loadSmartAlerts() {
  const today = new Date().toISOString().slice(0,10);
  const dismissed = localStorage.getItem("dash_alerts_dismissed");
  if(dismissed === today) return; // suppressed for today

  const data = await apiFetch(API.smartAlerts);
  if(!data || !data.length) return;

  const badge = $("bell-badge");
  badge.textContent = data.length;
  badge.style.display = "flex";

  const body = $("alerts-modal-body");
  body.innerHTML = data.map(a => `
    <div class="alert-item ${a.type}">
      <i class="fa-solid ${a.icon}"></i>
      <div><strong>${esc(a.title)}</strong>${esc(a.message)}</div>
    </div>`).join("");

  // Auto-open only if not dismissed
  showModal("alerts-modal-overlay");
}

// Bell click → always show
$("dash-alerts-bell")?.addEventListener("click", async () => {
  const today = new Date().toISOString().slice(0,10);
  localStorage.removeItem("dash_alerts_dismissed"); // force reload
  await loadSmartAlerts();
  showModal("alerts-modal-overlay");
});

$("alerts-modal-ok")?.addEventListener("click", () => {
  if($("alerts-dismiss-today").checked) {
    localStorage.setItem("dash_alerts_dismissed", new Date().toISOString().slice(0,10));
  }
  closeModal("alerts-modal-overlay");
});
$("alerts-modal-close")?.addEventListener("click", () => closeModal("alerts-modal-overlay"));

// ══════════════════════════════════════════════════════════════════════════
// 1. SALES TODAY KPIs
// ══════════════════════════════════════════════════════════════════════════
async function loadSalesToday() {
  const data = await apiFetch(API.salesToday);
  if(!data) return;
  setEl("kpi-sales-today", fmt(data.sales_today));
  setEl("kpi-invoice-count", fmtN(data.invoice_count)+" invoices today");
  setEl("kpi-profit-today", fmt(data.profit_today));
}

// ══════════════════════════════════════════════════════════════════════════
// 2. SALES CHART (fixed: explicit re-trigger on custom dates)
// ══════════════════════════════════════════════════════════════════════════
let salesChart = null;
let lastChartData = [];

async function loadSalesChart(preset, customFrom, customTo) {
  let params = {};
  if(preset && preset !== "custom") params = rangeToParams(preset);
  else if(customFrom && customTo)   params = {from:customFrom, to:customTo};

  const data = await apiFetch(API.salesChart, params);
  if(!data || !data.length) return;
  lastChartData = data;

  const labels   = data.map(d=>d.label);
  const revenues = data.map(d=>parseFloat(d.revenue)||0);
  const profits  = data.map(d=>parseFloat(d.profit)||0);

  // Update chart KPI summary row
  const totalRev = revenues.reduce((a,b)=>a+b,0);
  const totalPro = profits.reduce((a,b)=>a+b,0);
  const avgRev   = revenues.length ? totalRev/revenues.length : 0;
  const peakIdx  = revenues.indexOf(Math.max(...revenues));
  setEl("chart-total-revenue", fmt(totalRev));
  setEl("chart-total-profit",  fmt(totalPro));
  setEl("chart-avg-revenue",   fmt(avgRev));
  setEl("chart-peak-day", labels[peakIdx] || "—");

  const ctx = $("sales-chart")?.getContext("2d");
  if(!ctx) return;
  if(salesChart) salesChart.destroy();

  salesChart = new Chart(ctx, {
    type:"bar",
    data: {
      labels,
      datasets:[
        {
          label:"Revenue", data:revenues, type:"bar",
          backgroundColor:"rgba(59,130,246,.15)", borderColor:"#3b82f6",
          borderWidth:2, borderRadius:6, order:2,
        },
        {
          label:"Profit", data:profits, type:"line",
          borderColor:"#10b981", backgroundColor:"rgba(16,185,129,.07)",
          borderWidth:2.5, pointRadius:5, pointBackgroundColor:"#10b981",
          tension:0.4, fill:true, order:1,
        },
      ],
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      interaction:{mode:"index",intersect:false},
      plugins:{
        legend:{position:"top",labels:{boxWidth:12,font:{size:11}}},
        tooltip:{callbacks:{label:c=>` ${c.dataset.label}: ${PKR.format(c.parsed.y)}`}},
      },
      scales:{
        x:{grid:{display:false},ticks:{font:{size:11}}},
        y:{grid:{color:"#f1f5f9"},ticks:{callback:v=>"PKR "+(v>=1000?(v/1000).toFixed(0)+"k":v),font:{size:10}}},
      },
    },
  });
}

// Apply custom date range button
$("sales-custom-apply")?.addEventListener("click", () => {
  const from = $("sales-from").value;
  const to   = $("sales-to").value;
  if(from && to) {
    document.querySelectorAll("[data-sales-range]").forEach(b=>b.classList.remove("active"));
    loadSalesChart("custom", from, to);
  }
});

// Preset buttons
document.addEventListener("click", async e => {
  if(e.target.matches("[data-sales-range]")) {
    document.querySelectorAll("[data-sales-range]").forEach(b=>b.classList.remove("active"));
    e.target.classList.add("active");
    $("sales-from").value = "";
    $("sales-to").value   = "";
    await loadSalesChart(e.target.dataset.salesRange);
  }
});

// Chart PDF — includes the actual chart image
$("chart-pdf-btn")?.addEventListener("click", async () => {
  const {jsPDF} = window.jspdf;
  const doc = new jsPDF({orientation:"landscape",unit:"mm",format:"a4"});
  const ts  = new Date().toLocaleDateString("en-PK");

  // Title
  doc.setFontSize(18); doc.setTextColor(30,41,59);
  doc.text("Revenue & Profit Trend Report", 14, 18);
  doc.setFontSize(9); doc.setTextColor(100);
  doc.text("Generated: "+ts, 14, 24);

  // KPI summary
  doc.setFontSize(10); doc.setTextColor(30,41,59);
  const kpis = [
    ["Total Revenue", $("chart-total-revenue").textContent],
    ["Total Profit",  $("chart-total-profit").textContent],
    ["Avg Daily Revenue", $("chart-avg-revenue").textContent],
    ["Peak Day", $("chart-peak-day").textContent],
  ];
  doc.autoTable({
    startY:28, head:[["Metric","Value"]], body:kpis,
    styles:{fontSize:9}, headStyles:{fillColor:[59,130,246]},
    columnStyles:{0:{fontStyle:"bold"}, 1:{halign:"right"}},
    margin:{left:14},
    tableWidth:100,
  });

  // Chart image
  const canvas = $("sales-chart");
  if(canvas) {
    const imgData = canvas.toDataURL("image/png");
    const startY  = doc.lastAutoTable.finalY + 6;
    doc.addImage(imgData, "PNG", 14, startY, 265, 110);
  }

  // Data table
  if(lastChartData.length) {
    const finalY = doc.lastAutoTable ? doc.lastAutoTable.finalY : 150;
    doc.addPage();
    doc.setFontSize(12); doc.text("Daily Breakdown", 14, 16);
    doc.autoTable({
      startY:20,
      head:[["Date","Revenue","Profit"]],
      body: lastChartData.map(r=>[r.label, fmt(r.revenue), fmt(r.profit)]),
      styles:{fontSize:8}, headStyles:{fillColor:[59,130,246]},
    });
  }
  doc.save(`revenue_profit_${new Date().toISOString().slice(0,10)}.pdf`);
  if (globalThis.FinanceeActivity) globalThis.FinanceeActivity.exported("pdf");
});

// ══════════════════════════════════════════════════════════════════════════
// 3. CASH BALANCE KPI + LEDGER MODAL
// ══════════════════════════════════════════════════════════════════════════
async function loadCashBalance() {
  const data = await apiFetch(API.cashBalance);
  if(data === null) return;
  const bal = parseFloat(data.cash_balance)||0;
  setEl("kpi-cash-balance", fmt(bal));
  const card = $("cash-kpi-card");
  if(card) {
    card.querySelector(".kpi-accent").className = "kpi-accent " + (bal < 0 ? "accent-red" : "accent-cyan");
  }
}

$("cash-kpi-card")?.addEventListener("click", function () {
  // Opens the ledger only while the Cash Ledger report is on (data-ledger).
  if (this.dataset.ledger !== "1") return;
  // Pre-fill last 7 days
  const now = new Date();
  const from7 = new Date(now); from7.setDate(from7.getDate()-6);
  $("cash-from").value = from7.toISOString().slice(0,10);
  $("cash-to").value   = now.toISOString().slice(0,10);
  showModal("cash-modal-overlay");
  loadCashLedger();
});

$("cash-load-btn")?.addEventListener("click", loadCashLedger);
$("cash-modal-close")?.addEventListener("click", () => closeModal("cash-modal-overlay"));

let cashLedgerData = [];
async function loadCashLedger() {
  const from = $("cash-from").value;
  const to   = $("cash-to").value;
  if(!from || !to) return;

  const tbody = $("cash-ledger-body");
  tbody.innerHTML = skeletonRows(6,7);
  $("cash-kpi-row").innerHTML = "";

  const data = await apiFetch(API.cashLedger, {}, "POST", {from_date:from, to_date:to});
  if(!data || !Array.isArray(data) || !data.length) {
    tbody.innerHTML = `<tr><td colspan="7">${emptyState("No cash transactions in this period")}</td></tr>`;
    return;
  }
  cashLedgerData = data;

  // Compute KPIs
  const totalDebit  = data.reduce((s,r)=>s+(parseFloat(r.debit)||0),  0);
  const totalCredit = data.reduce((s,r)=>s+(parseFloat(r.credit)||0), 0);
  const closing     = parseFloat(data[data.length-1].balance)||0;

  $("cash-kpi-row").innerHTML = `
    <div class="modal-kpi kpi-inflow">
      <div class="modal-kpi-icon"><i class="fa-solid fa-arrow-down"></i></div>
      <div class="modal-kpi-label">Total Inflow</div>
      <div class="modal-kpi-val td-pos">${fmt(totalDebit)}</div>
    </div>
    <div class="modal-kpi kpi-outflow">
      <div class="modal-kpi-icon"><i class="fa-solid fa-arrow-up"></i></div>
      <div class="modal-kpi-label">Total Outflow</div>
      <div class="modal-kpi-val td-neg">${fmt(totalCredit)}</div>
    </div>
    <div class="modal-kpi ${closing<0?"kpi-outflow":"kpi-balance"}">
      <div class="modal-kpi-icon"><i class="fa-solid fa-coins"></i></div>
      <div class="modal-kpi-label">Closing Balance</div>
      <div class="modal-kpi-val ${closing<0?"td-neg":"td-pos"}">${fmt(closing)}</div>
    </div>`;

  tbody.innerHTML = data.map(r => {
    const bal = parseFloat(r.balance)||0;
    return `<tr>
      <td>${esc(r.entry_date||"")}</td>
      <td class="td-muted">${r.journal_id||"—"}</td>
      <td class="td-name">${esc(r.party_name||"—")}</td>
      <td>${esc(r.description||"")}</td>
      <td class="td-pos">${r.debit?fmt(r.debit):""}</td>
      <td class="td-neg">${r.credit?fmt(r.credit):""}</td>
      <td class="${bal<0?"td-neg":"td-pos"} td-amount">${fmt(bal)}</td>
    </tr>`;
  }).join("");
}

// Cash PDF
$("cash-pdf-btn")?.addEventListener("click", () => {
  if(!cashLedgerData.length) return;
  const {jsPDF} = window.jspdf;
  const doc = new jsPDF({orientation:"landscape",unit:"mm",format:"a4"});
  doc.setFontSize(16); doc.text("Cash Ledger", 14, 16);
  doc.setFontSize(9); doc.setTextColor(100);
  doc.text(`Period: ${$("cash-from").value} to ${$("cash-to").value}  |  Generated: ${new Date().toLocaleDateString("en-PK")}`, 14, 22);
  doc.autoTable({
    startY:26,
    head:[["Date","Journal #","Party","Description","Debit","Credit","Balance"]],
    body: cashLedgerData.map(r=>[
      r.entry_date||"", r.journal_id||"—", r.party_name||"—", r.description||"",
      r.debit?fmt(r.debit):"", r.credit?fmt(r.credit):"", fmt(r.balance)
    ]),
    styles:{fontSize:7.5}, headStyles:{fillColor:[6,182,212]},
    columnStyles:{4:{halign:"right"},5:{halign:"right"},6:{halign:"right",fontStyle:"bold"}},
  });
  doc.save(`cash_ledger_${$("cash-from").value}_${$("cash-to").value}.pdf`);
  if (globalThis.FinanceeActivity) globalThis.FinanceeActivity.exported("pdf");
});

// ══════════════════════════════════════════════════════════════════════════
// 4. STOCK KPIs
// ══════════════════════════════════════════════════════════════════════════
async function loadStockKpi() {
  const data = await apiFetch(API.stockKpi);
  if(!data) return;
  setEl("kpi-total-units", fmtN(data.total_units));
  setEl("kpi-total-items", fmtN(data.total_items)+" total items");
}

// ══════════════════════════════════════════════════════════════════════════
// 5. LOW STOCK
// ══════════════════════════════════════════════════════════════════════════
async function loadLowStock(threshold=5) {
  const tbody = $("low-stock-body");
  if(!tbody) return;
  tbody.innerHTML = skeletonRows(4,4);
  const data = await apiFetch(API.lowStock, {threshold});
  if(!data||!data.length) { tbody.innerHTML=`<tr><td colspan="4">${emptyState("All items sufficiently stocked ✓")}</td></tr>`; return; }
  const pct = u => Math.min(100,(u/threshold)*100);
  const cls = u => u===0?"low":u<3?"low":"med";
  tbody.innerHTML = data.map(r=>`
    <tr>
      <td class="td-name">${esc(r.item_name)}</td>
      <td class="td-muted">${esc(r.category)}</td>
      <td>
        <strong style="color:${r.units_in_stock===0?"var(--ink-red)":r.units_in_stock<3?"var(--ink-amber)":"var(--ink-green)"}">${r.units_in_stock}</strong>
        <div class="stock-bar-track"><div class="stock-bar-fill ${cls(r.units_in_stock)}" style="width:${pct(r.units_in_stock)}%"></div></div>
      </td>
      <td class="td-amount">${fmt(r.sale_price)}</td>
    </tr>`).join("");
}
$("low-stock-threshold")?.addEventListener("change", function(){ loadLowStock(parseInt(this.value)||5); });

// ══════════════════════════════════════════════════════════════════════════
// 6. FAST MOVING
// ══════════════════════════════════════════════════════════════════════════
async function loadFastMoving(days=30) {
  const tbody = $("fast-moving-body");
  if(!tbody) return;
  tbody.innerHTML = skeletonRows(5,5);
  const data = await apiFetch(API.fastMoving, {days, limit:10});
  if(!data||!data.length) { tbody.innerHTML=`<tr><td colspan="5">${emptyState("No sales in this period")}</td></tr>`; return; }
  tbody.innerHTML = data.map((r,i)=>`
    <tr>
      <td>${rankBadge(i+1)}</td>
      <td class="td-name">${esc(r.item_name)}</td>
      <td class="td-muted">${esc(r.category)}</td>
      <td><strong>${fmtN(r.units_sold)}</strong></td>
      <td class="td-amount">${fmt(r.revenue)}</td>
    </tr>`).join("");
}
document.addEventListener("click", async e => {
  if(e.target.matches("[data-fast-days]")) {
    document.querySelectorAll("[data-fast-days]").forEach(b=>b.classList.remove("active"));
    e.target.classList.add("active");
    await loadFastMoving(parseInt(e.target.dataset.fastDays));
  }
});

// ══════════════════════════════════════════════════════════════════════════
// 7. STALE STOCK
// ══════════════════════════════════════════════════════════════════════════
async function loadStaleStock(days=30) {
  const tbody = $("stale-stock-body");
  if(!tbody) return;
  tbody.innerHTML = skeletonRows(4,5);
  const data = await apiFetch(API.staleStock, {days});
  if(!data||!data.length) { tbody.innerHTML=`<tr><td colspan="5">${emptyState("No stale items ✓")}</td></tr>`; return; }
  tbody.innerHTML = data.map(r=>`
    <tr>
      <td class="td-name">${esc(r.item_name)}</td>
      <td class="td-muted">${esc(r.category)}</td>
      <td>${r.last_sold_date||'<span style="color:var(--ink-red);font-size:.72rem;font-weight:700;">Never sold</span>'}</td>
      <td><span class="days-badge ${(r.days_stale||999)>60?"days-overdue":(r.days_stale||999)>30?"days-medium":"days-fresh"}">${r.days_stale??'N/A'} d</span></td>
      <td>${fmtN(r.units_in_stock)} units</td>
    </tr>`).join("");
}
document.addEventListener("click", async e => {
  if(e.target.matches("[data-stale-days]")) {
    document.querySelectorAll("[data-stale-days]").forEach(b=>b.classList.remove("active"));
    e.target.classList.add("active");
    await loadStaleStock(parseInt(e.target.dataset.staleDays));
  }
});

// ══════════════════════════════════════════════════════════════════════════
// 8. TOP CUSTOMERS & VENDORS
// ══════════════════════════════════════════════════════════════════════════
async function loadTopCustomers(p={}) {
  const tbody = $("top-customers-body");
  if(!tbody) return;
  tbody.innerHTML = skeletonRows(5,5);
  const data = await apiFetch(API.topCustomers, {limit:5,...p});
  if(!data||!data.length) { tbody.innerHTML=`<tr><td colspan="5">${emptyState("No customer data")}</td></tr>`; return; }
  tbody.innerHTML = data.map((r,i)=>`
    <tr>
      <td>${rankBadge(i+1)}</td>
      <td class="td-name">${esc(r.party_name)}</td>
      <td class="td-muted">${r.invoice_count}</td>
      <td class="td-muted">${r.last_purchase}</td>
      <td class="td-amount">${fmt(r.total_purchases)}</td>
    </tr>`).join("");
}
async function loadTopVendors(p={}) {
  const tbody = $("top-vendors-body");
  if(!tbody) return;
  tbody.innerHTML = skeletonRows(5,5);
  const data = await apiFetch(API.topVendors, {limit:5,...p});
  if(!data||!data.length) { tbody.innerHTML=`<tr><td colspan="5">${emptyState("No vendor data")}</td></tr>`; return; }
  tbody.innerHTML = data.map((r,i)=>`
    <tr>
      <td>${rankBadge(i+1)}</td>
      <td class="td-name">${esc(r.party_name)}</td>
      <td class="td-muted">${r.invoice_count}</td>
      <td class="td-muted">${r.last_purchase}</td>
      <td class="td-amount">${fmt(r.total_purchased)}</td>
    </tr>`).join("");
}
document.addEventListener("click", async e => {
  if(e.target.matches("[data-party-range]")) {
    document.querySelectorAll("[data-party-range]").forEach(b=>b.classList.remove("active"));
    e.target.classList.add("active");
    const p = rangeToParams(e.target.dataset.partyRange);
    await Promise.all([loadTopCustomers(p), loadTopVendors(p)]);
  }
});

// ══════════════════════════════════════════════════════════════════════════
// 9. RECEIVABLES AGING
// ══════════════════════════════════════════════════════════════════════════
let agingData = null;
async function loadReceivablesAging() {
  const data = await apiFetch(API.receivablesAging);
  agingData = data;
  if(!data) return;
  setEl("aging-overdue-amount", fmt(data.total_overdue_amount));
  setEl("aging-medium-amount",  fmt(data.total_medium_amount));
  setEl("aging-fresh-amount",   fmt(data.total_fresh_amount));
  setEl("aging-overdue-count", (data.overdue||[]).length+" parties");
  setEl("aging-medium-count",  (data.medium_risk||[]).length+" parties");
  setEl("aging-fresh-count",   (data.fresh||[]).length+" parties");
  renderAgingTable("overdue");
}
function renderAgingTable(bucket) {
  const tbody = $("aging-table-body");
  if(!tbody||!agingData) return;
  document.querySelectorAll(".aging-bucket").forEach(b=>b.classList.remove("active"));
  document.querySelector(`[data-aging="${bucket}"]`)?.classList.add("active");
  const rows = agingData[bucket==="overdue"?"overdue":bucket==="medium"?"medium_risk":"fresh"]||[];
  if(!rows.length) { tbody.innerHTML=`<tr><td colspan="4">${emptyState("No entries in this bucket")}</td></tr>`; return; }
  const cls = bucket==="overdue"?"days-overdue":bucket==="medium"?"days-medium":"days-fresh";
  tbody.innerHTML = rows.map(r=>`
    <tr>
      <td class="td-name">${esc(r.party_name)}</td>
      <td class="td-amount">${fmt(r.balance)}</td>
      <td class="td-muted">${r.last_txn}</td>
      <td><span class="days-badge ${cls}">${r.days_overdue} days</span></td>
    </tr>`).join("");
}
document.addEventListener("click", e => {
  const b = e.target.closest("[data-aging]");
  if(b) renderAgingTable(b.dataset.aging);
});

// ══════════════════════════════════════════════════════════════════════════
// 10. RECENT TRANSACTIONS
// ══════════════════════════════════════════════════════════════════════════
let allTxns = [];
async function loadRecentTransactions() {
  const feed = $("txn-feed");
  if(!feed) return;
  feed.innerHTML = `<div class="skeleton" style="height:50px;margin-bottom:6px"></div>`.repeat(4);
  const data = await apiFetch(API.recentTransactions, {limit:20});
  allTxns = data||[];
  renderTxns(allTxns);
}
function renderTxns(list) {
  const feed = $("txn-feed");
  if(!feed) return;
  if(!list.length) { feed.innerHTML = emptyState("No recent transactions"); return; }
  const iconMap  = {Sale:"fa-arrow-trend-up",Purchase:"fa-cart-shopping",Receipt:"fa-arrow-down-to-bracket",Payment:"fa-arrow-up-from-bracket"};
  const clsMap   = {Sale:"txn-sale",Purchase:"txn-purchase",Receipt:"txn-receipt",Payment:"txn-payment"};
  const badgeMap = {Sale:"badge-sale",Purchase:"badge-purchase",Receipt:"badge-receipt",Payment:"badge-payment"};
  feed.innerHTML = `<div class="txn-list">${list.map(r=>`
    <div class="txn-item">
      <div class="txn-icon ${clsMap[r.type]||"txn-sale"}"><i class="fa-solid ${iconMap[r.type]||"fa-circle"}"></i></div>
      <div class="txn-body">
        <div class="txn-title">${esc(r.party_name)}</div>
        <div class="txn-meta">${r.txn_date} &nbsp;·&nbsp;<span class="txn-type-badge ${badgeMap[r.type]}">${r.type}</span></div>
      </div>
      <div class="txn-amount">${fmt(r.amount)}</div>
    </div>`).join("")}</div>`;
}
$("txn-search")?.addEventListener("input", function() {
  const q=this.value.toLowerCase();
  renderTxns(allTxns.filter(t=>t.party_name.toLowerCase().includes(q)||t.type.toLowerCase().includes(q)));
});
document.addEventListener("click", e => {
  if(e.target.matches("[data-txn-type]")) {
    document.querySelectorAll("[data-txn-type]").forEach(b=>b.classList.remove("active"));
    e.target.classList.add("active");
    const type = e.target.dataset.txnType;
    renderTxns(type==="all"?allTxns:allTxns.filter(t=>t.type===type));
  }
});

// ══════════════════════════════════════════════════════════════════════════
// 11. EXPENSE KPIs & CATEGORIES
// ══════════════════════════════════════════════════════════════════════════
async function loadExpenseKpi() {
  const data = await apiFetch(API.expenseKpi);
  if(!data) return;
  setEl("kpi-expense-today", fmt(data.today));
  setEl("kpi-expense-month", fmt(data.this_month));
  setEl("kpi-expense-year",  fmt(data.this_year));
}
async function loadExpenseCategories(p={}) {
  const cont = $("expense-cat-list");
  if(!cont) return;
  cont.innerHTML = `<div class="skeleton" style="height:24px;margin-bottom:8px"></div>`.repeat(3);
  const data = await apiFetch(API.expenseCategories, {limit:6,...p});
  if(!data||!data.length) { cont.innerHTML=emptyState("No expense data"); return; }
  const max = Math.max(...data.map(d=>parseFloat(d.total)));
  cont.innerHTML = `<div class="expense-cat-list">${data.map(d=>`
    <div class="expense-cat-item">
      <div class="expense-cat-label"><strong>${esc(d.category)}</strong><span>${fmt(d.total)}</span></div>
      <div class="expense-bar-track"><div class="expense-bar-fill" style="width:${((parseFloat(d.total)/max)*100).toFixed(1)}%"></div></div>
    </div>`).join("")}</div>`;
}
async function loadExpenseDescriptions(p={}) {
  const tbody = $("expense-desc-body");
  if(!tbody) return;
  tbody.innerHTML = skeletonRows(4,5);
  const data = await apiFetch(API.expenseDescriptions, {limit:8,...p});
  if(!data||!data.length) { tbody.innerHTML=`<tr><td colspan="5">${emptyState("No data")}</td></tr>`; return; }
  tbody.innerHTML = data.map((r,i)=>`
    <tr>
      <td>${rankBadge(i+1)}</td>
      <td class="td-name">${esc(r.description)}</td>
      <td class="td-muted">${esc(r.category)}</td>
      <td class="td-amount">${fmt(r.total)}</td>
      <td class="td-muted">${r.count}×</td>
    </tr>`).join("");
}
document.addEventListener("click", async e => {
  if(e.target.matches("[data-expense-range]")) {
    document.querySelectorAll("[data-expense-range]").forEach(b=>b.classList.remove("active"));
    e.target.classList.add("active");
    const p = rangeToParams(e.target.dataset.expenseRange);
    await Promise.all([loadExpenseCategories(p)]);
  }
  if(e.target.matches("[data-expense-range2]")) {
    document.querySelectorAll("[data-expense-range2]").forEach(b=>b.classList.remove("active"));
    e.target.classList.add("active");
    await loadExpenseDescriptions(rangeToParams(e.target.dataset.expenseRange2));
  }
});

// ══════════════════════════════════════════════════════════════════════════
// 12. PARTY BALANCES MODAL
// ══════════════════════════════════════════════════════════════════════════
let pbAllData = [];
async function loadPartyBalanceSummary() {
  const data = await apiFetch(API.partyBalances);
  const arr = Array.isArray(data) ? data : (data ? Object.values(data) : []);
  pbAllData = arr;
  setEl("pb-total-count", arr.length);
  setEl("pb-total-meta", "Total parties with balance");
}
async function openPartyBalance() {
  showModal("party-balance-modal-overlay");
  if(!pbAllData.length) {
    const data = await apiFetch(API.partyBalances);
    pbAllData = Array.isArray(data) ? data : (data ? Object.values(data) : []);
  }
  renderPartyBalance(pbAllData);
}
function renderPartyBalance(list) {
  const tbody = $("party-balance-body");
  if(!tbody) return;
  if(!list.length) { tbody.innerHTML=`<tr><td colspan="5">${emptyState("No party balances")}</td></tr>`; return; }
  tbody.innerHTML = list.map(r => {
    // Legacy endpoints return {name, balance} — balance is net (positive=debit, negative=credit)
    const name    = r.party_name || r.name || "";
    const ptype   = r.party_type || r.type || "—";
    const net     = parseFloat(r.balance ?? (r.debit_balance - r.credit_balance) ?? 0);
    const debit   = net > 0 ? net : 0;
    const credit  = net < 0 ? Math.abs(net) : 0;
    return `<tr>
      <td class="td-name">${esc(name)}</td>
      <td class="td-muted">${esc(ptype)}</td>
      <td class="${debit?"td-pos":""}">${debit ? fmt(debit) : "—"}</td>
      <td class="${credit?"td-neg":""}">${credit ? fmt(credit) : "—"}</td>
      <td class="${net<0?"td-neg":"td-pos"} td-amount">${fmt(Math.abs(net))} ${net<0?"(Cr)":"(Dr)"}</td>
    </tr>`;
  }).join("");
}
// Filters
$("pb-search")?.addEventListener("input", filterPB);
$("pb-type-filter")?.addEventListener("change", filterPB);
$("pb-balance-filter")?.addEventListener("change", filterPB);
function filterPB() {
  const q    = ($("pb-search")?.value||"").toLowerCase();
  const type = ($("pb-type-filter")?.value||"").toLowerCase();
  const bal  = ($("pb-balance-filter")?.value||"");
  renderPartyBalance(pbAllData.filter(r => {
    const name = (r.party_name||r.name||"").toLowerCase();
    const rtype= (r.party_type||r.type||"").toLowerCase();
    const net  = parseFloat(r.balance??0);
    if(q && !name.includes(q)) return false;
    if(type && !rtype.includes(type)) return false;
    if(bal==="debit"  && net <= 0) return false;
    if(bal==="credit" && net >= 0) return false;
    return true;
  }));
}

// ══════════════════════════════════════════════════════════════════════════
// 13. RECEIVABLE MODAL
// ══════════════════════════════════════════════════════════════════════════
let recAllData = [];
async function loadReceivableSummary() {
  const data = await apiFetch(API.receivable);
  const arr  = Array.isArray(data)?data:(data?Object.values(data):[]);
  recAllData = arr;
  // balance is positive for receivable
  const total = arr.reduce((s,r)=>s+Math.abs(parseFloat(r.balance??0)),0);
  setEl("rec-total", fmt(total));
  setEl("rec-count", arr.length+" parties");
}
async function openReceivable() {
  showModal("receivable-modal-overlay");
  if(!recAllData.length) { const d=await apiFetch(API.receivable); recAllData=Array.isArray(d)?d:(d?Object.values(d):[]); }
  renderReceivable(recAllData);
}
function renderReceivable(list) {
  const tbody=$("receivable-body");
  if(!tbody) return;
  if(!list.length) { tbody.innerHTML=`<tr><td colspan="2">${emptyState("No receivables")}</td></tr>`; return; }
  tbody.innerHTML = list.map(r=>`
    <tr>
      <td class="td-name">${esc(r.party_name||r.name||"")}</td>
      <td class="td-pos td-amount">${fmt(Math.abs(parseFloat(r.balance??r.receivable??0)))}</td>
    </tr>`).join("");
}
$("rec-search")?.addEventListener("input", function() {
  const q=this.value.toLowerCase();
  renderReceivable(recAllData.filter(r=>(r.party_name||r.name||"").toLowerCase().includes(q)));
});

// ══════════════════════════════════════════════════════════════════════════
// 14. PAYABLE MODAL
// ══════════════════════════════════════════════════════════════════════════
let payAllData = [];
async function loadPayableSummary() {
  const data = await apiFetch(API.payable);
  const arr  = Array.isArray(data)?data:(data?Object.values(data):[]);
  payAllData = arr;
  const total = arr.reduce((s,r)=>s+Math.abs(parseFloat(r.balance??r.payable??0)),0);
  setEl("pay-total", fmt(total));
  setEl("pay-count", arr.length+" parties");
}
async function openPayable() {
  showModal("payable-modal-overlay");
  if(!payAllData.length) { const d=await apiFetch(API.payable); payAllData=Array.isArray(d)?d:(d?Object.values(d):[]); }
  renderPayable(payAllData);
}
function renderPayable(list) {
  const tbody=$("payable-body");
  if(!tbody) return;
  if(!list.length) { tbody.innerHTML=`<tr><td colspan="2">${emptyState("No payables")}</td></tr>`; return; }
  tbody.innerHTML = list.map(r=>`
    <tr>
      <td class="td-name">${esc(r.party_name||r.name||"")}</td>
      <td class="td-neg td-amount">${fmt(Math.abs(parseFloat(r.balance??r.payable??0)))}</td>
    </tr>`).join("");
}
$("pay-search")?.addEventListener("input", function() {
  const q=this.value.toLowerCase();
  renderPayable(payAllData.filter(r=>(r.party_name||r.name||"").toLowerCase().includes(q)));
});

// ══════════════════════════════════════════════════════════════════════════
// 15. EXPENSE PARTIES MODAL
// ══════════════════════════════════════════════════════════════════════════
let epAllData = [];
async function loadExpensePartySummary() {
  const data = await apiFetch(API.expenseParties);
  const arr  = Array.isArray(data)?data:(data?Object.values(data):[]);
  epAllData  = arr;
  const total= arr.reduce((s,r)=>s+Math.abs(parseFloat(r.balance??0)),0);
  setEl("ep-total", fmt(total));
}
async function openExpenseParty() {
  showModal("exp-party-modal-overlay");
  if(!epAllData.length) { const d=await apiFetch(API.expenseParties); epAllData=Array.isArray(d)?d:(d?Object.values(d):[]); }
  renderExpenseParty(epAllData);
}
function renderExpenseParty(list) {
  const tbody=$("exp-party-body");
  if(!tbody) return;
  if(!list.length) { tbody.innerHTML=`<tr><td colspan="2">${emptyState("No data")}</td></tr>`; return; }
  tbody.innerHTML = list.map(r=>{
    const bal = parseFloat(r.balance??0);
    return `<tr>
      <td class="td-name">${esc(r.party_name||r.name||"")}</td>
      <td class="${bal<0?"td-neg":"td-pos"} td-amount">${fmt(Math.abs(bal))} ${bal<0?"(Cr)":"(Dr)"}</td>
    </tr>`;
  }).join("");
}
$("ep-search")?.addEventListener("input", function() {
  const q=this.value.toLowerCase();
  renderExpenseParty(epAllData.filter(r=>(r.party_name||r.name||"").toLowerCase().includes(q)));
});

// ══════════════════════════════════════════════════════════════════════════
// 16. ITEMS MODAL
// ══════════════════════════════════════════════════════════════════════════
let itemsAllData = [];
async function loadAndShowItems() {
  showModal("items-modal-overlay");
  if(!itemsAllData.length) {
    $("items-body").innerHTML = skeletonRows(6,5);
    const data = await apiFetch(API.items);
    itemsAllData = Array.isArray(data)?data:(data?Object.values(data):[]);
    // Populate category filter
    const cats = [...new Set(itemsAllData.map(r=>r.category||"N/A").filter(Boolean))].sort();
    const sel  = $("items-cat-filter");
    cats.forEach(c=>{ const o=document.createElement("option"); o.value=c; o.textContent=c; sel.appendChild(o); });
  }
  renderItems(itemsAllData);
}
function renderItems(list) {
  const tbody=$("items-body");
  if(!tbody) return;
  if(!list.length) { tbody.innerHTML=`<tr><td colspan="5">${emptyState("No items found")}</td></tr>`; return; }
  tbody.innerHTML = list.map(r=>`
    <tr>
      <td class="td-name">${esc(r.item_name||r.name||"")}</td>
      <td class="td-muted">${esc(r.category||"N/A")}</td>
      <td class="td-muted">${esc(r.brand||"—")}</td>
      <td class="td-amount">${fmt(r.sale_price||0)}</td>
      <td>${fmtN(r.units_in_stock||r.stock||0)}</td>
    </tr>`).join("");
}
$("items-search")?.addEventListener("input", function() {
  const q=this.value.toLowerCase(); const cat=$("items-cat-filter").value;
  renderItems(itemsAllData.filter(r=>{
    const n=(r.item_name||r.name||"").toLowerCase();
    const c=(r.category||"");
    return n.includes(q)&&(!cat||c===cat);
  }));
});
$("items-cat-filter")?.addEventListener("change", function() {
  const cat=this.value; const q=$("items-search").value.toLowerCase();
  renderItems(itemsAllData.filter(r=>{
    const n=(r.item_name||r.name||"").toLowerCase();
    const c=(r.category||"");
    return n.includes(q)&&(!cat||c===cat);
  }));
});

// ══════════════════════════════════════════════════════════════════════════
// 17. PARTIES MODAL
// ══════════════════════════════════════════════════════════════════════════
let partiesAllData = [];
async function loadAndShowParties() {
  showModal("parties-modal-overlay");
  if(!partiesAllData.length) {
    $("parties-body").innerHTML = skeletonRows(6,3);
    const data = await apiFetch(API.parties);
    partiesAllData = Array.isArray(data)?data:(data?Object.values(data):[]);
  }
  setEl("parties-total-count", partiesAllData.length);
  renderParties(partiesAllData);
}
async function loadPartiesSummary() {
  const data = await apiFetch(API.parties);
  partiesAllData = Array.isArray(data)?data:(data?Object.values(data):[]);
  setEl("parties-total-count", partiesAllData.length);
}
function renderParties(list) {
  const tbody=$("parties-body");
  if(!tbody) return;
  if(!list.length) { tbody.innerHTML=`<tr><td colspan="3">${emptyState("No parties found")}</td></tr>`; return; }
  tbody.innerHTML = list.map(r=>`
    <tr>
      <td class="td-name">${esc(r.party_name||r.name||"")}</td>
      <td class="td-muted">${esc(r.party_type||r.type||"—")}</td>
      <td class="td-muted">${esc(r.contact_info||r.contact||"—")}</td>
    </tr>`).join("");
}
$("parties-search")?.addEventListener("input", filterParties);
$("parties-type-filter")?.addEventListener("change", filterParties);
function filterParties() {
  const q=($("parties-search")?.value||"").toLowerCase();
  const t=($("parties-type-filter")?.value||"").toLowerCase();
  renderParties(partiesAllData.filter(r=>{
    const n=(r.party_name||r.name||"").toLowerCase();
    const rt=(r.party_type||r.type||"").toLowerCase();
    const c=(r.contact_info||r.contact||"").toLowerCase();
    return (n.includes(q)||c.includes(q))&&(!t||rt.includes(t));
  }));
}

// ══════════════════════════════════════════════════════════════════════════
// MODAL HELPERS
// ══════════════════════════════════════════════════════════════════════════
function showModal(id) { const m=$(id); if(m){ m.style.display="flex"; document.body.style.overflow="hidden"; } }
function closeModal(id) { const m=$(id); if(m){ m.style.display="none"; document.body.style.overflow=""; } }

// Close on overlay click
document.addEventListener("click", e => {
  if(e.target.classList.contains("modal-overlay")) closeModal(e.target.id);
});

// ══════════════════════════════════════════════════════════════════════════
// BIND ALL EVENTS (click-to-open cards and buttons)
// ══════════════════════════════════════════════════════════════════════════
function bindEvents() {
  $("open-party-balance")?.addEventListener("click", openPartyBalance);
  $("open-parties")?.addEventListener("click", loadAndShowParties);
  $("open-parties-qa")?.addEventListener("click", loadAndShowParties);
  $("open-receivable")?.addEventListener("click", openReceivable);
  $("open-payable")?.addEventListener("click", openPayable);
  $("open-exp-party")?.addEventListener("click", openExpenseParty);
  $("open-items-btn")?.addEventListener("click", loadAndShowItems);

  // Modal close buttons (new class)
  document.querySelectorAll(".modal-close-btn").forEach(btn => {
    btn.addEventListener("click", e => {
      const overlay = e.target.closest(".modal-overlay");
      if(overlay) closeModal(overlay.id);
    });
  });

  // Refresh all
  $("dash-refresh-all")?.addEventListener("click", initDashboard);

  // Generic table search
  document.querySelectorAll("[data-search-for]").forEach(inp => {
    inp.addEventListener("input", function() {
      const q=this.value.toLowerCase();
      document.querySelector(`#${this.dataset.searchFor} tbody`)
        ?.querySelectorAll("tr")
        .forEach(tr=>{ tr.style.display=tr.textContent.toLowerCase().includes(q)?"":"none"; });
    });
  });

  // PDF buttons for simple sections
  document.addEventListener("click", e => {
    const btn = e.target.closest("[data-pdf]");
    if(!btn || btn.id==="chart-pdf-btn" || btn.id==="cash-pdf-btn") return;
    exportSectionPdf(btn.dataset.pdf);
  });

  // PDF for modals
  $("pb-pdf-btn")?.addEventListener("click", ()=>exportModalPdf("Party Balances","party-balance-table"));
  $("rec-pdf-btn")?.addEventListener("click",()=>exportModalPdf("Accounts Receivable","receivable-table"));
  $("pay-pdf-btn")?.addEventListener("click",()=>exportModalPdf("Accounts Payable","payable-table"));
  $("items-pdf-btn")?.addEventListener("click",()=>exportModalPdf("Items List","items-table"));
  $("parties-pdf-btn")?.addEventListener("click",()=>exportModalPdf("Parties List","parties-table"));
  $("ep-pdf-btn")?.addEventListener("click",()=>exportModalPdf("Expense Party Balances","exp-party-table"));
}

// ══════════════════════════════════════════════════════════════════════════
// PDF EXPORT
// ══════════════════════════════════════════════════════════════════════════
function exportSectionPdf(section) {
  if (!pdfOn()) return;
  const {jsPDF} = window.jspdf;
  const doc = new jsPDF({orientation:"landscape",unit:"mm",format:"a4"});
  const titles = {
    "low-stock":"Low Stock Items","fast-moving":"Fast Moving Items","stale-stock":"Stale Stock",
    "top-customers":"Top Customers","top-vendors":"Top Vendors","aging":"Receivables Aging",
    "transactions":"Recent Transactions","expenses":"Top Expense Descriptions",
  };
  const tableIds = {
    "low-stock":"low-stock-table","fast-moving":"fast-moving-table","stale-stock":"stale-stock-table",
    "top-customers":"top-customers-table","top-vendors":"top-vendors-table","aging":"aging-table",
    "expenses":"expense-desc-table",
  };
  doc.setFontSize(15); doc.text(titles[section]||section, 14, 16);
  doc.setFontSize(8); doc.setTextColor(100); doc.text("Generated: "+new Date().toLocaleDateString("en-PK"),14,22);
  if(section==="transactions") {
    doc.autoTable({startY:26,head:[["Date","Type","Party","Amount"]],
      body:allTxns.map(t=>[t.txn_date,t.type,t.party_name,fmt(t.amount)]),
      styles:{fontSize:8},headStyles:{fillColor:[59,130,246]}});
  } else if(tableIds[section]) {
    doc.autoTable({html:"#"+tableIds[section],startY:26,styles:{fontSize:8},headStyles:{fillColor:[59,130,246]}});
  }
  doc.save(`${section}_${new Date().toISOString().slice(0,10)}.pdf`);
  if (globalThis.FinanceeActivity) globalThis.FinanceeActivity.exported("pdf");
}

function exportModalPdf(title, tableId) {
  if (!pdfOn()) return;
  const {jsPDF} = window.jspdf;
  const doc = new jsPDF({unit:"mm",format:"a4"});
  doc.setFontSize(15); doc.text(title, 14, 16);
  doc.setFontSize(8); doc.setTextColor(100); doc.text("Generated: "+new Date().toLocaleDateString("en-PK"),14,22);
  doc.autoTable({html:"#"+tableId,startY:26,styles:{fontSize:8},headStyles:{fillColor:[59,130,246]}});
  doc.save(`${title.replace(/\s+/g,"_").toLowerCase()}_${new Date().toISOString().slice(0,10)}.pdf`);
  if (globalThis.FinanceeActivity) globalThis.FinanceeActivity.exported("pdf");
}

// ══════════════════════════════════════════════════════════════════════════
// STOCK RESERVED ON DRAFTS
// The card is only rendered for users who may see it (and only when drafts
// are switched on for the company), so return early — fetching nothing —
// when it is absent.
// ══════════════════════════════════════════════════════════════════════════
async function loadDraftCard() {
  const card = $("draft-reservations-card");
  if (!card) return;

  const data = await apiFetch(API.draftReservations, { limit: 5 });
  if (!data) return;

  setEl("draft-open-count", String(data.open_drafts || 0));
  setEl("draft-reserved-units", String(data.reserved_units || 0));
  setEl("draft-oldest-days", String(data.oldest_days || 0));

  // The ageing chip appears only when something is actually ageing; a
  // permanent "0" trains people to ignore it.
  const aged = Number(data.aged_drafts || 0);
  const agedChip = $("draft-aged-chip");
  if (agedChip) {
    agedChip.hidden = aged === 0;
    setEl("draft-aged-count", String(aged));
  }

  const body = document.querySelector("#draft-reservations-table tbody");
  if (!body) return;
  const rows = data.recent || [];
  body.innerHTML = rows.length
    ? rows.map(r => `<tr>
          <td>${featureOn("draft_invoices", "drafts")
                ? `<a href="/draft/?open=${encodeURIComponent(r.draft_invoice_id)}">#${esc(r.draft_invoice_id)}</a>`
                : `#${esc(r.draft_invoice_id)}`}</td>
          <td>${esc(r.customer)}</td>
          <td>${esc(r.draft_date)}</td>
          <td>${esc(String(r.reserved_units))}</td>
          <td>${esc(String(r.days_outstanding))}</td>
        </tr>`).join("")
    : '<tr><td colspan="5" style="text-align:center;opacity:.6;">Nothing reserved</td></tr>';
}
