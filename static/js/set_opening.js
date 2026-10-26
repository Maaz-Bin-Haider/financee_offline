// ============================================================
// Set Opening — section script
// Loads and saves the company's opening values. For now: Opening Cash.
// ============================================================

const SET_OPENING_API = {
  openingCash:    "/set-opening/api/opening-cash/",
  openingCashSet: "/set-opening/api/opening-cash/set/",
};

function getCsrf() {
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] || "";
}

function fmtMoney(n) {
  return (parseFloat(n) || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

// Left-panel selector (only one option for now; ready for more later)
function selectOpening(which) {
  document.querySelectorAll(".report-btn").forEach((b) => b.classList.remove("active"));
  if (which === "cash") {
    document.getElementById("btn-opening-cash")?.classList.add("active");
    document.getElementById("opening-cash-section").style.display = "block";
  }
}

async function loadOpeningCash() {
  try {
    const r = await fetch(SET_OPENING_API.openingCash, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    if (!r.ok) return;
    const d = await r.json();
    const amount = parseFloat(d.amount) || 0;
    const cur = document.getElementById("opening-cash-current");
    const inp = document.getElementById("opening-cash-input");
    if (cur) cur.textContent = fmtMoney(amount);
    if (inp) inp.value = amount.toFixed(2);
  } catch (e) {
    /* leave blank on error */
  }
}

async function saveOpeningCash() {
  const inp = document.getElementById("opening-cash-input");
  const status = document.getElementById("opening-cash-status");
  const amount = parseFloat(inp ? inp.value : "");

  if (isNaN(amount) || amount < 0) {
    if (status) { status.textContent = "Enter a valid amount (\u2265 0)"; status.className = "opening-status err"; }
    return;
  }
  if (status) { status.textContent = "Saving\u2026"; status.className = "opening-status"; }

  try {
    const r = await fetch(SET_OPENING_API.openingCashSet, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrf(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ amount }),
    });
    const d = await r.json().catch(() => ({}));
    if (r.ok && d.status === "success") {
      const newAmount = parseFloat(d.opening_cash?.amount) || 0;
      const cur = document.getElementById("opening-cash-current");
      if (cur) cur.textContent = fmtMoney(newAmount);
      if (status) { status.textContent = "Saved \u2713"; status.className = "opening-status ok"; }
      if (window.Alerts) {
        // Swal.fire({ icon: "success", title: "Opening cash saved",
        //             text: "Saved as " + fmtMoney(newAmount), timer: 1600, showConfirmButton: false });
        Alerts.success("Saved as " + fmtMoney(newAmount), { title: "Opening cash saved" });
      }
    } else {
      const msg = d.message || "Could not save opening cash.";
      if (status) { status.textContent = msg; status.className = "opening-status err"; }
      // if (window.Swal) Swal.fire({ icon: "error", title: "Error", text: msg });
      if (window.Alerts) Alerts.error(msg);
    }
  } catch (e) {
    if (status) { status.textContent = "Network error"; status.className = "opening-status err"; }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("opening-cash-save-btn")?.addEventListener("click", saveOpeningCash);
  loadOpeningCash();
});
