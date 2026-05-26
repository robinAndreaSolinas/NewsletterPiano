from django.urls import path, re_path

from . import views

DATE_PATTERN = r"\d{8}"

urlpatterns = [
    path('', views.index),
    re_path(
        rf"stats(/(?P<from_date>{DATE_PATTERN}))?(/(?P<to_date>{DATE_PATTERN}))?/(all|campaign/(?P<campaign_id>[0-9]+))$",
        views.get_stats
    ),
    re_path(
        rf"stats/aggregate/(?P<from_date>{DATE_PATTERN})(/(?P<to_date>{DATE_PATTERN}))?(/(?P<campaign_id>[0-9]+))?$",
        views.get_aggregated_stats
    ),
    path(f"stats/users", views.get_users, name="users")
]