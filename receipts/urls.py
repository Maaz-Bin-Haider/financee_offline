from django.urls import path
from .views import make_receipt, get_receipt,get_old_receipts,get_receipts_date_wise,get_party_balance

app_name = "receipts"

urlpatterns = [
    path('receipt/',make_receipt,name="receipt"),
    path("receipt/get/", get_receipt, name="get_receipt"),
    path('get-old-receipts/',get_old_receipts,name="get_old_receipts"),
    path('get-receipts-date-wise/',get_receipts_date_wise,name="get_receipts_date_wise"),
    path('party-balance/', get_party_balance, name="get_party_balance"),
]