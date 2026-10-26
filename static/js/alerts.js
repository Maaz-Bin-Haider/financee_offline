/* ============================================================================
 * alerts.js — Financee unified alert layer (wraps SweetAlert2 v11)
 * ----------------------------------------------------------------------------
 * One consistent standard for every alert in the system. Load this AFTER the
 * SweetAlert2 CDN and it exposes a global `Alerts` object.
 *
 *   Alerts.success(message, opts)  -> top-right toast, auto-dismiss ~2.5s
 *   Alerts.error(message, opts)    -> top-right toast, MANUAL close (no timer)
 *   Alerts.notify(message, opts)   -> top-right toast, auto-dismiss ~3s
 *   Alerts.warning(message, opts)  -> bottom-center toast, auto-dismiss ~4s
 *   Alerts.confirm(opts) -> Promise<boolean>  centered modal, Confirm/Cancel
 *   Alerts.loading(message)        -> centered blocking spinner
 *   Alerts.dialog(opts)            -> centered modal (detail views, Close btn)
 *   Alerts.close()                 -> close the current popup
 *   Alerts.raw                     -> the underlying Swal (input dialogs, etc.)
 *
 * `message` is the primary body text. `opts` may override `title` or any raw
 * SweetAlert2 option. All methods return the SweetAlert2 promise so existing
 * `.then(...)` follow-up chains keep working.
 * ========================================================================== */
(function (global) {
  "use strict";

  if (typeof global.Swal === "undefined") {
    global.Alerts = null;
    /* eslint-disable no-console */
    if (global.console && console.warn) {
      console.warn("[alerts.js] SweetAlert2 (Swal) not found; Alerts disabled.");
    }
    return;
  }

  var Swal = global.Swal;

  var PALETTE = {
    success: "#16a34a",
    error:   "#dc2626",
    warning: "#d97706",
    notify:  "#2563eb",
    neutral: "#6b7280",
    primary: "#2563eb"
  };

  // Merge helper: start from `base`, apply the primary message as `text`
  // (unless the caller already supplied text), then let `opts` win over all.
  function build(base, message, opts) {
    opts = opts || {};
    var cfg = {};
    var k;
    for (k in base) { if (base.hasOwnProperty(k)) cfg[k] = base[k]; }
    if (message != null && opts.text == null) cfg.text = String(message);
    for (k in opts) { if (opts.hasOwnProperty(k)) cfg[k] = opts[k]; }
    return cfg;
  }

  // Pause/resume the auto-dismiss timer while the pointer is over the toast.
  function pauseOnHover(toast) {
    toast.addEventListener("mouseenter", Swal.stopTimer);
    toast.addEventListener("mouseleave", Swal.resumeTimer);
  }

  var Alerts = {
    /* ---- top-right family: success / error / notification ---------------- */
    success: function (message, opts) {
      return Swal.fire(build({
        toast: true,
        position: "top-end",
        icon: "success",
        title: "Success",
        timer: 2500,
        timerProgressBar: true,
        showConfirmButton: false,
        showClass: { popup: "alerts-anim-in-right" },
        hideClass: { popup: "alerts-anim-out-right" },
        customClass: { popup: "alerts-toast alerts-toast--success" },
        didOpen: pauseOnHover
      }, message, opts));
    },

    error: function (message, opts) {
      // No timer: errors persist until the user closes them.
      return Swal.fire(build({
        toast: true,
        position: "top-end",
        icon: "error",
        title: "Error",
        showConfirmButton: false,
        showCloseButton: true,
        showClass: { popup: "alerts-anim-shake" },
        hideClass: { popup: "alerts-anim-out-right" },
        customClass: { popup: "alerts-toast alerts-toast--error" }
      }, message, opts));
    },

    notify: function (message, opts) {
      return Swal.fire(build({
        toast: true,
        position: "top-end",
        icon: "info",
        title: "Notice",
        timer: 3000,
        timerProgressBar: true,
        showConfirmButton: false,
        showClass: { popup: "alerts-anim-in-right" },
        hideClass: { popup: "alerts-anim-out-right" },
        customClass: { popup: "alerts-toast alerts-toast--notify" },
        didOpen: pauseOnHover
      }, message, opts));
    },

    /* ---- bottom-center: warnings / validation ---------------------------- */
    warning: function (message, opts) {
      return Swal.fire(build({
        toast: true,
        position: "bottom",
        icon: "warning",
        title: "Warning",
        timer: 4000,
        timerProgressBar: true,
        showConfirmButton: false,
        showClass: { popup: "alerts-anim-in-up" },
        hideClass: { popup: "alerts-anim-out-down" },
        customClass: { popup: "alerts-toast alerts-toast--warning" },
        didOpen: pauseOnHover
      }, message, opts));
    },

    /* ---- centered: confirmation (returns Promise<boolean>) --------------- */
    confirm: function (opts) {
      opts = opts || {};
      var danger = !!opts.danger;
      return Swal.fire({
        icon: opts.icon || "warning",
        title: opts.title || "Are you sure?",
        text: opts.text,
        html: opts.html,
        position: "center",
        showCancelButton: true,
        reverseButtons: true,
        focusCancel: danger,
        confirmButtonText: opts.confirmText || "Confirm",
        cancelButtonText: opts.cancelText || "Cancel",
        confirmButtonColor: danger ? PALETTE.error : PALETTE.primary,
        cancelButtonColor: PALETTE.neutral,
        showClass: { popup: "alerts-anim-zoom-in" },
        hideClass: { popup: "alerts-anim-zoom-out" },
        customClass: { popup: "alerts-modal" }
      }).then(function (result) { return !!result.isConfirmed; });
    },

    /* ---- centered: blocking loading spinner ------------------------------ */
    loading: function (message) {
      return Swal.fire({
        title: message || "Please wait…",
        position: "center",
        allowOutsideClick: false,
        allowEscapeKey: false,
        showConfirmButton: false,
        showClass: { popup: "alerts-anim-zoom-in" },
        hideClass: { popup: "alerts-anim-zoom-out" },
        customClass: { popup: "alerts-modal" },
        didOpen: function () { Swal.showLoading(); }
      });
    },

    /* ---- centered: generic modal / detail view (Close button) ------------ */
    dialog: function (opts) {
      return Swal.fire(build({
        position: "center",
        confirmButtonText: "Close",
        confirmButtonColor: PALETTE.neutral,
        showClass: { popup: "alerts-anim-zoom-in" },
        hideClass: { popup: "alerts-anim-zoom-out" },
        customClass: { popup: "alerts-modal" }
      }, null, opts));
    },

    close: function () { Swal.close(); },

    PALETTE: PALETTE,
    raw: Swal
  };

  global.Alerts = Alerts;
})(window);
