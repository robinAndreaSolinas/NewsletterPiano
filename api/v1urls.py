from django.urls import path, re_path
from rest_framework.routers import DefaultRouter

import url_shorter.views
from . import views
import image.views
from rest_framework.authtoken import views as auth_views

router = DefaultRouter(trailing_slash=False)
router.register('image', image.views.ImageViewSet, basename='image')
router.register('shortener', url_shorter.views.UrlShorterViewSet, basename='shortener')

urlpatterns = router.urls

DATE_PATTERN = r"\d{8}"

urlpatterns += [
    # re_path(
    #     rf"stats(/(?P<from_date>{DATE_PATTERN}))?(/(?P<to_date>{DATE_PATTERN}))?/(all|campaign/(?P<campaign_id>[0-9]+))$",
    #     views.get_stats
    # ),
    # re_path(
    #     rf"stats/aggregate/(?P<from_date>{DATE_PATTERN})(/(?P<to_date>{DATE_PATTERN}))?(/(?P<campaign_id>[0-9]+))?$",
    #     views.get_aggregated_stats,
    # ),
    # path(f"stats/users", views.get_users, name="users"),


    path('token', auth_views.obtain_auth_token)

]