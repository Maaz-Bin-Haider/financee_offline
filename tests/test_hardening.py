import json
import os
import unittest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django
from django.http import JsonResponse
from django.test import RequestFactory

django.setup()

from financee.security import required_permissions_for_path
from tenancy.middleware import TenantSchemaMiddleware


class UserStub:
    is_authenticated = True

    def __init__(self, allowed=()):
        self.allowed = set(allowed)

    def has_perm(self, perm):
        return perm in self.allowed


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = TenantSchemaMiddleware(lambda request: None)

    def test_sale_path_requires_sale_permission(self):
        perms, mode = required_permissions_for_path("/sale/get-sale/")
        self.assertEqual(mode, "all")
        self.assertIn("auth.view_sale", perms)

    def test_sales_reports_require_any_report_permission(self):
        perms, mode = required_permissions_for_path("/sales-reports/api/summary/")
        self.assertEqual(mode, "any")
        self.assertIn("auth.can_view_sales_summary", perms)

    def test_tenant_without_membership_is_blocked_from_business_path(self):
        request = self.factory.get("/sale/get-sale/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        request.user = UserStub()
        request.tenant_is_active = False
        response = self.middleware.process_view(request, lambda r: None, (), {})
        self.assertEqual(response.status_code, 403)

    def test_tenant_without_membership_can_reach_admin_path(self):
        request = self.factory.get("/admin/")
        request.user = UserStub()
        request.tenant_is_active = False
        response = self.middleware.process_view(request, lambda r: None, (), {})
        self.assertIsNone(response)

    def test_json_500_response_is_scrubbed(self):
        response = JsonResponse(
            {"error": "relation secret_table does not exist", "details": "SQL details"},
            status=500,
        )
        scrubbed = self.middleware._scrub_error_response(response)
        payload = json.loads(scrubbed.content)
        self.assertEqual(payload, {"status": "error", "message": "An unexpected error occurred."})


if __name__ == "__main__":
    unittest.main()
