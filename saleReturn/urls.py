from django.urls import path
from .views import createSaleReturn, sale_return_lookup,get_sale_return,get_sale_return_summary

app_name = "saleReturn"

urlpatterns = [
    path('create-sale-return/',createSaleReturn, name="create_sale_return"),
    path('lookup/<str:serial>/',sale_return_lookup,name="sale_return_lookup"),
    path('get-sale-return/',get_sale_return, name="get_sale_return"),
    path('get-sale-return-summary/',get_sale_return_summary, name="get_sale_return_summary"),
]




