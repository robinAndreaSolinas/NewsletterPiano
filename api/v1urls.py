from django.urls import path, re_path

from . import views, img_views

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
    path(f"stats/users", views.get_users, name="users"),

    re_path(rf"table/(?P<from_date>{DATE_PATTERN})(/(?P<to_date>{DATE_PATTERN}))?(/(?P<site>qn|rdc|naz|gio|lux))?$",
            views.visual_table_campaigns, name="table"),

    re_path(f"image/(?P<from_date>{DATE_PATTERN})(/(?P<to_date>{DATE_PATTERN}))?", img_views.img_view, name="image")
]