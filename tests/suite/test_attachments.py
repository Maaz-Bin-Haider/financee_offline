#!/usr/bin/env python3
"""Document attachments: metadata/file storage, endpoint access, replacement,
cleanup, and attachment-only update behavior across all supported documents.

Run inside the web container:
    docker compose -f deploy/docker-compose.yml exec -e PYTHONPATH=/app web \
        python tests/suite/test_attachments.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402
from tenancy.models import (  # noqa: E402
    Company,
    Membership,
)

GROUP = "attachments"
TAG = f"{time.strftime('%H%M%S')}_{os.getpid()}"
RESULTS = []


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), "" if ok else str(detail)))
    return bool(ok)


def sql(schema, statement, params=None, fetch="one"):
    with connection.cursor() as cursor:
        cursor.execute(f'SET search_path TO "{schema}", public')
        cursor.execute(statement, params or [])
        if fetch == "none":
            return None
        if fetch == "all":
            return cursor.fetchall()
        row = cursor.fetchone()
        return row[0] if row else None


def call_json(schema, statement, params=None):
    value = sql(schema, statement, params)
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value) if value else value


def add_party(schema, user_id, party_type, name):
    payload = {
        "party_name": name,
        "party_type": party_type,
        "opening_balance": 0,
        "balance_type": "Debit",
        "created_by_id": str(user_id),
    }
    sql(schema, "SELECT add_party_from_json(%s::jsonb)", [json.dumps(payload)])
    return name


def add_item(schema, user_id, name):
    payload = {
        "item_name": name,
        "sale_price": 250,
        "storage": "WH",
        "created_by_id": str(user_id),
    }
    sql(schema, "SELECT add_item_from_json(%s::jsonb)", [json.dumps(payload)])
    return name


def party_id(schema, name):
    return sql(schema, "SELECT party_id FROM parties WHERE party_name=%s", [name])


def make_upload(name, content, content_type):
    return SimpleUploadedFile(name, content, content_type=content_type)


def image_upload(name="scan.png", payload=b"image-v1"):
    return make_upload(name, b"\x89PNG\r\n\x1a\n" + payload, "image/png")


def pdf_upload(name="scan.pdf", payload=b"pdf-v1"):
    return make_upload(name, b"%PDF-1.4\n" + payload + b"\n%%EOF\n", "application/pdf")


def post_json_files(client, path, payload, image=None, pdf=None):
    data = {"payload": json.dumps(payload)}
    if image is not None:
        data["attachment_image"] = image
    if pdf is not None:
        data["attachment_pdf"] = pdf
    return client.post(path, data=data)


def rows(schema, document_type, document_id):
    result = sql(
        schema,
        """
        SELECT file_kind, original_name, storage_path, content_type, file_size
        FROM document_attachments
        WHERE document_type=%s AND document_id=%s
        ORDER BY file_kind
        """,
        [document_type, document_id],
        fetch="all",
    )
    return {row[0]: row for row in result}


def storage_path(row):
    return Path(settings.PRIVATE_MEDIA_ROOT) / "document_attachments" / row[2]


def assert_two_files(schema, document_type, document_id, label):
    current = rows(schema, document_type, document_id)
    chk(f"{label}: one image and one PDF metadata row", set(current) == {"image", "pdf"}, current)
    for kind, row in current.items():
        chk(f"{label}: {kind} file exists", storage_path(row).exists(), row[2])
    return current


def latest_id(schema, table, column, description):
    return sql(schema, f"SELECT {column} FROM {table} WHERE description=%s ORDER BY {column} DESC LIMIT 1", [description])


def build_documents(schema, user_id):
    vendor = add_party(schema, user_id, "Vendor", f"ATT VENDOR {TAG} {schema}".upper())
    customer = add_party(schema, user_id, "Customer", f"ATT CUSTOMER {TAG} {schema}".upper())
    both_a = add_party(schema, user_id, "Both", f"ATT BOTH A {TAG} {schema}".upper())
    both_b = add_party(schema, user_id, "Both", f"ATT BOTH B {TAG} {schema}".upper())
    item = add_item(schema, user_id, f"ATT ITEM {TAG} {schema}".upper())

    serials = [f"ATT-{TAG}-{schema}-{i}" for i in range(1, 9)]
    purchase_items = [{
        "item_name": item,
        "qty": len(serials),
        "unit_price": 100,
        "serials": [{"serial": s, "comment": ""} for s in serials],
    }]
    purchase_id = sql(
        schema,
        "SELECT create_purchase(%s,%s,%s::jsonb,%s)",
        [party_id(schema, vendor), "2025-07-01", json.dumps(purchase_items), user_id],
    )
    sale_items = [{"item_name": item, "qty": 4, "unit_price": 160, "serials": serials[:4]}]
    sale_id = sql(
        schema,
        "SELECT create_sale(%s,%s,%s::jsonb,%s)",
        [party_id(schema, customer), "2025-07-02", json.dumps(sale_items), user_id],
    )
    sale_return_id = sql(
        schema,
        "SELECT create_sale_return(%s,%s::jsonb,%s)",
        [customer, json.dumps([serials[0]]), user_id],
    )
    resale_id = sql(
        schema,
        "SELECT create_sale(%s,%s,%s::jsonb,%s)",
        [party_id(schema, customer), "2025-07-03", json.dumps([{"item_name": item, "qty": 1, "unit_price": 165, "serials": [serials[0]]}]), user_id],
    )
    purchase_return_id = sql(
        schema,
        "SELECT create_purchase_return(%s,%s::jsonb,%s)",
        [vendor, json.dumps([serials[4]]), user_id],
    )
    sale_return_date = str(sql(schema, "SELECT return_date FROM salesreturns WHERE sales_return_id=%s", [sale_return_id]))
    purchase_return_date = str(sql(schema, "SELECT return_date FROM purchasereturns WHERE purchase_return_id=%s", [purchase_return_id]))

    payment = call_json(
        schema,
        "SELECT make_payment(%s::jsonb)",
        [json.dumps({"party_name": vendor, "amount": 25, "method": "Cash", "payment_date": "2025-07-04", "description": f"ATT PAYMENT {TAG}", "created_by_id": str(user_id)})],
    )
    receipt = call_json(
        schema,
        "SELECT make_receipt(%s::jsonb)",
        [json.dumps({"party_name": customer, "amount": 20, "method": "Cash", "receipt_date": "2025-07-04", "description": f"ATT RECEIPT {TAG}", "created_by_id": str(user_id)})],
    )
    contra = call_json(
        schema,
        "SELECT make_contra(%s::jsonb)",
        [json.dumps({"from_party_name": both_a, "to_party_name": both_b, "amount": 15, "contra_date": "2025-07-04", "description": f"ATT CONTRA {TAG}", "created_by_id": str(user_id)})],
    )

    sale_delete_id = sql(
        schema,
        "SELECT create_sale(%s,%s,%s::jsonb,%s)",
        [party_id(schema, customer), "2025-07-05", json.dumps([{"item_name": item, "qty": 1, "unit_price": 170, "serials": [serials[5]]}]), user_id],
    )
    payment_delete = call_json(
        schema,
        "SELECT make_payment(%s::jsonb)",
        [json.dumps({"party_name": vendor, "amount": 10, "method": "Cash", "payment_date": "2025-07-05", "description": f"ATT PAYMENT DELETE {TAG}", "created_by_id": str(user_id)})],
    )

    return {
        "vendor": vendor,
        "customer": customer,
        "both_a": both_a,
        "both_b": both_b,
        "item": item,
        "serials": serials,
        "purchase_id": purchase_id,
        "purchase_items": purchase_items,
        "sale_id": sale_id,
        "sale_items": sale_items,
        "sale_return_id": sale_return_id,
        "sale_return_date": sale_return_date,
        "resale_id": resale_id,
        "purchase_return_id": purchase_return_id,
        "purchase_return_date": purchase_return_date,
        "payment_id": payment["payment_id"],
        "receipt_id": receipt["receipt_id"],
        "contra_id": contra["contra_id"],
        "sale_delete_id": sale_delete_id,
        "payment_delete_id": payment_delete["payment_id"],
    }


DOCS = {
    "sale": {
        "path": "/sale/sales/",
        "id_key": "sale_id",
        "payload": lambda d: {
            "action": "submit",
            "sale_id": d["sale_id"],
            "party_name": d["customer"],
            "sale_date": "2025-07-02",
            "sale_type": "credit",
            "description": "",
            "force": True,
            "items": d["sale_items"],
        },
        "attachment_message": "attachments saved",
    },
    "purchase": {
        "path": "/purchase/purchasing/",
        "id_key": "purchase_id",
        "payload": lambda d: {
            "action": "submit",
            "purchase_id": d["purchase_id"],
            "party_name": d["vendor"],
            "purchase_date": "2025-07-01",
            "purchase_type": "credit",
            "description": "",
            "items": d["purchase_items"],
        },
        "attachment_message": "attachments saved",
    },
    "sale_return": {
        "path": "/saleReturn/create-sale-return/",
        "id_key": "sale_return_id",
        "payload": lambda d: {
            "action": "submit",
            "return_id": d["sale_return_id"],
            "party_name": d["customer"],
            "return_date": d["sale_return_date"],
            "description": "",
            "serials": [d["serials"][0]],
        },
        "attachment_message": "attachments saved",
    },
    "purchase_return": {
        "path": "/purchaseReturn/create-purchase-return/",
        "id_key": "purchase_return_id",
        "payload": lambda d: {
            "action": "submit",
            "return_id": d["purchase_return_id"],
            "party_name": d["vendor"],
            "return_date": d["purchase_return_date"],
            "description": "",
            "serials": [d["serials"][4]],
        },
        "attachment_message": "attachments saved",
    },
}


FORM_DOCS = {
    "payment": {
        "path": "/payments/payment/",
        "id_key": "payment_id",
        "payload": lambda d: {
            "action": "submit",
            "current_id": d["payment_id"],
            "payment_date": "2025-07-04",
            "search_name": d["vendor"],
            "amount": "25",
            "description": f"ATT PAYMENT UPDATE {TAG}",
        },
        "bad_payload": lambda d: {
            "action": "submit",
            "current_id": d["payment_id"],
            "payment_date": "2025-07-04",
            "search_name": d["vendor"],
            "amount": "0",
            "description": "bad",
        },
    },
    "receipt": {
        "path": "/receipts/receipt/",
        "id_key": "receipt_id",
        "payload": lambda d: {
            "action": "submit",
            "current_id": d["receipt_id"],
            "receipt_date": "2025-07-04",
            "search_name": d["customer"],
            "amount": "20",
            "description": f"ATT RECEIPT UPDATE {TAG}",
        },
        "bad_payload": lambda d: {
            "action": "submit",
            "current_id": d["receipt_id"],
            "receipt_date": "2025-07-04",
            "search_name": d["customer"],
            "amount": "0",
            "description": "bad",
        },
    },
    "contra": {
        "path": "/contra/contra/",
        "id_key": "contra_id",
        "payload": lambda d: {
            "action": "submit",
            "current_id": d["contra_id"],
            "contra_date": "2025-07-04",
            "from_search_name": d["both_a"],
            "to_search_name": d["both_b"],
            "amount": "15",
            "description": f"ATT CONTRA UPDATE {TAG}",
        },
        "bad_payload": lambda d: {
            "action": "submit",
            "current_id": d["contra_id"],
            "contra_date": "2025-07-04",
            "from_search_name": d["both_a"],
            "to_search_name": d["both_b"],
            "amount": "0",
            "description": "bad",
        },
    },
}


def post_form_files(client, path, payload, image=None, pdf=None):
    data = dict(payload)
    if image is not None:
        data["attachment_image"] = image
    if pdf is not None:
        data["attachment_pdf"] = pdf
    return client.post(path, data=data, follow=False)


def exercise_json_document(client, schema, doc_type, cfg, docs):
    doc_id = docs[cfg["id_key"]]
    payload = cfg["payload"](docs)
    response = post_json_files(client, cfg["path"], payload, image_upload(), pdf_upload())
    body = response.json()
    chk(f"{doc_type}: update upload succeeds", response.status_code == 200 and body.get("success"), body)
    if doc_type in {"sale", "purchase", "sale_return", "purchase_return"}:
        chk(f"{doc_type}: attachment-only update bypass used", cfg["attachment_message"] in body.get("message", "").lower(), body)

    before = assert_two_files(schema, doc_type, doc_id, doc_type)
    old_image_path = storage_path(before["image"])
    old_pdf_path = storage_path(before["pdf"])

    response = post_json_files(client, cfg["path"], payload, image_upload("replacement.png", b"image-v2"))
    body = response.json()
    chk(f"{doc_type}: image replacement succeeds", response.status_code == 200 and body.get("success"), body)
    after = assert_two_files(schema, doc_type, doc_id, f"{doc_type} replacement")
    chk(f"{doc_type}: PDF metadata preserved when only image uploaded", after["pdf"][2] == before["pdf"][2], after)
    chk(f"{doc_type}: old PDF file still exists", old_pdf_path.exists(), old_pdf_path)
    chk(f"{doc_type}: image storage path replaced", after["image"][2] != before["image"][2], after)
    chk(f"{doc_type}: old image file removed", not old_image_path.exists(), old_image_path)


def exercise_form_document(client, schema, doc_type, cfg, docs):
    doc_id = docs[cfg["id_key"]]
    response = post_form_files(client, cfg["path"], cfg["payload"](docs), image_upload(), pdf_upload())
    chk(f"{doc_type}: update upload redirects after success", response.status_code == 302, response.status_code)
    before = assert_two_files(schema, doc_type, doc_id, doc_type)
    old_image_path = storage_path(before["image"])

    response = post_form_files(client, cfg["path"], cfg["payload"](docs), image_upload("replacement.png", b"image-v2"))
    chk(f"{doc_type}: image replacement redirects after success", response.status_code == 302, response.status_code)
    after = assert_two_files(schema, doc_type, doc_id, f"{doc_type} replacement")
    chk(f"{doc_type}: PDF preserved on image-only update", after["pdf"][2] == before["pdf"][2], after)
    chk(f"{doc_type}: old image removed on replacement", not old_image_path.exists(), old_image_path)

    bad_id = doc_id
    before_bad = rows(schema, doc_type, bad_id)
    response = post_form_files(client, cfg["path"], cfg["bad_payload"](docs), image_upload("bad.png", b"bad"))
    chk(f"{doc_type}: invalid update is not bypassed", response.status_code == 200, response.status_code)
    after_bad = rows(schema, doc_type, bad_id)
    chk(f"{doc_type}: invalid update did not save files", after_bad == before_bad, after_bad)


def exercise_endpoints(client, schema, docs):
    doc_id = docs["sale_id"]
    response = client.get(f"/attachments/sale/{doc_id}/")
    body = response.json()
    chk("metadata endpoint returns both attachments", response.status_code == 200 and set(body.get("attachments", {})) == {"image", "pdf"}, body)

    response = client.get(f"/attachments/sale/{doc_id}/image/preview/")
    content = b"".join(getattr(response, "streaming_content", []))
    chk("preview endpoint streams image bytes", response.status_code == 200 and content.startswith(b"\x89PNG"), response.status_code)

    response = client.get(f"/attachments/sale/{doc_id}/pdf/download/")
    content = b"".join(getattr(response, "streaming_content", []))
    disposition = response.headers.get("Content-Disposition", "")
    chk("download endpoint streams PDF as attachment", response.status_code == 200 and content.startswith(b"%PDF") and "attachment" in disposition, disposition)

    allowed = [h for h in (settings.ALLOWED_HOSTS or []) if h not in ("*", "")]
    server = allowed[0].lstrip(".") if allowed else "localhost"
    anon = Client(SERVER_NAME=server)
    response = anon.get(f"/attachments/sale/{doc_id}/")
    chk("metadata endpoint requires authentication", response.status_code == 302, response.status_code)

    response = client.get("/attachments/unknown/1/")
    chk("unsupported document type is denied", response.status_code == 403, response.status_code)
    response = client.get("/attachments/sale/999999999/")
    chk("missing document metadata is 404", response.status_code == 404, response.status_code)


def exercise_validation(client, schema, docs):
    payload = DOCS["sale"]["payload"](docs)
    response = post_json_files(client, DOCS["sale"]["path"], payload, image=make_upload("bad.txt", b"not image", "text/plain"))
    body = response.json()
    chk("invalid image type is rejected", response.status_code == 200 and not body.get("success") and "image attachment" in body.get("message", "").lower(), body)

    large = b"0" * (10 * 1024 * 1024 + 1)
    response = post_json_files(client, DOCS["sale"]["path"], payload, image=make_upload("large.png", large, "image/png"))
    body = response.json()
    chk("oversize image is rejected", response.status_code == 200 and not body.get("success") and "10 mb" in body.get("message", "").lower(), body)


def exercise_cleanup(client, schema, docs):
    payment_id = docs["payment_delete_id"]
    payload = {
        "action": "submit",
        "current_id": payment_id,
        "payment_date": "2025-07-05",
        "search_name": docs["vendor"],
        "amount": "10",
        "description": f"ATT PAYMENT DELETE UPDATE {TAG}",
    }
    response = post_form_files(client, "/payments/payment/", payload, image_upload(), pdf_upload())
    chk("delete fixture payment received attachments", response.status_code == 302, response.status_code)
    payment_paths = [storage_path(row) for row in rows(schema, "payment", payment_id).values()]
    response = client.post("/payments/payment/", data={"action": "delete", "current_id": payment_id}, follow=False)
    chk("successful document delete redirects", response.status_code == 302, response.status_code)
    chk("successful delete removes attachment metadata", rows(schema, "payment", payment_id) == {}, rows(schema, "payment", payment_id))
    chk("successful delete removes physical files", all(not path.exists() for path in payment_paths), payment_paths)

    sale_id = docs["sale_id"]
    sale_before = rows(schema, "sale", sale_id)
    sale_paths = [storage_path(row) for row in sale_before.values()]
    response = post_json_files(client, "/sale/sales/", {"action": "delete", "sale_id": sale_id})
    body = response.json()
    chk("failed business delete is reported", response.status_code == 200 and not body.get("success"), body)
    chk("failed delete preserves metadata", rows(schema, "sale", sale_id) == sale_before, rows(schema, "sale", sale_id))
    chk("failed delete preserves files", all(path.exists() for path in sale_paths), sale_paths)


def run_for_company(user, company, original_membership):
    Membership.objects.update_or_create(user=user, defaults={"company": company})
    # A company may start without attachments or some document screens (the
    # new-company default plan); switch everything on for the run and restore
    # its own switches afterwards.
    features_snapshot = list(Company.objects.get(pk=company.pk).disabled_features or [])
    Company.objects.filter(pk=company.pk).update(disabled_features=[])
    connection.close()

    server = "localhost"
    allowed = [h for h in (settings.ALLOWED_HOSTS or []) if h not in ("*", "")]
    if allowed:
        server = allowed[0].lstrip(".")
    client = Client(SERVER_NAME=server)
    client.force_login(user)

    try:
        docs = build_documents(company.schema_name, user.id)
        for doc_type, cfg in DOCS.items():
            exercise_json_document(client, company.schema_name, doc_type, cfg, docs)
        for doc_type, cfg in FORM_DOCS.items():
            exercise_form_document(client, company.schema_name, doc_type, cfg, docs)
        exercise_endpoints(client, company.schema_name, docs)
        exercise_validation(client, company.schema_name, docs)
        exercise_cleanup(client, company.schema_name, docs)
    finally:
        connection.close()
        Company.objects.filter(pk=company.pk).update(disabled_features=features_snapshot)
        if original_membership is not None:
            Membership.objects.update_or_create(user=user, defaults={"company": original_membership.company})
        else:
            Membership.objects.filter(user=user).delete()


def main():
    User = get_user_model()
    user = User.objects.filter(is_superuser=True).first()
    if user is None:
        chk("a superuser exists", False, "no superuser to drive attachment tests")
        return report()

    # All registered companies are serial-only; the legacy column is unmapped.
    companies = list(Company.objects.filter(
        is_active=True,
        schema_name__isnull=False,
    ).order_by("id"))
    if not companies:
        chk("an active company exists", False, "no active tenant companies")
        return report()

    original_root = getattr(settings, "PRIVATE_MEDIA_ROOT", settings.BASE_DIR / "media" / "private")
    temp_root = tempfile.mkdtemp(prefix="financee-attachments-test-")
    settings.PRIVATE_MEDIA_ROOT = Path(temp_root) / "private"
    try:
        try:
            original_membership = user.membership
        except Membership.DoesNotExist:
            original_membership = None
        for company in companies:
            chk(f"{company.schema_name}: document_attachments table exists", bool(sql(company.schema_name, "SELECT to_regclass('document_attachments')")))
            try:
                run_for_company(user, company, original_membership)
            except Exception as exc:
                import traceback
                chk(
                    f"{company.schema_name}: attachment module completed",
                    False,
                    f"{type(exc).__name__}: {exc} | {traceback.format_exc().splitlines()[-3:]}",
                )
    finally:
        connection.close()
        settings.PRIVATE_MEDIA_ROOT = original_root
        shutil.rmtree(temp_root, ignore_errors=True)

    return report()


def report():
    print("\n" + "=" * 78)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"{passed}/{len(RESULTS)} attachment checks passed")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  [FAIL] {name} - {detail}")
    print("=" * 78)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
