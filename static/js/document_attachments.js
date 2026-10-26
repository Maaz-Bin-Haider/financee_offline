(function () {
  const state = {
    docType: null,
    getId: null,
    current: {},
    form: null,
    confirmed: false,
  };

  function byId(id) {
    return document.getElementById(id);
  }

  function notify(message) {
    if (window.Alerts && Alerts.notify) {
      Alerts.notify(message, { title: "Attachment" });
    } else {
      alert(message);
    }
  }

  function confirmReplace(message) {
    if (window.Alerts && Alerts.confirm) {
      return Alerts.confirm({
        title: "Replace attachment?",
        text: message,
        confirmText: "Continue",
      });
    }
    return Promise.resolve(window.confirm(message));
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function cardFor(kind) {
    return document.querySelector(`[data-attachment-kind="${kind}"]`);
  }

  function selectedLabel(kind) {
    return byId(kind === "image" ? "attachment_image_selected" : "attachment_pdf_selected");
  }

  function renderSelected(kind) {
    const file = selectedFile(kind);
    const label = selectedLabel(kind);
    const card = cardFor(kind);
    if (!label) return;

    if (!file) {
      label.textContent = "No new file selected";
      label.classList.remove("has-selection");
      if (card) card.classList.remove("is-selected");
      return;
    }

    label.textContent = file.name;
    label.title = file.name;
    label.classList.add("has-selection");
    if (card) {
      card.classList.remove("is-selected");
      void card.offsetWidth;
      card.classList.add("is-selected");
    }
  }

  function renderStatus(kind, attachment) {
    const el = byId(`attachment_${kind}_status`);
    if (!el) return;
    if (!attachment) {
      el.classList.remove("has-file");
      el.innerHTML = `<span class="attachment-name attachment-empty">No ${kind === "image" ? "image" : "PDF"} attached</span>`;
      return;
    }
    const fileName = escapeHtml(attachment.file_name || "Attached file");
    const previewUrl = escapeHtml(attachment.preview_url || "#");
    const downloadUrl = escapeHtml(attachment.download_url || "#");
    el.classList.add("has-file");
    el.innerHTML = `
      <span class="attachment-name" title="${fileName}">${fileName}</span>
      <span class="attachment-actions">
        <a href="${previewUrl}" target="_blank" rel="noopener" title="Preview attachment" aria-label="Preview attachment">
          <i class="fa-solid fa-eye"></i><span>Preview</span>
        </a>
        <a href="${downloadUrl}" title="Download attachment" aria-label="Download attachment">
          <i class="fa-solid fa-arrow-down"></i><span>Download</span>
        </a>
      </span>
    `;
  }

  function selectedFile(kind) {
    const input = byId(kind === "image" ? "attachment_image" : "attachment_pdf");
    return input && input.files && input.files.length ? input.files[0] : null;
  }

  function replacementKinds() {
    return ["image", "pdf"].filter((kind) => selectedFile(kind) && state.current[kind]);
  }

  function clearInputs() {
    ["attachment_image", "attachment_pdf"].forEach((id, index) => {
      const input = byId(id);
      if (input) input.value = "";
      renderSelected(index === 0 ? "image" : "pdf");
    });
  }

  function reset() {
    state.current = {};
    clearInputs();
    renderStatus("image", null);
    renderStatus("pdf", null);
  }

  function load(documentId) {
    reset();
    if (!state.docType || !documentId) return;
    const panel = byId("attachments_panel");
    // Widget absent: the attachments feature is disabled for this company —
    // skip the metadata fetch entirely (the endpoint is blocked server-side).
    if (!panel) return;
    panel.dataset.loading = "1";
    fetch(`/attachments/${state.docType}/${encodeURIComponent(documentId)}/`)
      .then((res) => res.json())
      .then((data) => {
        if (!data.success) return;
        state.current = data.attachments || {};
        renderStatus("image", state.current.image);
        renderStatus("pdf", state.current.pdf);
      })
      .catch((err) => console.error("Attachment metadata error:", err))
      .finally(() => {
        if (panel) delete panel.dataset.loading;
      });
  }

  function appendToFormData(formData) {
    const image = selectedFile("image");
    const pdf = selectedFile("pdf");
    if (image) formData.append("attachment_image", image);
    if (pdf) formData.append("attachment_pdf", pdf);
  }

  function hasFiles() {
    return Boolean(selectedFile("image") || selectedFile("pdf"));
  }

  function requestOptions(payload, csrfToken) {
    if ((payload.action || "").toLowerCase() !== "delete" && hasFiles()) {
      const formData = new FormData();
      formData.append("payload", JSON.stringify(payload));
      appendToFormData(formData);
      return {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
        body: formData,
      };
    }
    return {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
      body: JSON.stringify(payload),
    };
  }

  function warnIfReplacingOnChange(kind) {
    const input = byId(kind === "image" ? "attachment_image" : "attachment_pdf");
    if (!input) return;
    if (input.dataset.attachmentBound === "1") return;
    input.dataset.attachmentBound = "1";
    input.addEventListener("change", function () {
      renderSelected(kind);
      if (selectedFile(kind) && state.current[kind]) {
        notify(`Uploading a new ${kind === "image" ? "image" : "PDF"} will replace the existing ${kind === "image" ? "image" : "PDF"}.`);
      }
    });
  }

  document.addEventListener("click", function (event) {
    const action = event.target.closest(".attachment-actions a");
    if (!action) return;
    action.classList.remove("attachment-action-pop");
    void action.offsetWidth;
    action.classList.add("attachment-action-pop");
  });

  function confirmReplacementIfNeeded() {
    const kinds = replacementKinds();
    if (!kinds.length || state.confirmed) return Promise.resolve(true);
    const label = kinds.map((kind) => (kind === "image" ? "image" : "PDF")).join(" and ");
    return confirmReplace(`By uploading a new ${label}, the old ${label} will be replaced.`).then((confirmed) => {
      state.confirmed = Boolean(confirmed);
      return Boolean(confirmed);
    });
  }

  function bindForm(formId, docType, getId) {
    init(docType, getId);
    state.form = byId(formId);
    if (!state.form) return;
    state.form.addEventListener("submit", function (event) {
      const submitter = event.submitter;
      if (submitter && submitter.value === "delete") return;
      if (state.confirmed || !replacementKinds().length) return;
      event.preventDefault();
      confirmReplacementIfNeeded().then((confirmed) => {
        if (confirmed) {
          state.form.requestSubmit(submitter || undefined);
          state.confirmed = false;
        }
      });
    });
  }

  function init(docType, getId) {
    state.docType = docType;
    state.getId = getId;
    warnIfReplacingOnChange("image");
    warnIfReplacingOnChange("pdf");
    const currentId = typeof getId === "function" ? getId() : "";
    if (currentId) load(currentId);
    else reset();
  }

  window.DocumentAttachments = {
    init,
    bindForm,
    load,
    reset,
    appendToFormData,
    hasFiles,
    requestOptions,
    confirmReplacementIfNeeded,
  };
})();
