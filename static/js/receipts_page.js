// /* ============================================================
//    RECEIPTS PAGE — JavaScript
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
//       submitBtn.innerHTML = '<i class="fa-solid fa-pen-to-square"></i> Update Receipt';
//     }
//     if (deleteBtn) deleteBtn.style.display = "inline-flex";
//     if (badgeEl)   badgeEl.style.display = "inline-flex";
//   } else {
//     statusMode.className = "status-mode mode-new";
//     if (statusText) statusText.textContent = "New Entry";
//     if (submitBtn) {
//       submitBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Receipt';
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
//   document.getElementById("receipt_date").value  = data.receipt_date || "";
//   document.getElementById("search_name").value   = data.party_name   || "";
//   document.getElementById("amount").value        = data.amount       || "";
//   document.getElementById("method").value        = data.method       || "Cash";
//   document.getElementById("description").value   = data.description  || "";

//   const entryByName = document.getElementById("entryByName");
//   if (entryByName) entryByName.textContent = data.created_by || "—";

//   const hiddenId = document.getElementById("current_receipt_id");
//   if (hiddenId) hiddenId.value = data.receipt_id || "";

//   updateRecordChip(data.receipt_id);
//   setFormMode(data.receipt_id ? "edit" : "new");
// }


// /* ===== DOCUMENT READY ===== */
// $(document).ready(function () {

//   // Set today's date on page load (if field is empty)
//   const dateInput = document.getElementById("receipt_date");
//   if (dateInput && !dateInput.value) {
//     dateInput.valueAsDate = new Date();
//   }

//   // Set initial form mode based on whether we have an ID
//   const existingId = document.getElementById("current_receipt_id")?.value;
//   setFormMode(existingId ? "edit" : "new");

//   const autocompleteUrl = $("#search_name").data("autocomplete-url");
//   let selectedIndex = -1;

//   /* --- Autocomplete --- */
//   $("#search_name").on("input", function () {
//     const query          = $(this).val();
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


// /* ===== NAVIGATE RECEIPT (Previous / Next) ===== */
// function navigateReceipt(action) {
//   const currentId = document.getElementById("current_receipt_id").value || "";

//   fetch(`/receipts/receipt/get/?action=${action}&current_id=${encodeURIComponent(currentId)}`)
//     .then(res => res.json())
//     .then(data => {
//       if (data.error) {
//         Swal.fire({
//           title:              "End of Records",
//           text:               action === "previous"
//                                 ? "You are at the first receipt."
//                                 : "You are at the latest receipt.",
//           icon:               "info",
//           confirmButtonColor: "#2563eb",
//           toast:              true,
//           position:           "top-end",
//           timer:              2000,
//           showConfirmButton:  false
//         });
//         return;
//       }
//       populateForm(data);
//     })
//     .catch(err => console.error("Navigation error:", err));
// }


// /* ===== DELETE CONFIRM ===== */
// document.addEventListener("DOMContentLoaded", function () {
//   const form = document.getElementById("receiptForm");
//   let confirmedDelete = false;

//   form.addEventListener("submit", function (e) {
//     const btn = e.submitter;
//     if (btn && btn.value === "delete" && !confirmedDelete) {
//       e.preventDefault();
//       Swal.fire({
//         title:              "Delete this receipt?",
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


// /* ===== FETCH RECEIPTS (History / Date-Wise) ===== */
// function fetchReceipts(url) {
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
//           title: "No Receipts Found",
//           text:  "No receipts match this query.",
//           icon:  "info",
//           confirmButtonColor: "#059669"
//         });
//         return;
//       }

//       let html = `
//         <div style="margin-bottom:10px;">
//           <input type="text" id="receiptSearch"
//                  placeholder="🔍 Search by party or ref #"
//                  style="width:100%;padding:8px 12px;border:1.5px solid #e2e8f0;
//                         border-radius:8px;font-size:0.875rem;outline:none;
//                         font-family:inherit;">
//         </div>
//         <div id="receiptsList" style="max-height:360px;overflow-y:auto;text-align:left;">
//       `;

//       let currentDate = null;

//       response.forEach((receipt, index) => {
//         if (receipt.receipt_date !== currentDate) {
//           if (currentDate !== null) html += `</div>`;
//           currentDate = receipt.receipt_date;
//           html += `
//             <div class="receipt-date-group">
//               <div class="receipt-date-header">${currentDate}</div>
//           `;
//         }

//         html += `
//           <div class="receipt-row"
//                data-party="${(receipt.party_name || "").toLowerCase()}"
//                data-ref="${(receipt.reference_no || "").toLowerCase()}"
//                data-id="${receipt.receipt_id}">
//             <div class="receipt-top">
//               <span class="receipt-ref">${receipt.reference_no || ""}</span>
//               <span class="receipt-party">${receipt.party_name || ""}</span>
//               <span class="receipt-amount">${Number(receipt.amount).toLocaleString()}</span>
//             </div>
//             <div class="receipt-tooltip">
//               ${receipt.description || "No description"}
//             </div>
//           </div>
//         `;

//         if (index === response.length - 1) html += `</div>`;
//       });

//       html += `</div>`;

//       Swal.fire({
//         title:             "📑 Receipt History",
//         html:              html,
//         width:             "660px",
//         showConfirmButton: true,
//         confirmButtonText: "Close",
//         confirmButtonColor: "#6b7280",
//         didOpen: () => {

//           // Search filter
//           document.getElementById("receiptSearch").addEventListener("input", function () {
//             const q = this.value.toLowerCase();
//             document.querySelectorAll(".receipt-row").forEach(row => {
//               const visible = row.dataset.party.includes(q) || row.dataset.ref.includes(q);
//               row.style.display = visible ? "flex" : "none";
//             });
//             document.querySelectorAll(".receipt-date-group").forEach(group => {
//               const hasVisible = [...group.querySelectorAll(".receipt-row")]
//                 .some(r => r.style.display !== "none");
//               group.style.display = hasVisible ? "block" : "none";
//             });
//           });

//           // Click to load record
//           document.querySelectorAll(".receipt-row").forEach(row => {
//             row.addEventListener("click", function () {
//               const id = this.dataset.id;
//               fetch(`/receipts/receipt/get/?current_id=${id}`)
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
//         text:  "Could not load receipts. Please try again.",
//         icon:  "error",
//         confirmButtonColor: "#dc2626"
//       });
//     }
//   });
// }

// /* History button */
// $("#btnOldReceipts").on("click", function () {
//   fetchReceipts("/receipts/get-old-receipts/");
// });

// /* Date-wise button */
// $("#btnCustomerReceipts").on("click", function () {
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
//     confirmButtonText:   "Fetch Receipts",
//     confirmButtonColor:  "#059669",
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
//       fetchReceipts(`/receipts/get-receipts-date-wise/?from=${from}&to=${to}`);
//     }
//   });
// });


// /* ===== KEYBOARD FIELD NAVIGATION ===== */
// document.addEventListener("DOMContentLoaded", function () {
//   const form = document.getElementById("receiptForm");
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
   RECEIPTS PAGE — JavaScript
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
      submitBtn.innerHTML = '<i class="fa-solid fa-pen-to-square"></i> Update Receipt';
    }
    if (deleteBtn) deleteBtn.style.display = "inline-flex";
    if (badgeEl)   badgeEl.style.display = "inline-flex";
  } else {
    statusMode.className = "status-mode mode-new";
    if (statusText) statusText.textContent = "New Entry";
    if (submitBtn) {
      submitBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Receipt';
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
  document.getElementById("receipt_date").value  = data.receipt_date || "";
  document.getElementById("search_name").value   = data.party_name   || "";
  fetchPartyBalance(data.party_name || "");
  document.getElementById("amount").value        = data.amount       || "";
  document.getElementById("method").value        = data.method       || "Cash";
  document.getElementById("description").value   = data.description  || "";
  if (window.SmartDescriptions) SmartDescriptions.refreshAll();

  const entryByName = document.getElementById("entryByName");
  if (entryByName) entryByName.textContent = data.created_by || "—";

  const hiddenId = document.getElementById("current_receipt_id");
  if (hiddenId) hiddenId.value = data.receipt_id || "";

  updateRecordChip(data.receipt_id);
  setFormMode(data.receipt_id ? "edit" : "new");
  if (window.DocumentAttachments) DocumentAttachments.load(data.receipt_id || "");
}


/* ===== DOCUMENT READY ===== */
$(document).ready(function () {

  // Set today's date on page load (if field is empty)
  const dateInput = document.getElementById("receipt_date");
  if (dateInput && !dateInput.value) {
    dateInput.valueAsDate = new Date();
  }

  // Set initial form mode based on whether we have an ID
  const existingId = document.getElementById("current_receipt_id")?.value;
  setFormMode(existingId ? "edit" : "new");
  if (window.DocumentAttachments) {
    DocumentAttachments.bindForm("receiptForm", "receipt", () => document.getElementById("current_receipt_id")?.value || "");
  }

  const autocompleteUrl = $("#search_name").data("autocomplete-url");
  let selectedIndex = -1;

  /* --- Autocomplete --- */
  $("#search_name").on("input", function () {
    const query          = $(this).val();
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
    url:      "/receipts/party-balance/",
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


/* ===== NAVIGATE RECEIPT (Previous / Next) ===== */
function navigateReceipt(action) {
  const currentId = document.getElementById("current_receipt_id").value || "";

  fetch(`/receipts/receipt/get/?action=${action}&current_id=${encodeURIComponent(currentId)}`)
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        // Swal.fire({
        //   title:              "End of Records",
        //   text:               action === "previous"
        //                         ? "You are at the first receipt."
        //                         : "You are at the latest receipt.",
        //   icon:               "info",
        //   confirmButtonColor: "#2563eb",
        //   toast:              true,
        //   position:           "top-end",
        //   timer:              2000,
        //   showConfirmButton:  false
        // });
        Alerts.notify(action === "previous" ? "You are at the first receipt." : "You are at the latest receipt.", { title: "End of Records" });
        return;
      }
      populateForm(data);
    })
    .catch(err => console.error("Navigation error:", err));
}


/* ===== DELETE CONFIRM ===== */
document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("receiptForm");
  let confirmedDelete = false;

  form.addEventListener("submit", function (e) {
    const btn = e.submitter;
    if (btn && btn.value === "delete" && !confirmedDelete) {
      e.preventDefault();
      // Swal.fire({
      //   title:              "Delete this receipt?",
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
        title: "Delete this receipt?",
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


/* ===== FETCH RECEIPTS (History / Date-Wise) ===== */
function fetchReceipts(url) {
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
        //   title: "No Receipts Found",
        //   text:  "No receipts match this query.",
        //   icon:  "info",
        //   confirmButtonColor: "#059669"
        // });
        Alerts.notify("No receipts match this query.", { title: "No Receipts Found" });
        return;
      }

      let html = `
        <div style="margin-bottom:10px;">
          <input type="text" id="receiptSearch"
                 placeholder="🔍 Search by party or ref #"
                 style="width:100%;padding:8px 12px;border:1.5px solid #e2e8f0;
                        border-radius:8px;font-size:0.875rem;outline:none;
                        font-family:inherit;">
        </div>
        <div id="receiptsList" style="max-height:360px;overflow-y:auto;text-align:left;">
      `;

      let currentDate = null;

      response.forEach((receipt, index) => {
        if (receipt.receipt_date !== currentDate) {
          if (currentDate !== null) html += `</div>`;
          currentDate = receipt.receipt_date;
          html += `
            <div class="receipt-date-group">
              <div class="receipt-date-header">${currentDate}</div>
          `;
        }

        html += `
          <div class="receipt-row"
               data-party="${(receipt.party_name || "").toLowerCase()}"
               data-ref="${(receipt.reference_no || "").toLowerCase()}"
               data-id="${receipt.receipt_id}">
            <div class="receipt-top">
              <span class="receipt-ref">${receipt.reference_no || ""}</span>
              <span class="receipt-party">${receipt.party_name || ""}</span>
              <span class="receipt-amount">${Number(receipt.amount).toLocaleString()}</span>
            </div>
            <div class="receipt-tooltip">
              ${receipt.description || "No description"}
            </div>
          </div>
        `;

        if (index === response.length - 1) html += `</div>`;
      });

      html += `</div>`;

      Alerts.dialog({  /* was Swal.fire — centered detail view, standardized animation */
        title:             "📑 Receipt History",
        html:              html,
        width:             "660px",
        showConfirmButton: true,
        confirmButtonText: "Close",
        confirmButtonColor: "#6b7280",
        didOpen: () => {

          // Search filter
          document.getElementById("receiptSearch").addEventListener("input", function () {
            const q = this.value.toLowerCase();
            document.querySelectorAll(".receipt-row").forEach(row => {
              const visible = row.dataset.party.includes(q) || row.dataset.ref.includes(q);
              row.style.display = visible ? "flex" : "none";
            });
            document.querySelectorAll(".receipt-date-group").forEach(group => {
              const hasVisible = [...group.querySelectorAll(".receipt-row")]
                .some(r => r.style.display !== "none");
              group.style.display = hasVisible ? "block" : "none";
            });
          });

          // Click to load record
          document.querySelectorAll(".receipt-row").forEach(row => {
            row.addEventListener("click", function () {
              const id = this.dataset.id;
              fetch(`/receipts/receipt/get/?current_id=${id}`)
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
      //   text:  "Could not load receipts. Please try again.",
      //   icon:  "error",
      //   confirmButtonColor: "#dc2626"
      // });
      Alerts.error("Could not load receipts. Please try again.");
    }
  });
}

/* History button */
$("#btnOldReceipts").on("click", function () {
  fetchReceipts("/receipts/get-old-receipts/");
});

/* Date-wise button */
$("#btnCustomerReceipts").on("click", function () {
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
    confirmButtonText:   "Fetch Receipts",
    confirmButtonColor:  "#059669",
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
      fetchReceipts(`/receipts/get-receipts-date-wise/?from=${from}&to=${to}`);
    }
  });
});


/* ===== KEYBOARD FIELD NAVIGATION ===== */
document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("receiptForm");
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
