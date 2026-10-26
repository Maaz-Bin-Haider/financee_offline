from django.urls import path

from activity import views

app_name = "activity"

urlpatterns = [
    path("", views.team_activity_page, name="page"),
    path("api/year/", views.user_year, name="user_year"),
    path("api/day/", views.user_day, name="user_day"),
    path("api/team/", views.team, name="team"),
    path("api/watch/", views.watch, name="watch"),
    path("record/", views.record_export, name="record"),
]
