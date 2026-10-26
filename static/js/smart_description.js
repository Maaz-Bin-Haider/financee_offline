(function () {
  const instances = new Map();

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function parseCsvLine(line) {
    const out = [];
    let cur = "";
    let quoted = false;
    for (let i = 0; i < line.length; i += 1) {
      const ch = line[i];
      const next = line[i + 1];
      if (ch === '"' && quoted && next === '"') {
        cur += '"';
        i += 1;
      } else if (ch === '"') {
        quoted = !quoted;
      } else if (ch === "," && !quoted) {
        out.push(cur.trim());
        cur = "";
      } else {
        cur += ch;
      }
    }
    out.push(cur.trim());
    return out;
  }

  function parseTable(text) {
    const normalized = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
    if (!normalized) return null;

    const lines = normalized.split("\n").filter((line) => line.trim() !== "");
    if (lines.length < 2) return null;

    let delimiter = null;
    if (lines.some((line) => line.includes("\t"))) {
      delimiter = "\t";
    } else if (lines.every((line) => parseCsvLine(line).length > 1)) {
      delimiter = ",";
    }
    if (!delimiter) return null;

    const rows = lines.map((line) => delimiter === "\t" ? line.split("\t").map((cell) => cell.trim()) : parseCsvLine(line));
    const maxCols = Math.max(...rows.map((row) => row.length));
    if (maxCols < 2) return null;

    const meaningfulRows = rows.filter((row) => row.some((cell) => String(cell || "").trim() !== ""));
    if (meaningfulRows.length < 2) return null;

    const consistentRows = meaningfulRows.filter((row) => row.length > 1).length;
    if (consistentRows < 2) return null;

    return {
      rows: meaningfulRows.map((row) => {
        const copy = row.slice();
        while (copy.length < maxCols) copy.push("");
        return copy;
      }),
      delimiter,
    };
  }

  function toTsv(table) {
    if (!table || !table.rows) return "";
    return table.rows.map((row) => row.map((cell) => String(cell || "").replace(/\t/g, " ")).join("\t")).join("\n");
  }

  function tableFromPreview(preview) {
    const rows = Array.from(preview.querySelectorAll(".smart-description-table tr")).map((tr) =>
      Array.from(tr.children).map((cell) => cell.textContent.trim())
    );
    return rows.length ? { rows, delimiter: "\t" } : null;
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    const temp = document.createElement("textarea");
    temp.value = text;
    temp.setAttribute("readonly", "readonly");
    temp.style.position = "fixed";
    temp.style.left = "-9999px";
    document.body.appendChild(temp);
    temp.select();
    document.execCommand("copy");
    temp.remove();
    return Promise.resolve();
  }

  function notify(message) {
    if (window.Alerts && Alerts.notify) {
      Alerts.notify(message, { title: "Description" });
    }
  }

  function buildPreview(table) {
    const [headers, ...bodyRows] = table.rows;
    const head = headers.map((cell, index) => `<th contenteditable="true" spellcheck="false">${escapeHtml(cell || `Column ${index + 1}`)}</th>`).join("");
    const body = bodyRows.map((row) => `
      <tr>${row.map((cell) => `<td contenteditable="true" spellcheck="false">${escapeHtml(cell)}</td>`).join("")}</tr>
    `).join("");
    return `
      <div class="smart-description-table-scroll">
        <table class="smart-description-table">
          <thead><tr>${head}</tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
      <div class="smart-description-preview-foot">
        <span>${table.rows.length - 1} row${table.rows.length - 1 === 1 ? "" : "s"}</span>
        <span>${table.rows[0].length} column${table.rows[0].length === 1 ? "" : "s"}</span>
      </div>
    `;
  }

  function buildModalTable(table) {
    const [headers, ...bodyRows] = table.rows;
    const head = headers.map((cell, index) => `<th contenteditable="true" spellcheck="false">${escapeHtml(cell || `Column ${index + 1}`)}</th>`).join("");
    const body = bodyRows.map((row) => `
      <tr>${row.map((cell) => `<td contenteditable="true" spellcheck="false">${escapeHtml(cell)}</td>`).join("")}</tr>
    `).join("");
    return `
      <div class="smart-description-modal-body" data-sd-modal-kind="table">
        <div class="smart-description-modal-hint">
          <i class="fa-solid fa-table-cells"></i>
          Edit cells directly. Apply keeps the same spreadsheet-friendly format.
        </div>
        <div class="smart-description-table-scroll smart-description-modal-table-scroll">
          <table class="smart-description-table smart-description-modal-table">
            <thead><tr>${head}</tr></thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      </div>
    `;
  }

  function buildModalText(value) {
    return `
      <div class="smart-description-modal-body" data-sd-modal-kind="text">
        <div class="smart-description-modal-hint">
          <i class="fa-solid fa-align-left"></i>
          Write or paste normal notes, CSV, or spreadsheet rows.
        </div>
        <textarea class="smart-description-modal-textarea" spellcheck="true">${escapeHtml(value || "")}</textarea>
      </div>
    `;
  }

  function autosize(textarea, expanded) {
    textarea.style.height = "auto";
    const max = expanded ? 260 : 150;
    textarea.style.height = `${Math.min(textarea.scrollHeight, max)}px`;
  }

  function enhance(textarea) {
    if (!textarea || instances.has(textarea)) return;

    const shell = document.createElement("div");
    shell.className = "smart-description-shell";

    const toolbar = document.createElement("div");
    toolbar.className = "smart-description-toolbar";
    toolbar.innerHTML = `
      <div class="smart-description-meta">
        <span class="smart-description-chip"><i class="fa-solid fa-wand-magic-sparkles"></i><span>Smart note</span></span>
        <span class="smart-description-count">0 / ${textarea.maxLength > 0 ? textarea.maxLength : "∞"}</span>
      </div>
      <div class="smart-description-actions">
        <button type="button" class="smart-description-btn" data-sd-action="copy" title="Copy description">
          <i class="fa-solid fa-copy"></i><span>Copy</span>
        </button>
        <button type="button" class="smart-description-btn" data-sd-action="raw" title="Edit raw description">
          <i class="fa-solid fa-pen-to-square"></i><span>Edit</span>
        </button>
        <button type="button" class="smart-description-btn" data-sd-action="expand" title="Expand description">
          <i class="fa-solid fa-up-right-and-down-left-from-center"></i><span>Expand</span>
        </button>
      </div>
    `;

    const preview = document.createElement("div");
    preview.className = "smart-description-preview";

    textarea.parentNode.insertBefore(shell, textarea);
    shell.appendChild(toolbar);
    shell.appendChild(textarea);
    shell.appendChild(preview);

    let currentTable = null;
    const count = toolbar.querySelector(".smart-description-count");
    const copyBtn = toolbar.querySelector('[data-sd-action="copy"]');
    const rawBtn = toolbar.querySelector('[data-sd-action="raw"]');
    const expandBtn = toolbar.querySelector('[data-sd-action="expand"]');
    let rawVisible = false;
    let syncingFromTable = false;

    const api = {
      refresh() {
        if (syncingFromTable) return;
        const value = textarea.value || "";
        const max = textarea.maxLength > 0 ? textarea.maxLength : "∞";
        count.textContent = `${value.length} / ${max}`;
        shell.classList.toggle("has-value", value.trim().length > 0);

        const table = parseTable(value);
        currentTable = table;
        shell.classList.toggle("has-table", Boolean(table));
        shell.classList.toggle("is-raw-visible", !table || rawVisible);
        preview.innerHTML = table ? buildPreview(table) : "";
        rawBtn.style.display = table ? "inline-flex" : "none";
        rawBtn.classList.toggle("is-active", Boolean(table && rawVisible));
        rawBtn.title = rawVisible ? "Hide raw description" : "Edit raw description";
        rawBtn.querySelector("span").textContent = rawVisible ? "Hide raw" : "Edit raw";
        copyBtn.title = table ? "Copy table as spreadsheet text" : "Copy description";
        autosize(textarea, shell.classList.contains("is-expanded"));
      },
    };

    textarea.addEventListener("input", api.refresh);
    textarea.addEventListener("paste", function () {
      window.setTimeout(() => {
        rawVisible = false;
        api.refresh();
      }, 0);
    });

    preview.addEventListener("input", function (event) {
      if (!event.target.closest("[contenteditable='true']")) return;
      currentTable = tableFromPreview(preview);
      if (!currentTable) return;
      syncingFromTable = true;
      textarea.value = toTsv(currentTable);
      const max = textarea.maxLength > 0 ? textarea.maxLength : "∞";
      count.textContent = `${textarea.value.length} / ${max}`;
      syncingFromTable = false;
      shell.classList.add("has-value", "has-table");
    });

    copyBtn.addEventListener("click", function () {
      const text = currentTable ? toTsv(currentTable) : (textarea.value || "");
      if (!text.trim()) {
        notify("There is no description to copy.");
        return;
      }
      copyText(text).then(() => {
        copyBtn.classList.remove("is-copied");
        void copyBtn.offsetWidth;
        copyBtn.classList.add("is-copied");
        const label = copyBtn.querySelector("span");
        const old = label.textContent;
        label.textContent = "Copied";
        window.setTimeout(() => { label.textContent = old; }, 1200);
      });
    });

    expandBtn.addEventListener("click", function () {
      const Swal = window.Alerts && Alerts.raw;
      if (!Swal) {
        const expanded = !shell.classList.contains("is-expanded");
        shell.classList.toggle("is-expanded", expanded);
        expandBtn.classList.toggle("is-active", expanded);
        autosize(textarea, expanded);
        return;
      }

      const table = currentTable || parseTable(textarea.value || "");
      Swal.fire({
        title: "Description",
        html: table ? buildModalTable(table) : buildModalText(textarea.value || ""),
        width: Math.min(window.innerWidth - 32, 980),
        showCancelButton: true,
        confirmButtonText: "Apply",
        cancelButtonText: "Close",
        confirmButtonColor: "#2563eb",
        cancelButtonColor: "#64748b",
        focusConfirm: false,
        showClass: { popup: "smart-description-modal-in" },
        hideClass: { popup: "smart-description-modal-out" },
        customClass: {
          popup: "alerts-modal smart-description-modal",
          title: "smart-description-modal-title",
          htmlContainer: "smart-description-modal-html",
          actions: "smart-description-modal-actions",
        },
        didOpen: function () {
          const firstCell = document.querySelector(".smart-description-modal [contenteditable='true']");
          const modalText = document.querySelector(".smart-description-modal-textarea");
          if (firstCell) firstCell.focus();
          else if (modalText) modalText.focus();
        },
        preConfirm: function () {
          const modal = document.querySelector(".smart-description-modal");
          const modalText = modal && modal.querySelector(".smart-description-modal-textarea");
          if (modalText) return modalText.value;
          const modalTable = modal && tableFromPreview(modal);
          return modalTable ? toTsv(modalTable) : textarea.value || "";
        },
      }).then(function (result) {
        if (!result.isConfirmed) return;
        textarea.value = result.value || "";
        rawVisible = false;
        api.refresh();
      });
    });

    rawBtn.addEventListener("click", function () {
      rawVisible = !rawVisible;
      api.refresh();
    });

    instances.set(textarea, api);
    api.refresh();
  }

  function init(root) {
    (root || document).querySelectorAll("textarea[data-smart-description]").forEach(enhance);
  }

  function refreshAll() {
    instances.forEach((api) => api.refresh());
  }

  document.addEventListener("DOMContentLoaded", function () {
    init(document);
  });

  window.SmartDescriptions = {
    init,
    refreshAll,
    refresh(textarea) {
      const api = instances.get(textarea);
      if (api) api.refresh();
    },
  };
})();
