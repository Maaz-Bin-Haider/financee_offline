from django.urls import path
from . import views

app_name = "owner_equity"

urlpatterns = [
    path("", views.owner_equity_page, name="owner_equity"),
    path("api/transactions/", views.get_owner_equity, name="get_owner_equity"),
    path("api/equity-accounts/", views.get_equity_accounts, name="get_equity_accounts"),
    path("api/add/", views.add_owner_equity, name="add_owner_equity"),
    path("api/delete/", views.delete_owner_equity, name="delete_owner_equity"),
]
