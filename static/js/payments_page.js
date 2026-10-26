// /* ============================================================
//    PAYMENTS PAGE — JavaScript
//    Handles: autocomplete, navigation, history modals,
//             form mode UI, keyboard shortcuts, delete confirm
//    ============================================================ */

// /* ===== HELPERS ===== */

// function setFormMode(mode) {
//   const statusMode = document.getElementById("statusMode");
//   const statusText = document.getElementById("statusText");
//   const submitBtn  = document.getElementById("submitBtn");
//   const deleteBtn  = document.getElementById("deleteBtn");
//   const badgeEl    = document.getElementById("entryByBadge");

//   if (!statusMode) return;

//   if (mode === "edit") {
//     statusMode.className = "status-mode mode-edit";
//     if (statusText) statusText.textContent = "Editing Record";
//     if (submitBtn) {
//       submitBtn.innerHTML = '<i class="fa-solid fa-pen-to-square"></i> Update Payment';
//     }
//     if (deleteBtn) deleteBtn.style.display = "inline-flex";
//     if (badgeEl)   badgeEl.style.display = "inline-flex";
//   } else {
//     statusMode.className = "status-mode mode-new";
//     if (statusText) statusText.textContent = "New Entry";
//     if (submitBtn) {
//       submitBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Payment';
//     }
//     if (deleteBtn) deleteBtn.style.display = "inline-flex";
//     if (badgeEl)   badgeEl.style.display = "none";
//   }
// }

// function updateRecordChip(id) {
//   const chip = document.getElementById("recordIdChip");
//   if (!chip) return;
//   chip.textContent = id ? "#" + id : "New";
// }

// function populateForm(data) {
//   document.getElementById("payment_date").value  = data.payment_date || "";
//   document.getElementById("search_name").value   = data.party_name   || "";
//   document.getElementById("amount").value        = data.amount       || "";
//   document.getElementById("method").value        = data.method       || "Cash";
//   document.getElementById("description").value   = data.description  || "";

//   const entryByName = document.getElementById("entryByName");
//   if (entryByName) entryByName.textContent = data.created_by || "—";

//   const hiddenId = document.getElementById("current_payment_id");
//   if (hiddenId) hiddenId.value = data.payment_id || "";

//   updateRecordChip(data.payment_id);
//   setFormMode(data.payment_id ? "edit" : "new");
// }


// /* ===== DOCUMENT READY ===== */
// $(document).ready(function () {

//   // Set today's date on page load (if field is empty)
//   const dateInput = document.getElementById("payment_date");
//   if (dateInput && !dateInput.value) {
//     dateInput.valueAsDate = new Date();
//   }

//   // Set initial form mode based on whether we have an ID
//   const existingId = document.getElementById("current_payment_id")?.value;
//   setFormMode(existingId ? "edit" : "new");

//   const autocompleteUrl = $("#search_name").data("autocomplete-url");
//   let selectedIndex = -1;

//   /* --- Autocomplete --- */
//   $("#search_name").on("input", function () {
//     const query        = $(this).val();
//     const suggestionsBox = $("#suggestions");
//     selectedIndex = -1;

//     if (query.length >= 1) {
//       $.ajax({
//         url:      autocompleteUrl,
//         data:     { term: query },
//         dataType: "json",
//         success: function (data) {
//           suggestionsBox.empty();
//           if (data.length > 0) {
//             data.forEach(function (party) {
//               $("<div>")
//                 .addClass("suggestion-item")
//                 .text(party)
//                 .appendTo(suggestionsBox)
//                 .on("click", function () {
//                   $("#search_name").val(party);
//                   suggestionsBox.hide();
//                 });
//             });
//             suggestionsBox.show();
//           } else {
//             suggestionsBox.hide();
//           }
//         },
//         error: function (xhr, status, error) {
//           console.error("Autocomplete AJAX error:", status, error);
//         }
//       });
//     } else {
//       suggestionsBox.hide();
//     }
//   });

//   /* --- Autocomplete keyboard navigation --- */
//   $("#search_name").on("keydown", function (e) {
//     const items = $("#suggestions .suggestion-item");
//     if (items.length === 0) return;

//     if (e.key === "Enter" && items.length === 1) {
//       e.preventDefault();
//       items.eq(0).trigger("click");
//       return;
//     }
//     if (e.key === "ArrowDown") {
//       e.preventDefault();
//       selectedIndex = (selectedIndex + 1) % items.length;
//       items.removeClass("highlight");
//       items.eq(selectedIndex).addClass("highlight")[0].scrollIntoView({ block: "nearest" });
//     } else if (e.key === "ArrowUp") {
//       e.preventDefault();
//       selectedIndex = (selectedIndex - 1 + items.length) % items.length;
//       items.removeClass("highlight");
//       items.eq(selectedIndex).addClass("highlight")[0].scrollIntoView({ block: "nearest" });
//     } else if (e.key === "Enter" && selectedIndex >= 0) {
//       e.preventDefault();
//       items.eq(selectedIndex).trigger("click");
//     }
//   });

//   /* --- Hide suggestions on outside click --- */
//   $(document).on("click", function (e) {
//     if (!$(e.target).closest("#search_name, #suggestions").length) {
//       $("#suggestions").hide();
//     }
//   });

// });


// /* ===== NAVIGATE PAYMENT (Previous / Next) ===== */
// function navigatePayment(action) {
//   const currentId = document.getElementById("current_payment_id").value || "";

//   fetch(`/payments/payment/get/?action=${action}&current_id=${encodeURIComponent(currentId)}`)
//     .then(res => res.json())
//     .then(data => {
//       if (data.error) {
//         Swal.fire({
//           title:               "End of Records",
//           text:                action === "previous"
//                                  ? "You are at the first payment."
//                                  : "You are at the latest payment.",
//           icon:                "info",
//           confirmButtonColor:  "#2563eb",
//           confirmButtonText:   "OK",
//           toast:               true,
//           position:            "top-end",
//           timer:               2000,
//           showConfirmButton:   false
//         });
//         return;
//       }
//       populateForm(data);
//     })
//     .catch(err => console.error("Navigation error:", err));
// }


// /* ===== DELETE CONFIRM ===== */
// document.addEventListener("DOMContentLoaded", function () {
//   const form = document.getElementById("paymentForm");
//   let confirmedDelete = false;

//   form.addEventListener("submit", function (e) {
//     const btn = e.submitter;
//     if (btn && btn.value === "delete" && !confirmedDelete) {
//       e.preventDefault();
//       Swal.fire({
//         title:              "Delete this payment?",
//         text:               "This action cannot be undone.",
//         icon:               "warning",
//         showCancelButton:   true,
//         confirmButtonColor: "#dc2626",
//         cancelButtonColor:  "#6b7280",
//         confirmButtonText:  "Yes, delete",
//         cancelButtonText:   "Cancel"
//       }).then(result => {
//         if (result.isConfirmed) {
//           confirmedDelete = true;
//           form.requestSubmit(btn);
//         }
//       });
//     }
//   });
// });


// /* ===== FETCH PAYMENTS (History / Date-Wise) ===== */
// function fetchPayments(url) {
//   $.ajax({
//     url:      url,
//     type:     "GET",
//     dataType: "json",
//     beforeSend: function () {
//       Swal.fire({
//         title:             "Loading…",
//         allowOutsideClick: false,
//         didOpen: () => Swal.showLoading()
//       });
//     },
//     success: function (response) {
//       if (!response || response.length === 0) {
//         Swal.fire({
//           title: "No Payments Found",
//           text:  "No payments match this query.",
//           icon:  "info",
//           confirmButtonColor: "#2563eb"
//         });
//         return;
//       }

//       let html = `
//         <div style="margin-bottom:10px;">
//           <input type="text" id="paymentSearch"
//                  placeholder="🔍 Search by party or ref #"
//                  style="width:100%;padding:8px 12px;border:1.5px solid #e2e8f0;
//                         border-radius:8px;font-size:0.875rem;outline:none;
//                         font-family:inherit;">
//         </div>
//         <div id="paymentsList" style="max-height:360px;overflow-y:auto;text-align:left;">
//       `;

//       let currentDate = null;

//       response.forEach((payment, index) => {
//         if (payment.payment_date !== currentDate) {
//           if (currentDate !== null) html += `</div>`;
//           currentDate = payment.payment_date;
//           html += `
//             <div class="payment-date-group">
//               <div class="payment-date-header">${currentDate}</div>
//           `;
//         }

//         html += `
//           <div class="payment-row"
//                data-party="${(payment.party_name || "").toLowerCase()}"
//                data-ref="${(payment.reference_no || "").toLowerCase()}"
//                data-id="${payment.payment_id}">
//             <div class="payment-top">
//               <span class="payment-ref">${payment.reference_no || ""}</span>
//               <span class="payment-party">${payment.party_name || ""}</span>
//               <span class="payment-amount">${Number(payment.amount).toLocaleString()}</span>
//             </div>
//             <div class="payment-tooltip">
//               ${payment.description || "No description"}
//             </div>
//           </div>
//         `;

//         if (index === response.length - 1) html += `</div>`;
//       });

//       html += `</div>`;

//       Swal.fire({
//         title:             "📑 Payment History",
//         html:              html,
//         width:             "660px",
//         showConfirmButton: true,
//         confirmButtonText: "Close",
//         confirmButtonColor: "#6b7280",
//         didOpen: () => {

//           // Search filter
//           document.getElementById("paymentSearch").addEventListener("input", function () {
//             const q = this.value.toLowerCase();
//             document.querySelectorAll(".payment-row").forEach(row => {
//               const visible = row.dataset.party.includes(q) || row.dataset.ref.includes(q);
//               row.style.display = visible ? "flex" : "none";
//             });
//             document.querySelectorAll(".payment-date-group").forEach(group => {
//               const hasVisible = [...group.querySelectorAll(".payment-row")]
//                 .some(r => r.style.display !== "none");
//               group.style.display = hasVisible ? "block" : "none";
//             });
//           });

//           // Click to load record
//           document.querySelectorAll(".payment-row").forEach(row => {
//             row.addEventListener("click", function () {
//               const id = this.dataset.id;
//               fetch(`/payments/payment/get/?current_id=${id}`)
//                 .then(res => res.json())
//                 .then(data => {
//                   if (data.error) return;
//                   Swal.close();
//                   populateForm(data);
//                 })
//                 .catch(err => console.error(err));
//             });
//           });
//         }
//       });
//     },
//     error: function () {
//       Swal.fire({
//         title: "Error",
//         text:  "Could not load payments. Please try again.",
//         icon:  "error",
//         confirmButtonColor: "#dc2626"
//       });
//     }
//   });
// }

// /* History button */
// $("#btnOldPayments").on("click", function () {
//   fetchPayments("/payments/get-old-payments/");
// });

// /* Date-wise button */
// $("#btnVendorPayments").on("click", function () {
//   const today = new Date().toISOString().split("T")[0];
//   Swal.fire({
//     title:             "Filter by Date Range",
//     html: `
//       <div style="text-align:left;padding:0 8px;">
//         <div style="margin-bottom:14px;">
//           <label style="display:block;font-size:0.82rem;font-weight:500;color:#64748b;margin-bottom:5px;">From Date</label>
//           <input type="date" id="fromDate" class="swal2-input" style="width:100%;margin:0;" max="${today}">
//         </div>
//         <div>
//           <label style="display:block;font-size:0.82rem;font-weight:500;color:#64748b;margin-bottom:5px;">To Date</label>
//           <input type="date" id="toDate" class="swal2-input" style="width:100%;margin:0;" value="${today}" max="${today}">
//         </div>
//       </div>
//     `,
//     focusConfirm:        false,
//     showCancelButton:    true,
//     confirmButtonText:   "Fetch Payments",
//     confirmButtonColor:  "#2563eb",
//     cancelButtonColor:   "#6b7280",
//     preConfirm: () => {
//       const from = document.getElementById("fromDate").value;
//       const to   = document.getElementById("toDate").value;
//       if (!from || !to) {
//         Swal.showValidationMessage("⚠ Both dates are required");
//         return false;
//       }
//       if (from > to) {
//         Swal.showValidationMessage("⚠ From date cannot be after To date");
//         return false;
//       }
//       return { from, to };
//     }
//   }).then(result => {
//     if (result.isConfirmed) {
//       const { from, to } = result.value;
//       fetchPayments(`/payments/get-payments-date-wise/?from=${from}&to=${to}`);
//     }
//   });
// });


// /* ===== KEYBOARD FIELD NAVIGATION ===== */
// document.addEventListener("DOMContentLoaded", function () {
//   const form = document.getElementById("paymentForm");
//   if (!form) return;

//   const focusableElements = form.querySelectorAll(
//     "input:not([type=hidden]):not([readonly]), textarea, select, button"
//   );

//   form.addEventListener("keydown", function (e) {
//     const key           = e.key;
//     const activeElement = document.activeElement;

//     // Don't interfere with autocomplete
//     if ($("#suggestions:visible").length > 0 &&
//         ["ArrowDown", "ArrowUp", "Enter"].includes(key)) return;

//     const index = Array.from(focusableElements).indexOf(activeElement);
//     if (index === -1) return;

//     if (key === "Enter" || key === "ArrowDown") {
//       // Allow Enter in textarea
//       if (activeElement.tagName === "TEXTAREA" && key === "Enter") return;
//       e.preventDefault();
//       const next = focusableElements[index + 1];
//       if (next) next.focus();
//     } else if (key === "ArrowUp") {
//       e.preventDefault();
//       const prev = focusableElements[index - 1];
//       if (prev) prev.focus();
//     }
//   });
// });


/* ============================================================
   PAYMENTS PAGE — JavaScript
   Handles: autocomplete, navigation, history modals,
            form mode UI, keyboard shortcuts, delete confirm
   ============================================================ */

/* ===== HELPERS ===== */

function setFormMode(mode) {
  const statusMode = document.getElementById("statusMode");
  const statusText = document.getElementById("statusText");
  const submitBtn  = document.getElementById("submitBtn");
  const deleteBtn  = document.getElementById("deleteBtn");
  const badgeEl    = document.getElementById("entryByBadge");

  if (!statusMode) return;

  if (mode === "edit") {
    statusMode.className = "status-mode mode-edit";
    if (statusText) statusText.textContent = "Editing Record";
    if (submitBtn) {
      submitBtn.innerHTML = '<i class="fa-solid fa-pen-to-square"></i> Update Payment';
    }
    if (deleteBtn) deleteBtn.style.display = "inline-flex";
    if (badgeEl)   badgeEl.style.display = "inline-flex";
  } else {
    statusMode.className = "status-mode mode-new";
    if (statusText) statusText.textContent = "New Entry";
    if (submitBtn) {
      submitBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Payment';
    }
    if (deleteBtn) deleteBtn.style.display = "inline-flex";
    if (badgeEl)   badgeEl.style.display = "none";
  }
}

function updateRecordChip(id) {
  const chip = document.getElementById("recordIdChip");
  if (!chip) return;
  chip.textContent = id ? "#" + id : "New";
}

function populateForm(data) {
  document.getElementById("payment_date").value  = data.payment_date || "";
  document.getElementById("search_name").value   = data.party_name   || "";
  fetchPartyBalance(data.party_name || "");
  document.getElementById("amount").value        = data.amount       || "";
  document.getElementById("method").value        = data.method       || "Cash";
  document.getElementById("description").value   = data.description  || "";
  if (window.SmartDescriptions) SmartDescriptions.refreshAll();

  const entryByName = document.getElementById("entryByName");
  if (entryByName) entryByName.textContent = data.created_by || "—";

  const hiddenId = document.getElementById("current_payment_id");
  if (hiddenId) hiddenId.value = data.payment_id || "";

  updateRecordChip(data.payment_id);
  setFormMode(data.payment_id ? "edit" : "new");
  if (window.DocumentAttachments) DocumentAttachments.load(data.payment_id || "");
}


/* ===== DOCUMENT READY ===== */
$(document).ready(function () {

  // Set today's date on page load (if field is empty)
  const dateInput = document.getElementById("payment_date");
  if (dateInput && !dateInput.value) {
    dateInput.valueAsDate = new Date();
  }

  // Set initial form mode based on whether we have an ID
  const existingId = document.getElementById("current_payment_id")?.value;
  setFormMode(existingId ? "edit" : "new");
  if (window.DocumentAttachments) {
    DocumentAttachments.bindForm("paymentForm", "payment", () => document.getElementById("current_payment_id")?.value || "");
  }

  const autocompleteUrl = $("#search_name").data("autocomplete-url");
  let selectedIndex = -1;

  /* --- Autocomplete --- */
  $("#search_name").on("input", function () {
    const query        = $(this).val();
    const suggestionsBox = $("#suggestions");
    selectedIndex = -1;

    if (query.length >= 1) {
      $.ajax({
        url:      autocompleteUrl,
        data:     { term: query },
        dataType: "json",
        success: function (data) {
          suggestionsBox.empty();
          if (data.length > 0) {
            data.forEach(function (party) {
              $("<div>")
                .addClass("suggestion-item")
                .text(party)
                .appendTo(suggestionsBox)
                .on("click", function () {
                  $("#search_name").val(party);
                  suggestionsBox.hide();
                  fetchPartyBalance(party);
                });
            });
            suggestionsBox.show();
          } else {
            suggestionsBox.hide();
          }
        },
        error: function (xhr, status, error) {
          console.error("Autocomplete AJAX error:", status, error);
        }
      });
    } else {
      suggestionsBox.hide();
    }
  });

  /* --- Autocomplete keyboard navigation --- */
  $("#search_name").on("keydown", function (e) {
    const items = $("#suggestions .suggestion-item");
    if (items.length === 0) return;

    if (e.key === "Enter" && items.length === 1) {
      e.preventDefault();
      items.eq(0).trigger("click");
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      selectedIndex = (selectedIndex + 1) % items.length;
      items.removeClass("highlight");
      items.eq(selectedIndex).addClass("highlight")[0].scrollIntoView({ block: "nearest" });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      selectedIndex = (selectedIndex - 1 + items.length) % items.length;
      items.removeClass("highlight");
      items.eq(selectedIndex).addClass("highlight")[0].scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter" && selectedIndex >= 0) {
      e.preventDefault();
      items.eq(selectedIndex).trigger("click");
    }
  });

  /* --- Hide suggestions on outside click --- */
  $(document).on("click", function (e) {
    if (!$(e.target).closest("#search_name, #suggestions").length) {
      $("#suggestions").hide();
    }
  });

});


/* ===== PARTY BALANCE FETCH ===== */
function fetchPartyBalance(partyName) {
  if (!partyName) {
    $("#partyBalanceDisplay").hide();
    return;
  }
  $.ajax({
    url:      "/payments/party-balance/",
    data:     { name: partyName },
    dataType: "json",
    success: function (data) {
      var el = $("#partyBalanceDisplay");
      if (!data.found) {
        el.hide();
        return;
      }
      var balance  = parseFloat(data.balance) || 0;
      var absVal   = Math.abs(balance).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      var label, cssClass;
      if (balance > 0) {
        label    = "Balance Receivable: " + absVal;
        cssClass = "party-balance-receivable";
      } else if (balance < 0) {
        label    = "Balance Payable: " + absVal;
        cssClass = "party-balance-payable";
      } else {
        label    = "Balance: 0.00 (Settled)";
        cssClass = "party-balance-settled";
      }
      el.removeClass("party-balance-receivable party-balance-payable party-balance-settled")
        .addClass(cssClass)
        .text(label)
        .show();
    },
    error: function () {
      $("#partyBalanceDisplay").hide();
    }
  });
}


/* ===== NAVIGATE PAYMENT (Previous / Next) ===== */
function navigatePayment(action) {
  const currentId = document.getElementById("current_payment_id").value || "";

  fetch(`/payments/payment/get/?action=${action}&current_id=${encodeURIComponent(currentId)}`)
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        // Swal.fire({
        //   title:               "End of Records",
        //   text:                action === "previous"
        //                          ? "You are at the first payment."
        //                          : "You are at the latest payment.",
        //   icon:                "info",
        //   confirmButtonColor:  "#2563eb",
        //   confirmButtonText:   "OK",
        //   toast:               true,
        //   position:            "top-end",
        //   timer:               2000,
        //   showConfirmButton:   false
        // });
        Alerts.notify(action === "previous" ? "You are at the first payment." : "You are at the latest payment.", { title: "End of Records" });
        return;
      }
      populateForm(data);
    })
    .catch(err => console.error("Navigation error:", err));
}


/* ===== DELETE CONFIRM ===== */
document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("paymentForm");
  let confirmedDelete = false;

  form.addEventListener("submit", function (e) {
    const btn = e.submitter;
    if (btn && btn.value === "delete" && !confirmedDelete) {
      e.preventDefault();
      // Swal.fire({
      //   title:              "Delete this payment?",
      //   text:               "This action cannot be undone.",
      //   icon:               "warning",
      //   showCancelButton:   true,
      //   confirmButtonColor: "#dc2626",
      //   cancelButtonColor:  "#6b7280",
      //   confirmButtonText:  "Yes, delete",
      //   cancelButtonText:   "Cancel"
      // }).then(result => {
      //   if (result.isConfirmed) {
      //     confirmedDelete = true;
      //     form.requestSubmit(btn);
      //   }
      // });
      Alerts.confirm({
        title: "Delete this payment?",
        text: "This action cannot be undone.",
        confirmText: "Yes, delete", danger: true
      }).then(confirmed => {
        if (confirmed) {
          confirmedDelete = true;
          form.requestSubmit(btn);
        }
      });
    }
  });
});


/* ===== FETCH PAYMENTS (History / Date-Wise) ===== */
function fetchPayments(url) {
  $.ajax({
    url:      url,
    type:     "GET",
    dataType: "json",
    beforeSend: function () {
      // Swal.fire({
      //   title:             "Loading…",
      //   allowOutsideClick: false,
      //   didOpen: () => Swal.showLoading()
      // });
      Alerts.loading("Loading…");
    },
    success: function (response) {
      if (!response || response.length === 0) {
        // Swal.fire({
        //   title: "No Payments Found",
        //   text:  "No payments match this query.",
        //   icon:  "info",
        //   confirmButtonColor: "#2563eb"
        // });
        Alerts.notify("No payments match this query.", { title: "No Payments Found" });
        return;
      }

      let html = `
        <div style="margin-bottom:10px;">
          <input type="text" id="paymentSearch"
                 placeholder="🔍 Search by party or ref #"
                 style="width:100%;padding:8px 12px;border:1.5px solid #e2e8f0;
                        border-radius:8px;font-size:0.875rem;outline:none;
                        font-family:inherit;">
        </div>
        <div id="paymentsList" style="max-height:360px;overflow-y:auto;text-align:left;">
      `;

      let currentDate = null;

      response.forEach((payment, index) => {
        if (payment.payment_date !== currentDate) {
          if (currentDate !== null) html += `</div>`;
          currentDate = payment.payment_date;
          html += `
            <div class="payment-date-group">
              <div class="payment-date-header">${currentDate}</div>
          `;
        }

        html += `
          <div class="payment-row"
               data-party="${(payment.party_name || "").toLowerCase()}"
               data-ref="${(payment.reference_no || "").toLowerCase()}"
               data-id="${payment.payment_id}">
            <div class="payment-top">
              <span class="payment-ref">${payment.reference_no || ""}</span>
              <span class="payment-party">${payment.party_name || ""}</span>
              <span class="payment-amount">${Number(payment.amount).toLocaleString()}</span>
            </div>
            <div class="payment-tooltip">
              ${payment.description || "No description"}
            </div>
          </div>
        `;

        if (index === response.length - 1) html += `</div>`;
      });

      html += `</div>`;

      Alerts.dialog({  /* was Swal.fire — centered detail view, standardized animation */
        title:             "📑 Payment History",
        html:              html,
        width:             "660px",
        showConfirmButton: true,
        confirmButtonText: "Close",
        confirmButtonColor: "#6b7280",
        didOpen: () => {

          // Search filter
          document.getElementById("paymentSearch").addEventListener("input", function () {
            const q = this.value.toLowerCase();
            document.querySelectorAll(".payment-row").forEach(row => {
              const visible = row.dataset.party.includes(q) || row.dataset.ref.includes(q);
              row.style.display = visible ? "flex" : "none";
            });
            document.querySelectorAll(".payment-date-group").forEach(group => {
              const hasVisible = [...group.querySelectorAll(".payment-row")]
                .some(r => r.style.display !== "none");
              group.style.display = hasVisible ? "block" : "none";
            });
          });

          // Click to load record
          document.querySelectorAll(".payment-row").forEach(row => {
            row.addEventListener("click", function () {
              const id = this.dataset.id;
              fetch(`/payments/payment/get/?current_id=${id}`)
                .then(res => res.json())
                .then(data => {
                  if (data.error) return;
                  Swal.close();
                  populateForm(data);
                })
                .catch(err => console.error(err));
            });
          });
        }
      });
    },
    error: function () {
      // Swal.fire({
      //   title: "Error",
      //   text:  "Could not load payments. Please try again.",
      //   icon:  "error",
      //   confirmButtonColor: "#dc2626"
      // });
      Alerts.error("Could not load payments. Please try again.");
    }
  });
}

/* History button */
$("#btnOldPayments").on("click", function () {
  fetchPayments("/payments/get-old-payments/");
});

/* Date-wise button */
$("#btnVendorPayments").on("click", function () {
  const today = new Date().toISOString().split("T")[0];
  Alerts.dialog({  /* was Swal.fire — centered input dialog, standardized animation */
    title:             "Filter by Date Range",
    html: `
      <div style="text-align:left;padding:0 8px;">
        <div style="margin-bottom:14px;">
          <label style="display:block;font-size:0.82rem;font-weight:500;color:var(--text-primary);margin-bottom:5px;">From Date</label>
          <input type="date" id="fromDate" class="swal2-input" style="width:100%;margin:0;" max="${today}">
        </div>
        <div>
          <label style="display:block;font-size:0.82rem;font-weight:500;color:var(--text-primary);margin-bottom:5px;">To Date</label>
          <input type="date" id="toDate" class="swal2-input" style="width:100%;margin:0;" value="${today}" max="${today}">
        </div>
      </div>
    `,
    focusConfirm:        false,
    showCancelButton:    true,
    confirmButtonText:   "Fetch Payments",
    confirmButtonColor:  "#2563eb",
    cancelButtonColor:   "#6b7280",
    preConfirm: () => {
      const from = document.getElementById("fromDate").value;
      const to   = document.getElementById("toDate").value;
      if (!from || !to) {
        Swal.showValidationMessage("⚠ Both dates are required");
        return false;
      }
      if (from > to) {
        Swal.showValidationMessage("⚠ From date cannot be after To date");
        return false;
      }
      return { from, to };
    }
  }).then(result => {
    if (result.isConfirmed) {
      const { from, to } = result.value;
      fetchPayments(`/payments/get-payments-date-wise/?from=${from}&to=${to}`);
    }
  });
});


/* ===== KEYBOARD FIELD NAVIGATION ===== */
document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("paymentForm");
  if (!form) return;

  const focusableElements = form.querySelectorAll(
    "input:not([type=hidden]):not([readonly]), textarea, select, button"
  );

  form.addEventListener("keydown", function (e) {
    const key           = e.key;
    const activeElement = document.activeElement;

    // Don't interfere with autocomplete
    if ($("#suggestions:visible").length > 0 &&
        ["ArrowDown", "ArrowUp", "Enter"].includes(key)) return;

    const index = Array.from(focusableElements).indexOf(activeElement);
    if (index === -1) return;

    if (key === "Enter" || key === "ArrowDown") {
      // Allow Enter in textarea
      if (activeElement.tagName === "TEXTAREA" && key === "Enter") return;
      e.preventDefault();
      const next = focusableElements[index + 1];
      if (next) next.focus();
    } else if (key === "ArrowUp") {
      e.preventDefault();
      const prev = focusableElements[index - 1];
      if (prev) prev.focus();
    }
  });
});
