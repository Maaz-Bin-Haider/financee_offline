from pathlib import Path

from django.http import FileResponse, Http404, JsonResponse
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError

from .utils import (
    attachments_feature_enabled,
    build_metadata,
    document_exists,
    get_attachment,
    get_attachment_root,
    user_can_view_document,
)


def _ensure_access(request, document_type, document_id):
    if not attachments_feature_enabled(request):
        raise PermissionDenied
    if not user_can_view_document(request.user, document_type):
        raise PermissionDenied
    if not document_exists(document_type, document_id):
        raise Http404("Document not found.")


@login_required
def attachment_metadata(request, document_type, document_id):
    try:
        _ensure_access(request, document_type, document_id)
        return JsonResponse(
            {
                "success": True,
                "attachments": build_metadata(request, document_type, document_id),
            }
        )
    except (ValidationError, PermissionDenied):
        return JsonResponse({"success": False, "message": "Access denied."}, status=403)
    except Http404:
        return JsonResponse({"success": False, "message": "Document not found."}, status=404)


@login_required
def serve_attachment(request, document_type, document_id, file_kind, download=False):
    try:
        _ensure_access(request, document_type, document_id)
        row = get_attachment(document_type, document_id, file_kind)
        if not row:
            raise Http404("Attachment not found.")

        _, original_name, storage_path, content_type, _ = row
        root = get_attachment_root().resolve()
        absolute = (root / Path(storage_path)).resolve()
        if root not in absolute.parents or not absolute.exists():
            raise Http404("Attachment not found.")

        return FileResponse(
            absolute.open("rb"),
            as_attachment=download,
            filename=original_name,
            content_type=content_type or "application/octet-stream",
        )
    except (ValidationError, PermissionDenied):
        return JsonResponse({"success": False, "message": "Access denied."}, status=403)
