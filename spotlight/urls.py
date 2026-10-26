from django.urls import path
from . import views
app_name = 'spotlight'
urlpatterns = [path('search/', views.search, name='search'), path('resolve/', views.resolve, name='resolve')]
