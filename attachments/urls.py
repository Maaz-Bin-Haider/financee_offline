from django.urls import path

from . import views

app_name = "attachments"

urlpatterns = [
    path("<str:document_type>/<int:document_id>/", views.attachment_metadata, name="metadata"),
    path("<str:document_type>/<int:document_id>/<str:file_kind>/preview/", views.serve_attachment, {"download": False}, name="preview"),
    path("<str:document_type>/<int:document_id>/<str:file_kind>/download/", views.serve_attachment, {"download": True}, name="download"),
]
