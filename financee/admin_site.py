"""
Financee — custom admin site.

Adds, on top of the stock Django admin:
  * Superuser-only access to the whole admin panel.
  * Light / professional branding (Financee — Accounting Plus Inventory
    Management System, developed by Maaz Rehan).
  * A "User Activity" section that aggregates every user's activity across
    the business tables and shows which database schema each user belongs to.

This module is self-contained and additive: it does not change any existing
business logic. It only customises the admin panel.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import User, Group
from django.contrib import messages
from django.db import connection
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.http import Http404, HttpResponse
from django.utils import timezone
import datetime
import io

# ── Branding ────────────────────────────────────────────────────────────────
SYSTEM_NAME = "Financee"
SYSTEM_TAGLINE = "Accounting Plus Inventory Management System"
DEVELOPER = "Maaz Rehan"

# ── Activity sources ────────────────────────────────────────────────────────
# (label, table, user_column, date_column) — every business table that records
# which user created the row. date_column is cast to ::date in SQL so mixed
# timestamp / date columns compare cleanly.
ACTIVITY_SOURCES = [
    ("Items",             "items",                      "created_by",    "created_at"),
    ("Parties",           "parties",                    "created_by",    "date_created"),
    ("Payments",          "payments",                   "created_by",    "date_created"),
    ("Receipts",          "receipts",                   "created_by",    "date_created"),
    ("Sales Invoices",    "salesinvoices",              "created_by",    "invoice_date"),
    ("Purchase Invoices", "purchaseinvoices",           "created_by",    "invoice_date"),
    ("Sales Returns",     "salesreturns",               "created_by",    "return_date"),
    ("Purchase Returns",  "purchasereturns",            "created_by",    "return_date"),
    ("Contra Entries",    "contra_entries",             "created_by",    "date_created"),
    ("Opening Cash",      "opening_cash",               "created_by_id", "date_created"),
    ("Owner Equity",      "owner_equity_transactions",  "created_by_id", "date_created"),
]


def _app_schema():
    """The PostgreSQL schema the application's tables live in (e.g. 'public')."""
    try:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT table_schema FROM information_schema.tables
                WHERE table_name = 'items' AND table_type = 'BASE TABLE'
                LIMIT 1
            """)
            row = cur.fetchone()
            return row[0] if row else "public"
    except Exception:
        return "public"


def _collect_activity():
    """
    Returns a dict keyed by user id:
      { uid: {"counts": {label: n, ...}, "total": n, "last_date": date|None} }
    Each source is queried defensively so a missing table never breaks the page.
    """
    per_user = {}
    for label, table, col, datecol in ACTIVITY_SOURCES:
        try:
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT {col} AS uid, COUNT(*) AS cnt, MAX({dc})::date AS last_date "
                    "FROM {tbl} WHERE {col} IS NOT NULL GROUP BY {col}".format(
                        col=col, dc=datecol, tbl=table
                    )
                )
                rows = cur.fetchall()
        except Exception:
            rows = []
        for uid, cnt, last_date in rows:
            if uid is None:
                continue
            bucket = per_user.setdefault(uid, {"counts": {}, "total": 0, "last_date": None})
            bucket["counts"][label] = bucket["counts"].get(label, 0) + cnt
            bucket["total"] += cnt
            if last_date and (bucket["last_date"] is None or last_date > bucket["last_date"]):
                bucket["last_date"] = last_date
    return per_user


def _admin_action_counts():
    """How many admin-log actions each user has performed."""
    counts = {}
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT user_id, COUNT(*) FROM django_admin_log GROUP BY user_id"
            )
            for uid, cnt in cur.fetchall():
                counts[uid] = cnt
    except Exception:
        pass
    return counts


def build_user_activity():
    """Per-user activity rows for the User Activity list page."""
    activity = _collect_activity()
    admin_counts = _admin_action_counts()
    schema = _app_schema()

    rows = []
    users = User.objects.all().prefetch_related("groups").order_by("-is_superuser", "username")
    for u in users:
        a = activity.get(u.id, {"counts": {}, "total": 0, "last_date": None})
        groups = ", ".join(g.name for g in u.groups.all()) or "—"
        # last activity = latest of last record date and last_login
        last_login_date = u.last_login.date() if u.last_login else None
        last_dates = [d for d in (a["last_date"], last_login_date) if d]
        last_activity = max(last_dates) if last_dates else None

        if u.is_superuser:
            role = "Superuser"
        elif u.is_staff:
            role = "Staff"
        else:
            role = "User"

        rows.append({
            "id": u.id,
            "username": u.username,
            "full_name": u.get_full_name() or "—",
            "email": u.email or "—",
            "role": role,
            "is_active": u.is_active,
            "groups": groups,
            "schema": schema,
            "total_actions": a["total"],
            "admin_actions": admin_counts.get(u.id, 0),
            "last_login": u.last_login,
            "date_joined": u.date_joined,
            "last_activity": last_activity,
            "counts": a["counts"],
        })
    return rows, schema


# Detailed activity feed: one block per source. Each query returns
# (activity_date, recorded_at, amount, title, description) and accepts params
# in the order: user_id, date_from, date_from, date_to, date_to.
# (type_label, icon, is_monetary, sql)
ACTIVITY_DETAIL_SOURCES = [
    ("Sale", "fa-cart-shopping", True, """
        SELECT s.invoice_date AS activity_date, NULL::timestamp AS recorded_at, s.total_amount AS amount,
               'Sale to ' || COALESCE(c.party_name, '—') AS title,
               'Sales invoice #' || s.sales_invoice_id || ' to ''' || COALESCE(c.party_name,'—') ||
               ''' — Total ' || to_char(s.total_amount, 'FM999,999,990.00') AS description
        FROM salesinvoices s LEFT JOIN parties c ON c.party_id = s.customer_id
        WHERE s.created_by = %s
          AND (CAST(%s AS date) IS NULL OR s.invoice_date >= CAST(%s AS date))
          AND (CAST(%s AS date) IS NULL OR s.invoice_date <= CAST(%s AS date))
    """),
    ("Purchase", "fa-truck-ramp-box", True, """
        SELECT p.invoice_date, NULL::timestamp, p.total_amount,
               'Purchase from ' || COALESCE(v.party_name, '—'),
               'Purchase invoice #' || p.purchase_invoice_id || ' from ''' || COALESCE(v.party_name,'—') ||
               ''' — Total ' || to_char(p.total_amount, 'FM999,999,990.00') ||
               CASE WHEN p.is_opening THEN ' (Opening)' ELSE '' END
        FROM purchaseinvoices p LEFT JOIN parties v ON v.party_id = p.vendor_id
        WHERE p.created_by = %s
          AND (CAST(%s AS date) IS NULL OR p.invoice_date >= CAST(%s AS date))
          AND (CAST(%s AS date) IS NULL OR p.invoice_date <= CAST(%s AS date))
    """),
    ("Payment", "fa-money-bill-wave", True, """
        SELECT p.payment_date, p.date_created, p.amount,
               'Payment to ' || COALESCE(pt.party_name, '—'),
               'Paid ' || to_char(p.amount, 'FM999,999,990.00') || ' via ' || COALESCE(p.method,'—') ||
               ' to ''' || COALESCE(pt.party_name,'—') || '''' ||
               COALESCE(' (Ref ' || NULLIF(p.reference_no,'') || ')', '') ||
               COALESCE(' — ' || NULLIF(COALESCE(p.description, p.notes),''), '')
        FROM payments p LEFT JOIN parties pt ON pt.party_id = p.party_id
        WHERE p.created_by = %s
          AND (CAST(%s AS date) IS NULL OR p.payment_date >= CAST(%s AS date))
          AND (CAST(%s AS date) IS NULL OR p.payment_date <= CAST(%s AS date))
    """),
    ("Receipt", "fa-hand-holding-dollar", True, """
        SELECT r.receipt_date, r.date_created, r.amount,
               'Receipt from ' || COALESCE(pt.party_name, '—'),
               'Received ' || to_char(r.amount, 'FM999,999,990.00') || ' via ' || COALESCE(r.method,'—') ||
               ' from ''' || COALESCE(pt.party_name,'—') || '''' ||
               COALESCE(' (Ref ' || NULLIF(r.reference_no,'') || ')', '') ||
               COALESCE(' — ' || NULLIF(COALESCE(r.description, r.notes),''), '')
        FROM receipts r LEFT JOIN parties pt ON pt.party_id = r.party_id
        WHERE r.created_by = %s
          AND (CAST(%s AS date) IS NULL OR r.receipt_date >= CAST(%s AS date))
          AND (CAST(%s AS date) IS NULL OR r.receipt_date <= CAST(%s AS date))
    """),
    ("Sales Return", "fa-rotate-left", True, """
        SELECT sr.return_date, NULL::timestamp, sr.total_amount,
               'Sales return — ' || COALESCE(c.party_name, '—'),
               'Sales return #' || sr.sales_return_id || ' from ''' || COALESCE(c.party_name,'—') ||
               ''' — Total ' || to_char(sr.total_amount, 'FM999,999,990.00')
        FROM salesreturns sr LEFT JOIN parties c ON c.party_id = sr.customer_id
        WHERE sr.created_by = %s
          AND (CAST(%s AS date) IS NULL OR sr.return_date >= CAST(%s AS date))
          AND (CAST(%s AS date) IS NULL OR sr.return_date <= CAST(%s AS date))
    """),
    ("Purchase Return", "fa-rotate-right", True, """
        SELECT pr.return_date, NULL::timestamp, pr.total_amount,
               'Purchase return — ' || COALESCE(v.party_name, '—'),
               'Purchase return #' || pr.purchase_return_id || ' to ''' || COALESCE(v.party_name,'—') ||
               ''' — Total ' || to_char(pr.total_amount, 'FM999,999,990.00')
        FROM purchasereturns pr LEFT JOIN parties v ON v.party_id = pr.vendor_id
        WHERE pr.created_by = %s
          AND (CAST(%s AS date) IS NULL OR pr.return_date >= CAST(%s AS date))
          AND (CAST(%s AS date) IS NULL OR pr.return_date <= CAST(%s AS date))
    """),
    ("Contra", "fa-right-left", True, """
        SELECT ce.contra_date, ce.date_created, ce.amount,
               'Contra: ' || COALESCE(fp.party_name,'—') || ' → ' || COALESCE(tp.party_name,'—'),
               'Contra of ' || to_char(ce.amount, 'FM999,999,990.00') || ' from ''' || COALESCE(fp.party_name,'—') ||
               ''' to ''' || COALESCE(tp.party_name,'—') || '''' ||
               COALESCE(' — ' || NULLIF(COALESCE(ce.description, ce.notes),''), '')
        FROM contra_entries ce
        LEFT JOIN parties fp ON fp.party_id = ce.from_party_id
        LEFT JOIN parties tp ON tp.party_id = ce.to_party_id
        WHERE ce.created_by = %s
          AND (CAST(%s AS date) IS NULL OR ce.contra_date >= CAST(%s AS date))
          AND (CAST(%s AS date) IS NULL OR ce.contra_date <= CAST(%s AS date))
    """),
    ("Opening Cash", "fa-vault", True, """
        SELECT oc.entry_date, oc.date_created, oc.amount,
               'Opening cash',
               'Opening cash entry of ' || to_char(oc.amount, 'FM999,999,990.00')
        FROM opening_cash oc
        WHERE oc.created_by_id = %s
          AND (CAST(%s AS date) IS NULL OR oc.entry_date >= CAST(%s AS date))
          AND (CAST(%s AS date) IS NULL OR oc.entry_date <= CAST(%s AS date))
    """),
    ("Owner Equity", "fa-scale-balanced", True, """
        SELECT oe.txn_date, oe.date_created, oe.amount,
               'Owner equity (' || oe.direction || ')',
               'Owner equity ' || oe.direction || ' of ' || to_char(oe.amount, 'FM999,999,990.00') ||
               COALESCE(' — ' || NULLIF(oe.description,''), '')
        FROM owner_equity_transactions oe
        WHERE oe.created_by_id = %s
          AND (CAST(%s AS date) IS NULL OR oe.txn_date >= CAST(%s AS date))
          AND (CAST(%s AS date) IS NULL OR oe.txn_date <= CAST(%s AS date))
    """),
    ("Item", "fa-box", False, """
        SELECT it.created_at::date, it.created_at, it.sale_price,
               'Item added: ' || it.item_name,
               'Added item ''' || it.item_name || '''' ||
               COALESCE(' — Sale price ' || to_char(it.sale_price, 'FM999,999,990.00'), '') ||
               COALESCE(' · Code ' || NULLIF(it.item_code,''), '') ||
               COALESCE(' · ' || NULLIF(it.category,''), '') ||
               COALESCE(' · ' || NULLIF(it.brand,''), '')
        FROM items it
        WHERE it.created_by = %s
          AND (CAST(%s AS date) IS NULL OR it.created_at::date >= CAST(%s AS date))
          AND (CAST(%s AS date) IS NULL OR it.created_at::date <= CAST(%s AS date))
    """),
    ("Party", "fa-user-group", False, """
        SELECT pa.date_created::date, pa.date_created, pa.opening_balance,
               'Party added: ' || pa.party_name,
               'Added party ''' || pa.party_name || ''' (' || pa.party_type || ')' ||
               COALESCE(' — Opening ' || to_char(pa.opening_balance, 'FM999,999,990.00') || ' ' || pa.balance_type, '')
        FROM parties pa
        WHERE pa.created_by = %s
          AND (CAST(%s AS date) IS NULL OR pa.date_created::date >= CAST(%s AS date))
          AND (CAST(%s AS date) IS NULL OR pa.date_created::date <= CAST(%s AS date))
    """),
]


def build_detailed_activity(user_id, date_from=None, date_to=None):
    """
    Returns (entries, summary, totals):
      entries  : list of activity dicts, newest first
      summary  : per-type {type, icon, monetary, count, total}
      totals   : {count, amount}
    Each source is queried defensively so a missing table never breaks the page.
    """
    entries = []
    summary = []
    grand_count = 0
    grand_amount = 0

    for type_label, icon, monetary, sql in ACTIVITY_DETAIL_SOURCES:
        rows = []
        try:
            with connection.cursor() as cur:
                cur.execute(sql, [user_id, date_from, date_from, date_to, date_to])
                rows = cur.fetchall()
        except Exception:
            rows = []

        type_count = 0
        type_total = 0
        for activity_date, recorded_at, amount, title, description in rows:
            amt = float(amount) if amount is not None else None
            entries.append({
                "type": type_label,
                "icon": icon,
                "monetary": monetary,
                "title": title,
                "description": description,
                "amount": amt,
                "date": activity_date,
                "recorded_at": recorded_at,
            })
            type_count += 1
            if amt is not None:
                type_total += amt

        summary.append({
            "type": type_label,
            "icon": icon,
            "monetary": monetary,
            "count": type_count,
            "total": type_total if monetary else None,
        })
        grand_count += type_count
        if monetary:
            grand_amount += type_total

    # newest first; fall back to a min date for sorting when a date is missing
    def sort_key(e):
        d = e["date"] or datetime.date.min
        r = e["recorded_at"] or datetime.datetime.min
        return (d, r)
    entries.sort(key=sort_key, reverse=True)

    return entries, summary, {"count": grand_count, "amount": grand_amount}


def _parse_date(value):
    """Parse a YYYY-MM-DD string into a date, or None."""
    if not value:
        return None
    try:
        return datetime.datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def _money(v):
    if v is None:
        return "—"
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v)


def _render_activity_pdf(user, entries, summary, totals, date_from, date_to, schema):
    """Build a polished, light/professional PDF of a user's detailed activity."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether,
    )

    BRAND = colors.HexColor("#2563eb")
    BRAND_DARK = colors.HexColor("#1d4ed8")
    INK = colors.HexColor("#0f172a")
    SLATE = colors.HexColor("#475569")
    MUTED = colors.HexColor("#94a3b8")
    LINE = colors.HexColor("#e5e9f2")
    STRIPE = colors.HexColor("#f8fafc")
    HEADBG = colors.HexColor("#1e293b")

    styles = getSampleStyleSheet()
    p_title = ParagraphStyle("p_title", parent=styles["Normal"], fontName="Helvetica-Bold",
                             fontSize=18, textColor=colors.white, leading=22)
    p_sub = ParagraphStyle("p_sub", parent=styles["Normal"], fontName="Helvetica",
                           fontSize=9, textColor=colors.HexColor("#dbeafe"), leading=12)
    p_h2 = ParagraphStyle("p_h2", parent=styles["Normal"], fontName="Helvetica-Bold",
                          fontSize=12, textColor=INK, leading=15, spaceBefore=6, spaceAfter=6)
    p_cell = ParagraphStyle("p_cell", parent=styles["Normal"], fontName="Helvetica",
                            fontSize=8.5, textColor=INK, leading=11)
    p_cell_b = ParagraphStyle("p_cell_b", parent=p_cell, fontName="Helvetica-Bold")
    p_cell_r = ParagraphStyle("p_cell_r", parent=p_cell, alignment=TA_RIGHT)
    p_th = ParagraphStyle("p_th", parent=styles["Normal"], fontName="Helvetica-Bold",
                          fontSize=7.5, textColor=colors.white, leading=10)
    p_th_r = ParagraphStyle("p_th_r", parent=p_th, alignment=TA_RIGHT)
    p_meta_k = ParagraphStyle("p_meta_k", parent=styles["Normal"], fontName="Helvetica",
                              fontSize=8.5, textColor=MUTED, leading=12)
    p_meta_v = ParagraphStyle("p_meta_v", parent=styles["Normal"], fontName="Helvetica-Bold",
                              fontSize=8.5, textColor=INK, leading=12)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=16 * mm, bottomMargin=18 * mm,
        title=f"{SYSTEM_NAME} — Activity report for {user.username}",
        author=DEVELOPER,
    )
    content_w = doc.width

    def header_band():
        inner = Table([[
            Paragraph("User Activity Report", p_title),
            Paragraph(SYSTEM_NAME + "<br/>" + SYSTEM_TAGLINE, ParagraphStyle(
                "brand_r", parent=p_sub, alignment=TA_RIGHT)),
        ]], colWidths=[content_w * 0.6, content_w * 0.4])
        inner.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ("BACKGROUND", (0, 0), (-1, -1), BRAND),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ]))
        return inner

    if date_from or date_to:
        rng = f"{date_from.strftime('%d %b %Y') if date_from else 'Beginning'} — {date_to.strftime('%d %b %Y') if date_to else 'Today'}"
    else:
        rng = "All time"

    role = "Superuser" if user.is_superuser else ("Staff" if user.is_staff else "User")
    groups = ", ".join(g.name for g in user.groups.all()) or "—"
    generated = timezone.localtime().strftime("%d %b %Y, %I:%M %p") if timezone.is_aware(timezone.now()) else datetime.datetime.now().strftime("%d %b %Y, %I:%M %p")

    meta = Table([
        [Paragraph("User", p_meta_k), Paragraph(f"{user.username} ({user.get_full_name() or '—'})", p_meta_v),
         Paragraph("Role", p_meta_k), Paragraph(role, p_meta_v)],
        [Paragraph("Email", p_meta_k), Paragraph(user.email or "—", p_meta_v),
         Paragraph("Groups", p_meta_k), Paragraph(groups, p_meta_v)],
        [Paragraph("Schema", p_meta_k), Paragraph(schema, p_meta_v),
         Paragraph("Date range", p_meta_k), Paragraph(rng, p_meta_v)],
        [Paragraph("Generated", p_meta_k), Paragraph(generated, p_meta_v),
         Paragraph("Total actions", p_meta_k), Paragraph(str(totals["count"]), p_meta_v)],
    ], colWidths=[content_w * 0.13, content_w * 0.37, content_w * 0.16, content_w * 0.34])
    meta.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, -1), STRIPE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
    ]))

    # Summary table
    sum_head = [Paragraph("Activity Type", p_th), Paragraph("Count", p_th_r), Paragraph("Total Amount", p_th_r)]
    sum_rows = [sum_head]
    for s in summary:
        if s["count"] == 0:
            continue
        sum_rows.append([
            Paragraph(s["type"], p_cell),
            Paragraph(str(s["count"]), p_cell_r),
            Paragraph(_money(s["total"]) if s["monetary"] else "—", p_cell_r),
        ])
    sum_rows.append([
        Paragraph("TOTAL", p_cell_b),
        Paragraph(str(totals["count"]), ParagraphStyle("tb", parent=p_cell_b, alignment=TA_RIGHT)),
        Paragraph(_money(totals["amount"]), ParagraphStyle("tb2", parent=p_cell_b, alignment=TA_RIGHT)),
    ])
    summary_tbl = Table(sum_rows, colWidths=[content_w * 0.5, content_w * 0.2, content_w * 0.3], repeatRows=1)
    sstyle = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADBG),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eff6ff")),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, BRAND),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i in range(1, len(sum_rows) - 1):
        if i % 2 == 0:
            sstyle.append(("BACKGROUND", (0, i), (-1, i), STRIPE))
    summary_tbl.setStyle(TableStyle(sstyle))

    # Detailed activity table
    det_head = [
        Paragraph("#", p_th), Paragraph("Date", p_th), Paragraph("Type", p_th),
        Paragraph("Details", p_th), Paragraph("Amount", p_th_r),
    ]
    det_rows = [det_head]
    for i, e in enumerate(entries, 1):
        d = e["date"].strftime("%d %b %Y") if e["date"] else "—"
        det_rows.append([
            Paragraph(str(i), p_cell),
            Paragraph(d, p_cell),
            Paragraph(e["type"], p_cell_b),
            Paragraph(e["description"] or "—", p_cell),
            Paragraph(_money(e["amount"]) if e["amount"] is not None else "—", p_cell_r),
        ])

    elements = [header_band(), Spacer(1, 10), meta, Spacer(1, 14),
                Paragraph("Summary", p_h2), summary_tbl, Spacer(1, 14),
                Paragraph("Detailed Activity", p_h2)]

    if len(det_rows) == 1:
        empty = Table([[Paragraph("No activity found for the selected period.",
                                  ParagraphStyle("empty", parent=p_cell, textColor=MUTED))]],
                      colWidths=[content_w])
        empty.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.6, LINE), ("BACKGROUND", (0, 0), (-1, -1), STRIPE),
            ("TOPPADDING", (0, 0), (-1, -1), 16), ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        elements.append(empty)
    else:
        detail_tbl = Table(
            det_rows,
            colWidths=[content_w * 0.05, content_w * 0.13, content_w * 0.16, content_w * 0.50, content_w * 0.16],
            repeatRows=1,
        )
        dstyle = [
            ("BACKGROUND", (0, 0), (-1, 0), HEADBG),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
            ("BOX", (0, 0), (-1, -1), 0.6, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
        for i in range(1, len(det_rows)):
            if i % 2 == 0:
                dstyle.append(("BACKGROUND", (0, i), (-1, i), STRIPE))
        detail_tbl.setStyle(TableStyle(dstyle))
        elements.append(detail_tbl)

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        y = 12 * mm
        canvas.line(doc_.leftMargin, y + 6, doc_.leftMargin + doc_.width, y + 6)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc_.leftMargin, y,
                          f"{SYSTEM_NAME} — {SYSTEM_TAGLINE}   ·   Developed by {DEVELOPER}")
        canvas.drawRightString(doc_.leftMargin + doc_.width, y, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


class FinanceeAdminSite(admin.AdminSite):
    site_header = f"{SYSTEM_NAME} Administration"
    site_title = f"{SYSTEM_NAME} Admin"
    index_title = SYSTEM_TAGLINE

    # ── Superuser-only access to the entire admin ──
    def has_permission(self, request):
        return bool(
            request.user and request.user.is_active and request.user.is_superuser
        )

    # ── Shared branding context for every admin page ──
    def each_context(self, request):
        ctx = super().each_context(request)
        ctx.update({
            "financee_system_name": SYSTEM_NAME,
            "financee_tagline": SYSTEM_TAGLINE,
            "financee_developer": DEVELOPER,
        })
        return ctx

    # ── Extra URLs ──
    def get_urls(self):
        custom = [
            path(
                "user-activity/",
                self.admin_view(self.user_activity_view),
                name="user_activity",
            ),
            path(
                "user-activity/<int:user_id>/",
                self.admin_view(self.user_activity_detail_view),
                name="user_activity_detail",
            ),
            path(
                "user-activity/<int:user_id>/pdf/",
                self.admin_view(self.user_activity_pdf_view),
                name="user_activity_pdf",
            ),
        ]
        return custom + super().get_urls()

    # ── Custom index with KPIs ──
    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        rows, schema = build_user_activity()

        # Subscription overview: how many client companies are currently
        # blocked (paid-until + grace passed, or manually suspended).
        from tenancy.models import BLOCKED_STATES, Company
        companies = list(Company.objects.filter(is_active=True))
        blocked_companies = sum(
            1 for c in companies if c.subscription_state() in BLOCKED_STATES
        )

        extra_context.update({
            "kpi_total_users": User.objects.count(),
            "kpi_superusers": User.objects.filter(is_superuser=True).count(),
            "kpi_active_users": User.objects.filter(is_active=True).count(),
            "kpi_groups": Group.objects.count(),
            "kpi_total_actions": sum(r["total_actions"] for r in rows),
            "kpi_companies": len(companies),
            "kpi_blocked_companies": blocked_companies,
            "kpi_schema": schema,
        })
        return super().index(request, extra_context)

    # ── User Activity list ──
    def user_activity_view(self, request):
        rows, schema = build_user_activity()
        context = {
            **self.each_context(request),
            "title": "User Activity",
            "rows": rows,
            "schema": schema,
            "total_users": len(rows),
            "total_actions": sum(r["total_actions"] for r in rows),
        }
        return TemplateResponse(request, "admin/user_activity.html", context)

    # ── User Activity detail ──
    def user_activity_detail_view(self, request, user_id):
        try:
            user = User.objects.prefetch_related("groups", "user_permissions").get(pk=user_id)
        except User.DoesNotExist:
            raise Http404("User not found")

        date_from = _parse_date(request.GET.get("from"))
        date_to = _parse_date(request.GET.get("to"))

        rows, schema = build_user_activity()
        row = next((r for r in rows if r["id"] == user_id), None)

        entries, summary, totals = build_detailed_activity(user_id, date_from, date_to)

        # recent admin-log actions for this user
        recent = []
        try:
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT l.action_time, l.object_repr, l.change_message, l.action_flag,
                           COALESCE(c.model, '')
                    FROM django_admin_log l
                    LEFT JOIN django_content_type c ON c.id = l.content_type_id
                    WHERE l.user_id = %s
                    ORDER BY l.action_time DESC
                    LIMIT 25
                """, [user_id])
                for t, repr_, msg, flag, model in cur.fetchall():
                    recent.append({
                        "time": t,
                        "object": repr_,
                        "message": msg,
                        "action": {1: "Added", 2: "Changed", 3: "Deleted"}.get(flag, "—"),
                        "model": model,
                    })
        except Exception:
            pass

        context = {
            **self.each_context(request),
            "title": f"Activity — {user.username}",
            "u": user,
            "row": row,
            "summary": summary,
            "entries": entries,
            "totals": totals,
            "recent_actions": recent,
            "schema": schema,
            "groups": ", ".join(g.name for g in user.groups.all()) or "—",
            "date_from": date_from.isoformat() if date_from else "",
            "date_to": date_to.isoformat() if date_to else "",
        }
        return TemplateResponse(request, "admin/user_activity_detail.html", context)

    # ── User Activity PDF export ──
    def user_activity_pdf_view(self, request, user_id):
        try:
            user = User.objects.prefetch_related("groups").get(pk=user_id)
        except User.DoesNotExist:
            raise Http404("User not found")

        date_from = _parse_date(request.GET.get("from"))
        date_to = _parse_date(request.GET.get("to"))
        entries, summary, totals = build_detailed_activity(user_id, date_from, date_to)
        schema = _app_schema()

        pdf_bytes = _render_activity_pdf(user, entries, summary, totals, date_from, date_to, schema)

        filename = f"{SYSTEM_NAME}_activity_{user.username}.pdf"
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp


# Single shared instance used by the URL conf.
financee_admin_site = FinanceeAdminSite(name="financee_admin")

class FinanceeUserAdmin(UserAdmin):
    """
    Avoid destructive user deletes in a schema-per-tenant system.

    Tenant business tables keep user ids for audit columns across every schema.
    Deactivating a user preserves audit history and avoids cross-schema FK/admin
    collector failures.
    """

    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return super().has_delete_permission(request, obj)
        if hasattr(obj, "membership"):
            return False
        return super().has_delete_permission(request, obj)

    def delete_model(self, request, obj):
        if hasattr(obj, "membership"):
            messages.error(
                request,
                "This user is linked to a company. Deactivate the user instead of deleting it.",
            )
            return
        return super().delete_model(request, obj)


# Register the same models the stock admin exposed (Users & Groups).
financee_admin_site.register(User, FinanceeUserAdmin)
financee_admin_site.register(Group, GroupAdmin)
