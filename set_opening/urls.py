from django.urls import path
from . import views

app_name = "set_opening"

urlpatterns = [
    path("", views.set_opening_page, name="set_opening"),
    path("api/opening-cash/", views.get_opening_cash, name="get_opening_cash"),
    path("api/opening-cash/set/", views.set_opening_cash, name="set_opening_cash"),
]
