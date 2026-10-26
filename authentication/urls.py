from django.urls import path
from . views import login_view,logout_view,current_user

app_name = "authentication"

urlpatterns = [
    path('login/',login_view,name='login'),
    path('logout/',logout_view,name='logout'),
    path('current/user/',current_user,name="current_user"),
]