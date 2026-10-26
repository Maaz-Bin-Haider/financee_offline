// ============================================================
// Owner Equity — section script
// Record owner withdrawals & capital injections against an
// equity account (no party, no faked cash).
// ============================================================

const OE_API = {
  list:     "/owner-equity/api/transactions/",
  accounts: "/owner-equity/api/equity-accounts/",
  add:      "/owner-equity/api/add/",
  del:      "/owner-equity/api/delete/",
};

function oeCsrf() {
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] || "";
}

let _oeRows = [];
let _oeSummary = { total_injections: 0, total_withdrawals: 0, net_contributed: 0 };

function oeFmt(n) {
  return (parseFloat(n) || 0).toLocaleString("en-PK", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
}

async function oeLoadAccounts() {
  try {
    const r = await fetch(OE_API.accounts, { headers: { "X-Requested-With": "XMLHttpRequest" } });
    if (!r.ok) return;
    const d = await r.json();
    const sel = document.getElementById("oe-account");
    if (!sel) return;
    sel.innerHTML = "";
    (d.accounts || []).forEach((name) => {
      const o = document.createElement("option");
      o.value = name; o.textContent = name;
      if (name === "Owner's Capital") o.selected = true;
      sel.appendChild(o);
    });
  } catch (e) { /* ignore */ }
}

async function oeLoadList() {
  try {
    const r = await fetch(OE_API.list, { headers: { "X-Requested-With": "XMLHttpRequest" } });
    if (!r.ok) return;
    const d = await r.json();

    _oeSummary = {
      total_injections: d.total_injections || 0,
      total_withdrawals: d.total_withdrawals || 0,
      net_contributed: d.net_contributed || 0,
    };
    _oeRows = d.transactions || [];

    document.getElementById("oe-total-inj").textContent = oeFmt(d.total_injections);
    document.getElementById("oe-total-wd").textContent  = oeFmt(d.total_withdrawals);
    document.getElementById("oe-net").textContent       = oeFmt(d.net_contributed);

    const tb = document.getElementById("oe-tbody");
    const rows = d.transactions || [];
    if (!rows.length) {
      tb.innerHTML = `<tr><td colspan="6" class="oe-empty">No entries yet</td></tr>`;
      return;
    }
    tb.innerHTML = rows.map((t) => {
      const isWd = t.direction === "withdrawal";
      const badge = isWd
        ? `<span class="oe-badge oe-out">Withdrawal</span>`
        : `<span class="oe-badge oe-in">Injection</span>`;
      return `<tr>
        <td>${t.txn_date || ""}</td>
        <td>${badge}</td>
        <td>${t.account || ""}</td>
        <td class="oe-amt ${isWd ? "oe-amt-out" : "oe-amt-in"}">${isWd ? "−" : "+"}${oeFmt(t.amount)}</td>
        <td>${t.description ? t.description : "—"}</td>
        <td><button class="oe-del" title="Delete" onclick="oeDelete(${t.txn_id})"><i class="fa-solid fa-trash"></i></button></td>
      </tr>`;
    }).join("");
  } catch (e) { /* ignore */ }
}

async function oeSave() {
  const direction = document.getElementById("oe-direction").value;
  const account   = document.getElementById("oe-account").value;
  const amount    = parseFloat(document.getElementById("oe-amount").value);
  const date      = document.getElementById("oe-date").value;
  const desc      = document.getElementById("oe-desc").value;

  if (isNaN(amount) || amount <= 0) {
    // Swal.fire("Invalid amount", "Enter an amount greater than 0.", "warning");
    Alerts.warning("Enter an amount greater than 0.", { title: "Invalid amount" });
    return;
  }

  const btn = document.getElementById("oe-save-btn");
  btn.disabled = true;
  try {
    const r = await fetch(OE_API.add, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": oeCsrf() },
      body: JSON.stringify({
        direction, equity_account: account, amount,
        txn_date: date, description: desc,
      }),
    });
    const d = await r.json();
    if (!r.ok || d.status !== "success") {
      // Swal.fire("Error", d.message || "Could not save.", "error");
      Alerts.error(d.message || "Could not save.");
    } else {
      document.getElementById("oe-amount").value = "";
      document.getElementById("oe-desc").value = "";
      await oeLoadList();
      // Swal.fire({ icon: "success", title: "Recorded", timer: 1100, showConfirmButton: false });
      Alerts.success("", { title: "Recorded" });
    }
  } catch (e) {
    // Swal.fire("Error", "Request failed. " + e.message, "error");
    Alerts.error("Request failed. " + e.message);
  } finally {
    btn.disabled = false;
  }
}

async function oeDelete(txnId) {
  // const ok = await Swal.fire({
  //   title: "Delete this entry?",
  //   text: "Its journal entry will be removed too.",
  //   icon: "warning", showCancelButton: true, confirmButtonText: "Delete",
  //   confirmButtonColor: "#dc2626",
  // });
  // if (!ok.isConfirmed) return;
  const ok = await Alerts.confirm({
    title: "Delete this entry?",
    text: "Its journal entry will be removed too.",
    confirmText: "Delete", danger: true,
  });
  if (!ok) return;
  try {
    const r = await fetch(OE_API.del, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": oeCsrf() },
      body: JSON.stringify({ txn_id: txnId }),
    });
    const d = await r.json();
    if (!r.ok || d.status !== "success") {
      // Swal.fire("Error", d.message || "Could not delete.", "error");
      Alerts.error(d.message || "Could not delete.");
    } else {
      await oeLoadList();
    }
  } catch (e) {
    // Swal.fire("Error", "Request failed. " + e.message, "error");
    Alerts.error("Request failed. " + e.message);
  }
}

/* ─────────────────────────── Export: PDF / CSV ─────────────────────────── */
function oeExportPDF() {
  // if (!_oeRows.length) { Swal.fire("Nothing to export", "There are no entries yet.", "info"); return; }
  if (!_oeRows.length) { Alerts.notify("There are no entries yet.", { title: "Nothing to export" }); return; }
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF();
  doc.setFontSize(15); doc.text("Owner Equity — Withdrawals & Capital", 14, 18);
  doc.setFontSize(10);
  doc.text("Generated " + new Date().toLocaleDateString("en-PK"), 14, 25);

  doc.autoTable({
    startY: 32,
    head: [["Date", "Type", "Account", "Amount", "Note"]],
    body: _oeRows.map((t) => [
      t.txn_date || "",
      t.direction === "withdrawal" ? "Withdrawal" : "Injection",
      t.account || "",
      (t.direction === "withdrawal" ? "-" : "+") + oeFmt(t.amount),
      t.description || "",
    ]),
    theme: "grid",
    headStyles: { fillColor: [37, 99, 235] },
  });

  doc.autoTable({
    startY: doc.lastAutoTable.finalY + 6,
    body: [
      ["Capital injected", oeFmt(_oeSummary.total_injections)],
      ["Withdrawn", oeFmt(_oeSummary.total_withdrawals)],
      ["Net contributed", oeFmt(_oeSummary.net_contributed)],
    ],
    theme: "plain",
    styles: { fontStyle: "bold" },
  });

  doc.save("owner_equity_" + new Date().toISOString().slice(0, 10) + ".pdf");
  if (globalThis.FinanceeActivity) globalThis.FinanceeActivity.exported("pdf");
}

function oeExportCSV() {
  // if (!_oeRows.length) { Swal.fire("Nothing to export", "There are no entries yet.", "info"); return; }
  if (!_oeRows.length) { Alerts.notify("There are no entries yet.", { title: "Nothing to export" }); return; }
  const esc = (v) => '"' + String(v ?? "").replace(/"/g, '""') + '"';
  const rows = [["Date", "Type", "Account", "Amount", "Note"].map(esc)];
  _oeRows.forEach((t) => {
    const signed = t.direction === "withdrawal" ? -Math.abs(t.amount) : Math.abs(t.amount);
    rows.push([t.txn_date || "", t.direction, t.account || "", signed, t.description || ""].map(esc));
  });
  rows.push([]);
  rows.push(["Capital injected", _oeSummary.total_injections].map(esc));
  rows.push(["Withdrawn", _oeSummary.total_withdrawals].map(esc));
  rows.push(["Net contributed", _oeSummary.net_contributed].map(esc));

  const blob = new Blob([rows.map((r) => r.join(",")).join("\n")], { type: "text/csv;charset=utf-8;" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "owner_equity_" + new Date().toISOString().slice(0, 10) + ".csv";
  document.body.appendChild(a); a.click(); a.remove();
  if (globalThis.FinanceeActivity) globalThis.FinanceeActivity.exported("csv");
  URL.revokeObjectURL(a.href);
}

document.addEventListener("DOMContentLoaded", () => {
  const dt = document.getElementById("oe-date");
  if (dt) dt.value = new Date().toISOString().slice(0, 10);
  document.getElementById("oe-save-btn")?.addEventListener("click", oeSave);
  document.getElementById("oe-download-pdf")?.addEventListener("click", oeExportPDF);
  document.getElementById("oe-download-csv")?.addEventListener("click", oeExportCSV);
  oeLoadAccounts();
  oeLoadList();
});
