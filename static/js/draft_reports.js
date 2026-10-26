/*
 * Pending Drafts report, the history exports and the Proforma Invoice document.
 *
 * Ported from the sibling Accounting-Plus-Inventory-System (feature commit
 * 80e8f8a). The one change is the currency: the source printed a fixed
 * currency code in every money label; here each label reads the company's
 * base currency from window.FINANCEE_CURRENCY (rendered by the draft page
 * templates), falling back to "PKR" when a page does not set it. The age
 * threshold in the ageing note likewise falls back to DRAFT_AGE_WARNING_DAYS.
 *
 * Dual-mode: pure helpers first, browser global last, so Node can require()
 * the real file and test the logic rather than a copy of it.
 *
 * THE ONE RULE THIS FILE EXISTS TO KEEP: a draft's rate is optional by design,
 * so an indicative total that silently omits unpriced lines is the normal case
 * here, not an edge case. Every surface -- table, CSV and PDF -- must carry the
 * warning saying how many units have no agreed rate.
 */

(function (root, factory) {
  var api = factory(root);
  if (typeof module !== "undefined" && module.exports) { module.exports = api; }
  /* One namespaced global rather than formatDate/formatMoney/formatInt spread
     across window. */
  if (root) { root.DraftReports = api; }
}(typeof window !== "undefined" ? window : null, function (root) {
  "use strict";

  /* ── the company's currency ───────────────────────────────────────── */

  /* Read at call time, not at load time, so the order of the page's own
     <script> tags cannot freeze the fallback into a label. */
  function currency() {
    var code = root && root.FINANCEE_CURRENCY;
    code = code == null ? "" : String(code).trim();
    return code || "PKR";
  }

  function moneyLabel(label) {
    return label + " (" + currency() + ")";
  }

  /* The age threshold the server applied (summary.age_warning_days), else the
     page's DRAFT_AGE_WARNING_DAYS, else the documented default of 30. */
  function ageWarningDays(summary) {
    var fromSummary = Number(summary && summary.age_warning_days);
    if (isFinite(fromSummary) && fromSummary > 0) { return fromSummary; }
    var fromPage = Number(root && root.DRAFT_AGE_WARNING_DAYS);
    if (isFinite(fromPage) && fromPage > 0) { return fromPage; }
    return 30;
  }

  /* ── formatting ───────────────────────────────────────────────────── */

  /* Three-letter months, pinned, matching report_pdf.js: toLocaleDateString
     renders September as "Sept" in some locales. */
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function formatDate(value) {
    if (!value) { return ""; }
    var parts = String(value).slice(0, 10).split("-");
    if (parts.length !== 3) { return String(value); }
    var month = MONTHS[Number(parts[1]) - 1];
    if (!month) { return String(value); }
    return parts[2] + " " + month + " " + parts[0];
  }

  function formatMoney(value) {
    var number = Number(value);
    if (!isFinite(number)) { return "0.00"; }
    return number.toLocaleString("en-AE",
      { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function formatInt(value) {
    var number = Number(value);
    return isFinite(number) ? String(Math.round(number)) : "0";
  }

  /* ── the column contract ──────────────────────────────────────────── */

  /* One declaration read by the table, the CSV and the PDF, so they cannot
     drift apart. `money: true` puts the currency in the label. */
  var PENDING_COLUMNS = [
    { key: "draft_invoice_id", label: "Draft #", format: function (r) { return "#" + r.draft_invoice_id; } },
    { key: "draft_date", label: "Date", format: function (r) { return formatDate(r.draft_date); } },
    { key: "customer", label: "Customer", format: function (r) { return r.customer || ""; } },
    { key: "status_label", label: "Status", format: function (r) { return r.status_label || ""; } },
    { key: "reserved_units", label: "Reserved", format: function (r) { return formatInt(r.reserved_units); }, numeric: true },
    { key: "unpriced_units", label: "Unpriced", format: function (r) { return formatInt(r.unpriced_units); }, numeric: true },
    { key: "indicative_value", label: "Indicative", money: true, format: indicativeCell, numeric: true },
    { key: "days_outstanding", label: "Days Open", format: function (r) { return formatInt(r.days_outstanding); }, numeric: true },
  ];

  /* An em dash, never 0.00, when nothing on the draft carries a rate. A zero
     here would read as "worth nothing" rather than "not yet priced". */
  function indicativeCell(row) {
    var value = Number(row.indicative_value || 0);
    if (!value && Number(row.unpriced_units || 0) > 0) { return "—"; }
    return formatMoney(value);
  }

  function pendingHead() {
    return PENDING_COLUMNS.map(function (c) {
      return c.money ? moneyLabel(c.label) : c.label;
    });
  }

  function pendingRows(payload) {
    var rows = (payload && payload.rows) || [];
    return rows.map(function (row) {
      return PENDING_COLUMNS.map(function (column) { return column.format(row); });
    });
  }

  /* ── the warning ──────────────────────────────────────────────────── */

  /* Returns null when nothing is unpriced, so a caller can simply test it. */
  function pendingWarning(summary) {
    if (!summary) { return null; }
    var unpriced = Number(summary.unpriced_units || 0);
    if (!unpriced) { return null; }
    return "Indicative value is understated: " + unpriced
      + " reserved unit(s) have no agreed rate yet and contribute nothing to it.";
  }

  function agedWarning(summary) {
    if (!summary) { return null; }
    var aged = Number(summary.aged_drafts || 0);
    if (!aged) { return null; }
    return aged + " draft(s) have been open for "
      + formatInt(ageWarningDays(summary)) + " days or more.";
  }

  function pendingSummaryChips(summary) {
    if (!summary) { return []; }
    var chips = [
      ["Open Drafts", formatInt(summary.draft_count)],
      ["Customers", formatInt(summary.customer_count)],
      ["Reserved Units", formatInt(summary.reserved_units)],
      /* The same em-dash rule the table uses, so the chip and the row beside
         it never disagree about the identical figure. */
      [moneyLabel("Indicative"), indicativeCell({
        indicative_value: summary.indicative_value,
        unpriced_units: summary.unpriced_units })],
    ];
    if (Number(summary.unpriced_units || 0) > 0) {
      chips.push(["Unpriced Units", formatInt(summary.unpriced_units)]);
    }
    if (Number(summary.aged_drafts || 0) > 0) {
      chips.push(["Ageing", formatInt(summary.aged_drafts)]);
    }
    return chips;
  }

  /* ── CSV ──────────────────────────────────────────────────────────── */

  function csvCell(value) {
    var text = value == null ? "" : String(value);
    return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
  }

  function pendingCsv(payload) {
    var lines = [];
    var summary = payload && payload.summary;
    /* The warning leads the file. A reader who opens the CSV and never scrolls
       to the bottom must still be told the total is understated. */
    var warning = pendingWarning(summary);
    if (warning) { lines.push(csvCell(warning)); }
    var aged = agedWarning(summary);
    if (aged) { lines.push(csvCell(aged)); }
    if (lines.length) { lines.push(""); }

    lines.push(pendingHead().map(csvCell).join(","));
    pendingRows(payload).forEach(function (row) {
      lines.push(row.map(csvCell).join(","));
    });
    return lines.join("\n");
  }

  /* ── the Pending Drafts PDF ───────────────────────────────────────── */

  function pendingNotes(summary) {
    return [pendingWarning(summary), agedWarning(summary)]
      .filter(function (n) { return Boolean(n); });
  }

  /* ── Draft history export ─────────────────────────────────────────────
     The History popup's own rows, turned into a sheet. The rows are passed in
     rather than re-fetched: the export has to say what the operator is looking
     at, and a second query could answer differently. */
  function historyHead() {
    return ["#", "Draft", "Date", "Customer", "Status", "Reserved", moneyLabel("Indicative")];
  }

  function historyRows(rows) {
    return (rows || []).map(function (row, index) {
      return [
        String(index + 1),
        "#" + row.draft_invoice_id,
        formatDate(row.draft_date),
        String(row.customer == null ? "" : row.customer),
        String(row.status_label == null ? (row.status || "") : row.status_label),
        formatInt(row.reserved_units),
        /* An em dash, not a zero: a line with no agreed rate contributes
           nothing to a total, and 0.00 would read as "free". */
        Number(row.unpriced_lines) > 0
          ? "—"
          : formatMoney(row.indicative_value),
      ];
    });
  }

  function historyTotals(rows) {
    var drafts = (rows || []).length;
    var reserved = 0;
    var value = 0;
    var unpriced = 0;
    (rows || []).forEach(function (row) {
      reserved += Number(row.reserved_units) || 0;
      if (Number(row.unpriced_lines) > 0) { unpriced += 1; } else {
        value += Number(row.indicative_value) || 0;
      }
    });
    return { drafts: drafts, reserved: reserved, value: value, unpriced: unpriced };
  }

  function historySummaryChips(rows) {
    var t = historyTotals(rows);
    var chips = [
      ["Drafts", formatInt(t.drafts)],
      ["Reserved units", formatInt(t.reserved)],
      ["Indicative value", formatMoney(t.value)],
    ];
    if (t.unpriced > 0) {
      chips.push(["Drafts with no rate yet", formatInt(t.unpriced)]);
    }
    return chips;
  }

  function historyContext(deps) {
    if (deps && deps.from && deps.to) {
      return "Drafts dated " + formatDate(deps.from) + " to " + formatDate(deps.to);
    }
    return "All drafts";
  }

  function historyPdfOptions(rows, deps) {
    var t = historyTotals(rows);
    var notes = t.unpriced > 0
      ? [t.unpriced + " draft(s) carry at least one line with no agreed rate. "
         + "Those lines are excluded from the indicative value, so the total "
         + "below is a floor rather than the expected invoice."]
      : [];
    return {
      jsPDF: deps && deps.jsPDF,
      title: "Draft Invoice History",
      module: "draft",
      context: historyContext(deps),
      summary: historySummaryChips(rows),
      head: historyHead(),
      body: historyRows(rows),
      orient: "l",
      afterTable: notes.length ? drawNotes(notes) : undefined,
      generatedAt: deps && deps.generatedAt,
    };
  }

  /* ── Confirmed draft return history export ───────────────────────────
     Exported on the same terms as the draft history: rows in, sheet out. */
  function returnHistoryHead() {
    return ["#", "Return", "Date", "Customer", "From Draft", moneyLabel("Amount")];
  }

  function returnHistoryRows(rows) {
    return (rows || []).map(function (row, index) {
      return [
        String(index + 1),
        "#" + row.draft_return_id,
        formatDate(row.return_date),
        String(row.customer == null ? "" : row.customer),
        row.draft_invoice_id ? "#" + row.draft_invoice_id : "—",
        formatMoney(row.total_amount),
      ];
    });
  }

  function returnHistoryTotals(rows) {
    var total = 0;
    var drafts = {};
    (rows || []).forEach(function (row) {
      total += Number(row.total_amount) || 0;
      if (row.draft_invoice_id) { drafts[row.draft_invoice_id] = true; }
    });
    return {
      returns: (rows || []).length,
      value: total,
      drafts: Object.keys(drafts).length,
    };
  }

  function returnHistorySummaryChips(rows) {
    var t = returnHistoryTotals(rows);
    return [
      ["Returns", formatInt(t.returns)],
      ["Drafts involved", formatInt(t.drafts)],
      ["Returned value", formatMoney(t.value)],
    ];
  }

  function returnHistoryContext(deps) {
    if (deps && deps.from && deps.to) {
      return "Returns dated " + formatDate(deps.from) + " to " + formatDate(deps.to);
    }
    return "All confirmed draft returns";
  }

  function returnHistoryPdfOptions(rows, deps) {
    return {
      jsPDF: deps && deps.jsPDF,
      title: "Confirmed Draft Return History",
      module: "draft",
      context: returnHistoryContext(deps),
      summary: returnHistorySummaryChips(rows),
      head: returnHistoryHead(),
      body: returnHistoryRows(rows),
      orient: "l",
      generatedAt: deps && deps.generatedAt,
    };
  }

  function pendingPdfOptions(payload, deps) {
    var summary = payload && payload.summary;
    var notes = pendingNotes(summary);
    return {
      jsPDF: deps && deps.jsPDF,
      title: "Pending Draft Invoices",
      module: "draft",
      context: (deps && deps.context) || "All open drafts",
      summary: pendingSummaryChips(summary),
      head: pendingHead(),
      body: pendingRows(payload),
      orient: "l",
      /* afterTable is the theme's own mechanism for a note under the table.
         There is no `notes` option; assuming there was would throw the first
         time anyone pressed Download. */
      afterTable: notes.length ? drawNotes(notes) : undefined,
      generatedAt: deps && deps.generatedAt,
    };
  }

  /* Returns the afterTable callback the theme expects. Kept separate so the
     note text can be asserted purely, and the drawing through a stub. */
  function drawNotes(notes) {
    return function (doc, finalY) {
      var width = doc.internal.pageSize.width - 28;
      var y = finalY + 6;
      doc.setFont("helvetica", "normal");
      doc.setFontSize(8.5);
      notes.forEach(function (note) {
        var wrapped = doc.splitTextToSize(note, width);
        doc.text(wrapped, 14, y);
        y += (wrapped.length * 4) + 2;
      });
    };
  }

  /* ── the Proforma Invoice ─────────────────────────────────────────── */

  /* What the document says, separated from how it is drawn, so the wording
     can be tested without a PDF library. */
  function proformaModel(draft) {
    var items = ((draft && draft.items) || []).filter(function (item) {
      return item.serials && item.serials.length;
    });
    var units = 0;
    var priced = 0;
    var value = 0;
    var lines = items.map(function (item) {
      var qty = item.serials.length;
      units += qty;
      var rate = item.unit_price == null || item.unit_price === ""
        ? null : Number(item.unit_price);
      if (rate != null) { priced += qty; value += rate * qty; }
      return {
        item_name: item.item_name,
        qty: qty,
        rate: rate,
        /* Em dash, not 0.00: this line has no agreed rate. */
        rate_text: rate == null ? "—" : formatMoney(rate),
        amount_text: rate == null ? "—" : formatMoney(rate * qty),
        serials: item.serials.slice(),
      };
    });
    return {
      draft_invoice_id: draft && draft.draft_invoice_id,
      customer: (draft && draft.Party) || "",
      draft_date: formatDate(draft && draft.draft_date),
      status: (draft && draft.status_label) || (draft && draft.status) || "",
      lines: lines,
      total_units: units,
      unpriced_units: units - priced,
      indicative_value: value,
      indicative_text: priced ? formatMoney(value) : "—",
    };
  }

  /* The sentence that stops a proforma being paid against as though it were
     an invoice. It is the whole reason this document is not called one. */
  function proformaNotice(model) {
    var base = "PROFORMA ONLY - this is not a tax invoice and no payment is due "
      + "against it. These goods are reserved; a sale invoice is raised when the "
      + "rate is agreed.";
    if (model && model.unpriced_units > 0) {
      base += " " + model.unpriced_units
        + " unit(s) here have no agreed rate yet, so the value shown is incomplete.";
    }
    return base;
  }

  function proformaPdfOptions(draft, deps) {
    var model = proformaModel(draft);
    return {
      jsPDF: deps && deps.jsPDF,
      title: "Proforma Invoice",
      module: "draft",
      context: "Draft #" + model.draft_invoice_id + "   ·   " + model.customer
               + "   ·   " + model.draft_date,
      summary: [
        ["Reserved Units", formatInt(model.total_units)],
        ["Unpriced Units", formatInt(model.unpriced_units)],
        [moneyLabel("Indicative"), model.indicative_text],
      ],
      head: ["Item", "Qty", "Expected Rate", "Amount", "Serial Numbers"],
      body: model.lines.map(function (line) {
        return [line.item_name, String(line.qty), line.rate_text,
                line.amount_text, line.serials.join(", ")];
      }),
      afterTable: drawNotes([proformaNotice(model)]),
      generatedAt: deps && deps.generatedAt,
      _model: model,
    };
  }

  return {
    PENDING_COLUMNS: PENDING_COLUMNS,
    currency: currency,
    ageWarningDays: ageWarningDays,
    formatDate: formatDate,
    formatMoney: formatMoney,
    formatInt: formatInt,
    indicativeCell: indicativeCell,
    pendingHead: pendingHead,
    pendingRows: pendingRows,
    pendingWarning: pendingWarning,
    agedWarning: agedWarning,
    pendingSummaryChips: pendingSummaryChips,
    pendingCsv: pendingCsv,
    pendingNotes: pendingNotes,
    drawNotes: drawNotes,
    pendingPdfOptions: pendingPdfOptions,
    proformaModel: proformaModel,
    proformaNotice: proformaNotice,
    proformaPdfOptions: proformaPdfOptions,
    historyHead: historyHead,
    historyRows: historyRows,
    historyTotals: historyTotals,
    historySummaryChips: historySummaryChips,
    historyContext: historyContext,
    historyPdfOptions: historyPdfOptions,
    returnHistoryHead: returnHistoryHead,
    returnHistoryRows: returnHistoryRows,
    returnHistoryTotals: returnHistoryTotals,
    returnHistorySummaryChips: returnHistorySummaryChips,
    returnHistoryContext: returnHistoryContext,
    returnHistoryPdfOptions: returnHistoryPdfOptions,
  };
}));
