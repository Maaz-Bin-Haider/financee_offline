from django.urls import path
from .views import sales,get_sale,get_sale_summary,sale_lookup_serial,sale_bulk_serial_lookup

app_name = "sale"

urlpatterns = [
    path('sales/',sales,name="sales"),
    path('get-sale/',get_sale,name="get_sale"),
    path('get-sale-summary/',get_sale_summary,name="get_sale_summary"),
    # New endpoints (no schema change — only Django-side additions)
    path('lookup/<str:serial>/', sale_lookup_serial, name="sale_lookup_serial"),
    path('bulk-lookup/', sale_bulk_serial_lookup, name="sale_bulk_serial_lookup"),
]