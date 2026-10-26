from django.urls import path
from .views import purchasing,get_purchase,get_purchase_summary, purchase_serial_check

app_name = "purchase"

urlpatterns = [
    path('purchasing/',purchasing,name="purchasing"),
    path('get-purchase/',get_purchase,name="get_purchase"),
    path('get-purchase-summary/',get_purchase_summary,name="get_purchase_summary"),
    path('check-serials/', purchase_serial_check, name="purchase_serial_check"),
]
