$(function () {
  "use strict";

  /* ════════════ CONFIG ════════════ */
  var cfg = document.getElementById("partiesConfig");
  var AUTOCOMPLETE_URL = cfg.getAttribute("data-autocomplete-url");
  var ADD_URL          = cfg.getAttribute("data-add-url");
  var UPDATE_URL       = cfg.getAttribute("data-update-url");
  var LIST_URL         = cfg.getAttribute("data-list-url");

  var listLoaded = false;

  function getCsrf(form) {
    var el = form.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : "";
  }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  /* ════════════ TAB SWITCHING ════════════ */
  window.selectPartyTab = function (tab) {
    var map = {
      add:    { btn: "pbtn-add",    sec: "padd-section" },
      update: { btn: "pbtn-update", sec: "pupdate-section" },
      list:   { btn: "pbtn-list",   sec: "plist-section" }
    };
    Object.keys(map).forEach(function (k) {
      document.getElementById(map[k].sec).style.display = (k === tab) ? "block" : "none";
      document.getElementById(map[k].btn).classList.toggle("active", k === tab);
    });
    if (tab === "list" && !listLoaded) { loadPartiesList(); }
  };

  /* ════════════ ADD PARTY ════════════ */
  var addForm = document.getElementById("add_party_form");
  addForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var fd = new FormData(addForm);
    fetch(ADD_URL, {
      method: "POST",
      body: fd,
      headers: { "X-CSRFToken": getCsrf(addForm) }
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.status === "success") {
          listLoaded = false;
          // Swal.fire({ icon: "success", title: "Success", text: data.message,
          //             showConfirmButton: false, timer: 2200, timerProgressBar: true })
          Alerts.success(data.message)
              .then(function () {
                addForm.reset();
                document.getElementById("add_opening_balance").value = "0";
                document.getElementById("add_party_name").focus();
              });
        } else {
          // Swal.fire({ icon: "error", title: "Error", text: data.message, confirmButtonColor: "#3085d6" });
          Alerts.error(data.message);
        }
      })
      .catch(function () {
        // Swal.fire({ icon: "error", title: "Error", text: "Something went wrong while saving.", confirmButtonColor: "#d33" });
        Alerts.error("Something went wrong while saving.");
      });
  });

  /* ════════════ UPDATE PARTY ════════════ */
  var searchInput   = document.getElementById("search_name");
  var suggestionsBox = document.getElementById("suggestions");
  var editCard      = document.getElementById("pedit_card");
  var placeholder   = document.getElementById("pupdate_placeholder");
  var activeIndex   = -1;

  function clearSuggestions() {
    suggestionsBox.innerHTML = "";
    suggestionsBox.style.display = "none";
    activeIndex = -1;
  }

  function renderSuggestions(list) {
    suggestionsBox.innerHTML = "";
    activeIndex = -1;
    if (!list || !list.length) { suggestionsBox.style.display = "none"; return; }
    list.forEach(function (name) {
      var d = document.createElement("div");
      d.textContent = name;
      d.addEventListener("mousedown", function (ev) {
        ev.preventDefault();
        searchInput.value = name;
        clearSuggestions();
        doSearch();
      });
      d.addEventListener("mouseover", function () {
        setActive(Array.prototype.indexOf.call(suggestionsBox.children, d));
      });
      suggestionsBox.appendChild(d);
    });
    suggestionsBox.style.display = "block";
  }

  function setActive(idx) {
    var nodes = suggestionsBox.children;
    if (!nodes.length) return;
    if (idx < 0) idx = nodes.length - 1;
    if (idx >= nodes.length) idx = 0;
    for (var i = 0; i < nodes.length; i++) nodes[i].classList.remove("active-suggestion");
    nodes[idx].classList.add("active-suggestion");
    nodes[idx].scrollIntoView({ block: "nearest" });
    activeIndex = idx;
  }

  searchInput.addEventListener("input", function () {
    var q = searchInput.value.trim();
    if (q.length < 1) { clearSuggestions(); return; }
    fetch(AUTOCOMPLETE_URL + "?term=" + encodeURIComponent(q))
      .then(function (r) { return r.json(); })
      .then(function (list) { renderSuggestions(list); });
  });

  searchInput.addEventListener("keydown", function (e) {
    var open = suggestionsBox.style.display === "block" && suggestionsBox.children.length;
    if (e.key === "ArrowDown") {
      if (open) { e.preventDefault(); setActive(activeIndex + 1); }
    } else if (e.key === "ArrowUp") {
      if (open) { e.preventDefault(); setActive(activeIndex - 1); }
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (open && activeIndex >= 0) { searchInput.value = suggestionsBox.children[activeIndex].textContent; }
      clearSuggestions();
      doSearch();
    } else if (e.key === "Escape") {
      clearSuggestions();
    }
  });

  document.addEventListener("click", function (e) {
    if (!e.target.closest("#search_name, #suggestions")) { clearSuggestions(); }
  });

  function resetUpdateSection() {
    document.getElementById("update_party_form").reset();
    document.getElementById("upd_party_id").value = "";
    searchInput.value = "";
    editCard.style.display = "none";
    placeholder.style.display = "block";
    document.getElementById("padded_by_note").style.display = "none";
    clearSuggestions();
  }

  function fillForm(p) {
    document.getElementById("upd_party_id").value = p.party_id || "";
    document.getElementById("upd_party_name").value = p.party_name || "";
    document.getElementById("upd_party_type").value = (p.party_type === "Expense") ? "Expense" : "Both";
    document.getElementById("upd_contact_info").value = p.contact_info || "";
    document.getElementById("upd_address").value = p.address || "";
    document.getElementById("upd_opening_balance").value = (p.opening_balance != null ? p.opening_balance : 0);
    document.getElementById("upd_balance_type").value = (p.balance_type === "Credit") ? "Credit" : "Debit";

    var note = document.getElementById("padded_by_note");
    var nameEl = document.getElementById("padded_by_name");
    if (p.created_by_username && p.created_by_username !== "N/A") {
      nameEl.textContent = p.created_by_username;
      note.style.display = "flex";
    } else {
      note.style.display = "none";
    }
    editCard.style.display = "block";
    placeholder.style.display = "none";
  }

  window.FinanceeOpenMaster = function (record) { selectPartyTab("update"); fillForm(record); };

  function doSearch() {
    var name = searchInput.value.trim();
    if (!name) {
      // Swal.fire({ icon: "info", title: "Enter a name", text: "Please type a party name to search.", confirmButtonColor: "#3085d6" });
      Alerts.warning("Please type a party name to search.", { title: "Enter a name" });
      return;
    }
    fetch(UPDATE_URL + "?search_name=" + encodeURIComponent(name), {
      headers: { "X-Requested-With": "XMLHttpRequest" }
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.status === "found") {
          fillForm(data.party);
        } else {
          editCard.style.display = "none";
          placeholder.style.display = "block";
          // Swal.fire({ icon: "error", title: "Not found", text: "Party '" + name + "' was not found.", confirmButtonColor: "#3085d6" });
          Alerts.error("Party '" + name + "' was not found.", { title: "Not found" });
        }
      })
      .catch(function () {
        // Swal.fire({ icon: "error", title: "Error", text: "Could not search for the party.", confirmButtonColor: "#d33" });
        Alerts.error("Could not search for the party.");
      });
  }

  document.getElementById("search_party_btn").addEventListener("click", doSearch);

  var updForm = document.getElementById("update_party_form");
  updForm.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!document.getElementById("upd_party_id").value) {
      // Swal.fire({ icon: "info", title: "No party selected", text: "Please search and select a party first.", confirmButtonColor: "#3085d6" });
      Alerts.warning("Please search and select a party first.", { title: "No party selected" });
      return;
    }
    var fd = new FormData(updForm);
    fetch(UPDATE_URL, {
      method: "POST",
      body: fd,
      headers: { "X-CSRFToken": getCsrf(updForm), "X-Requested-With": "XMLHttpRequest" }
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.status === "success") {
          listLoaded = false;
          // Swal.fire({ icon: "success", title: "Success", text: data.message,
          //             showConfirmButton: false, timer: 2200, timerProgressBar: true })
          Alerts.success(data.message)
              .then(function () { resetUpdateSection(); });
        } else {
          // Swal.fire({ icon: "error", title: "Error", text: data.message, confirmButtonColor: "#3085d6" });
          Alerts.error(data.message);
        }
      })
      .catch(function () {
        // Swal.fire({ icon: "error", title: "Error", text: "Something went wrong while updating.", confirmButtonColor: "#d33" });
        Alerts.error("Something went wrong while updating.");
      });
  });

  /* ════════════ ALL PARTIES TABLE ════════════ */
  var tableBody = document.getElementById("partiesTableBody");

  function loadPartiesList() {
    tableBody.innerHTML = '<tr><td class="no-data" colspan="10">Loading parties…</td></tr>';
    fetch(LIST_URL, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.status !== "success") {
          tableBody.innerHTML = '<tr><td class="no-data" colspan="10">' + esc(data.message || "Could not load parties.") + '</td></tr>';
          return;
        }
        document.getElementById("partiesCount").textContent = data.count + (data.count === 1 ? " party" : " parties");
        if (!data.parties.length) {
          tableBody.innerHTML = '<tr><td class="no-data" colspan="10">No parties have been added yet.</td></tr>';
          listLoaded = true;
          return;
        }
        var html = "";
        data.parties.forEach(function (p, i) {
          var byUnknown = (!p.created_by || p.created_by === "N/A");
          var byCls = "by-pill" + (byUnknown ? " by-unknown" : "");
          var typeCls = "type-pill" + (p.party_type === "Expense" ? " type-expense" : "");
          html += "<tr>" +
            "<td>" + (i + 1) + "</td>" +
            "<td><strong>" + esc(p.party_name) + "</strong></td>" +
            '<td><span class="' + typeCls + '">' + esc(p.party_type || "—") + "</span></td>" +
            "<td>" + (esc(p.contact_info) || "—") + "</td>" +
            "<td>" + (esc(p.address) || "—") + "</td>" +
            "<td>" + esc(p.opening_balance) + "</td>" +
            "<td>" + (esc(p.balance_type) || "—") + "</td>" +
            '<td><span class="' + byCls + '"><i class="fa-solid fa-user-pen"></i>' + esc(p.created_by) + "</span></td>" +
            "<td>" + (esc(p.date_created) || "—") + "</td>" +
            '<td><button type="button" class="row-edit-btn" data-name="' + esc(p.party_name) + '"><i class="fa-solid fa-pen"></i> Edit</button></td>' +
            "</tr>";
        });
        tableBody.innerHTML = html;
        listLoaded = true;

        // Wire up per-row Edit buttons → jump to Update tab and load that party
        Array.prototype.forEach.call(tableBody.querySelectorAll(".row-edit-btn"), function (btn) {
          btn.addEventListener("click", function () {
            selectPartyTab("update");
            searchInput.value = btn.getAttribute("data-name");
            clearSuggestions();
            doSearch();
          });
        });
      })
      .catch(function () {
        tableBody.innerHTML = '<tr><td class="no-data" colspan="10">Could not load parties. Please try again.</td></tr>';
      });
  }

  document.getElementById("refreshPartiesBtn").addEventListener("click", function () { listLoaded = false; loadPartiesList(); });

  document.getElementById("partiesListSearch").addEventListener("input", function () {
    var q = this.value.toLowerCase();
    var rows = tableBody.querySelectorAll("tr");
    rows.forEach(function (row) {
      if (row.querySelector(".no-data")) return;
      var match = row.textContent.toLowerCase().indexOf(q) !== -1;
      row.classList.toggle("filtered-out", !match);
    });
  });

});
