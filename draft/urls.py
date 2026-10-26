from django.urls import path

from .views import (
    cancel_draft,
    convert_draft,
    convert_page,
    delete_draft,
    delete_draft_return,
    draft_page,
    draft_return_lookup,
    draft_return_page,
    draft_return_summary,
    draft_summary,
    get_draft,
    get_draft_return,
    pending_report,
    pending_report_page,
    release_units,
    save_draft,
    save_draft_return,
    serial_lookup,
)

app_name = "draft"

urlpatterns = [
    # ── Screens ───────────────────────────────────────────────────────────
    path('',                draft_page,        name="draft_page"),
    path('convert/screen/', convert_page,      name="convert_page"),
    path('return/screen/',  draft_return_page, name="draft_return_page"),
    path('pending/screen/', pending_report_page, name="pending_report_page"),

    # ── Draft invoice ─────────────────────────────────────────────────────
    path('save/',           save_draft,     name="save_draft"),
    path('delete/',         delete_draft,   name="delete_draft"),
    path('release/',        release_units,  name="release_units"),
    path('cancel/',         cancel_draft,   name="cancel_draft"),
    path('convert/',        convert_draft,  name="convert_draft"),
    path('get/',            get_draft,      name="get_draft"),
    path('summary/',        draft_summary,  name="draft_summary"),
    path('serial/lookup/',  serial_lookup,  name="serial_lookup"),

    # ── Pending drafts report ─────────────────────────────────────────────
    path('pending/',        pending_report, name="pending_report"),

    # ── Confirmed draft return ────────────────────────────────────────────
    path('return/save/',          save_draft_return,    name="save_draft_return"),
    path('return/delete/',        delete_draft_return,  name="delete_draft_return"),
    path('return/get/',           get_draft_return,     name="get_draft_return"),
    path('return/summary/',       draft_return_summary, name="draft_return_summary"),
    path('return/serial/lookup/', draft_return_lookup,  name="draft_return_lookup"),
]
