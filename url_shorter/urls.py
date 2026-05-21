from django.urls import re_path, path

from url_shorter import views

urlpatterns = [
    re_path(r"$", views.shortener, name="shortener"),
    re_path(r"^(?P<short_slug>.+)$", views.proxy, name="proxy"),
]