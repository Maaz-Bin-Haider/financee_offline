import json
import logging
import mimetypes
import os
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.urls import reverse
from django.utils.text import get_valid_filename


logger = logging.getLogger(__name__)

DOCUMENT_CONFIG = {
    "sale": {
        "permission": "auth.view_sale",
        "table": "salesinvoices",
        "column": "sales_invoice_id",
    },
    "purchase": {
        "permission": "auth.view_purchase",
        "table": "purchaseinvoices",
        "column": "purchase_invoice_id",
    },
    "sale_return": {
        "permission": "auth.view_sale_return",
        "table": "salesreturns",
        "column": "sales_return_id",
    },
    "purchase_return": {
        "permission": "auth.view_purchase_return",
        "table": "purchasereturns",
        "column": "purchase_return_id",
    },
    "payment": {
        "permission": "auth.view_payment",
        "table": "payments",
        "column": "payment_id",
    },
    "receipt": {
        "permission": "auth.view_receipt",
        "table": "receipts",
        "column": "receipt_id",
    },
    "contra": {
        "permission": "auth.view_contra_entry",
        "table": "contra_entries",
        "column": "contra_id",
    },
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PDF_EXTENSIONS = {".pdf"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_PDF_SIZE = 20 * 1024 * 1024


def parse_json_or_multipart_payload(request):
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        payload = request.POST.get("payload") or "{}"
        return json.loads(payload)
    return json.loads(request.body)


def get_attachment_root():
    return Path(getattr(settings, "PRIVATE_MEDIA_ROOT", settings.BASE_DIR / "media" / "private")) / "document_attachments"


def get_tenant_schema():
    membership = getattr(getattr(connection, "tenant", None), "schema_name", None)
    if membership:
        return membership
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_schema()")
            return cursor.fetchone()[0]
    except Exception:
        return "unknown"


def check_document_type(document_type):
    if document_type not in DOCUMENT_CONFIG:
        raise ValidationError("Unsupported document type.")
    return DOCUMENT_CONFIG[document_type]


def user_can_view_document(user, document_type):
    config = check_document_type(document_type)
    return user.is_authenticated and user.has_perm(config["permission"])


def document_exists(document_type, document_id):
    config = check_document_type(document_type)
    query = f"SELECT 1 FROM {config['table']} WHERE {config['column']} = %s LIMIT 1"
    with connection.cursor() as cursor:
        cursor.execute(query, [document_id])
        return bool(cursor.fetchone())


def validate_upload(uploaded_file, file_kind):
    if not uploaded_file:
        return

    ext = Path(uploaded_file.name).suffix.lower()
    content_type = (uploaded_file.content_type or mimetypes.guess_type(uploaded_file.name)[0] or "").lower()

    if file_kind == "image":
        if ext not in IMAGE_EXTENSIONS or not content_type.startswith("image/"):
            raise ValidationError("Image attachment must be JPG, PNG, WEBP, or GIF.")
        if uploaded_file.size > MAX_IMAGE_SIZE:
            raise ValidationError("Image attachment must be 10 MB or smaller.")
    elif file_kind == "pdf":
        if ext not in PDF_EXTENSIONS or content_type != "application/pdf":
            raise ValidationError("PDF attachment must be a PDF file.")
        if uploaded_file.size > MAX_PDF_SIZE:
            raise ValidationError("PDF attachment must be 20 MB or smaller.")
    else:
        raise ValidationError("Unsupported attachment type.")


def attachments_feature_enabled(request):
    """Per-company feature flag (admin-controlled). No tenant company = enabled."""
    company = getattr(request, "tenant_company", None)
    return company is None or company.feature_enabled("attachments")


def validate_request_attachments(request):
    if not request.FILES:
        return
    if not attachments_feature_enabled(request):
        raise ValidationError("Document attachments are not enabled for your company.")
    if len(request.FILES.getlist("attachment_image")) > 1:
        raise ValidationError("Only one image attachment is allowed.")
    if len(request.FILES.getlist("attachment_pdf")) > 1:
        raise ValidationError("Only one PDF attachment is allowed.")
    validate_upload(request.FILES.get("attachment_image"), "image")
    validate_upload(request.FILES.get("attachment_pdf"), "pdf")


def _storage_path(document_type, document_id, file_kind, uploaded_file):
    tenant_schema = get_tenant_schema()
    ext = Path(uploaded_file.name).suffix.lower()
    filename = f"{file_kind}_{uuid.uuid4().hex}{ext}"
    relative = Path(tenant_schema) / document_type / str(document_id) / filename
    absolute = get_attachment_root() / relative
    return relative.as_posix(), absolute


def _write_upload(uploaded_file, absolute_path):
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    with absolute_path.open("wb") as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)


def _delete_file(storage_path):
    if not storage_path:
        return
    try:
        absolute = (get_attachment_root() / storage_path).resolve()
        root = get_attachment_root().resolve()
        if root in absolute.parents or absolute == root:
            absolute.unlink(missing_ok=True)
    except Exception:
        logger.exception("Unable to delete attachment file %s", storage_path)


def get_attachment_rows(document_type, document_id):
    check_document_type(document_type)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT file_kind, original_name, storage_path, content_type, file_size, uploaded_at
            FROM document_attachments
            WHERE document_type = %s AND document_id = %s
            ORDER BY file_kind
            """,
            [document_type, document_id],
        )
        return cursor.fetchall()


def get_attachment(document_type, document_id, file_kind):
    check_document_type(document_type)
    if file_kind not in {"image", "pdf"}:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT file_kind, original_name, storage_path, content_type, file_size
            FROM document_attachments
            WHERE document_type = %s AND document_id = %s AND file_kind = %s
            """,
            [document_type, document_id, file_kind],
        )
        return cursor.fetchone()


def build_metadata(request, document_type, document_id):
    rows = get_attachment_rows(document_type, document_id)
    attachments = {}
    for file_kind, original_name, storage_path, content_type, file_size, uploaded_at in rows:
        attachments[file_kind] = {
            "file_name": original_name,
            "content_type": content_type,
            "file_size": file_size,
            "uploaded_at": uploaded_at.isoformat() if uploaded_at else None,
            "preview_url": request.build_absolute_uri(
                reverse("attachments:preview", args=[document_type, document_id, file_kind])
            ),
            "download_url": request.build_absolute_uri(
                reverse("attachments:download", args=[document_type, document_id, file_kind])
            ),
        }
    return attachments


def save_document_attachments(request, document_type, document_id):
    check_document_type(document_type)
    if not request.FILES:
        return
    # Defense in depth: views validate first, but never persist files for a
    # company whose attachments feature is switched off in the admin.
    if not attachments_feature_enabled(request):
        return
    if not document_exists(document_type, document_id):
        raise ValidationError("Cannot attach files to a missing document.")

    files = {
        "image": request.FILES.get("attachment_image"),
        "pdf": request.FILES.get("attachment_pdf"),
    }
    files = {kind: file for kind, file in files.items() if file}
    if not files:
        return

    new_paths = []
    old_paths = []
    for file_kind, uploaded_file in files.items():
        validate_upload(uploaded_file, file_kind)
        relative_path, absolute_path = _storage_path(document_type, document_id, file_kind, uploaded_file)
        safe_name = get_valid_filename(uploaded_file.name) or f"{file_kind}"
        _write_upload(uploaded_file, absolute_path)
        new_paths.append(relative_path)

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT storage_path
                    FROM document_attachments
                    WHERE document_type = %s AND document_id = %s AND file_kind = %s
                    """,
                    [document_type, document_id, file_kind],
                )
                existing = cursor.fetchone()
                if existing:
                    old_paths.append(existing[0])
                cursor.execute(
                    """
                    INSERT INTO document_attachments (
                        document_type, document_id, file_kind, original_name,
                        stored_name, storage_path, content_type, file_size, uploaded_by
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (document_type, document_id, file_kind)
                    DO UPDATE SET
                        original_name = EXCLUDED.original_name,
                        stored_name = EXCLUDED.stored_name,
                        storage_path = EXCLUDED.storage_path,
                        content_type = EXCLUDED.content_type,
                        file_size = EXCLUDED.file_size,
                        uploaded_by = EXCLUDED.uploaded_by,
                        uploaded_at = now()
                    """,
                    [
                        document_type,
                        document_id,
                        file_kind,
                        uploaded_file.name,
                        safe_name,
                        relative_path,
                        uploaded_file.content_type or "",
                        uploaded_file.size,
                        getattr(request.user, "id", None),
                    ],
                )

    for path in old_paths:
        if path not in new_paths:
            _delete_file(path)


def delete_document_attachments(document_type, document_id):
    check_document_type(document_type)
    rows = get_attachment_rows(document_type, document_id)
    paths = [row[2] for row in rows]
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM document_attachments WHERE document_type = %s AND document_id = %s",
            [document_type, document_id],
        )
    for path in paths:
        _delete_file(path)

    directory = get_attachment_root() / get_tenant_schema() / document_type / str(document_id)
    try:
        if directory.exists():
            os.rmdir(directory)
    except OSError:
        pass
