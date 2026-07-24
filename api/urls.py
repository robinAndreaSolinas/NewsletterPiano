from django.urls import path, re_path
from rest_framework.routers import DefaultRouter

import url_shorter.views
from . import views
import image.views
from rest_framework.authtoken import views as auth_views

router = DefaultRouter(trailing_slash=False)
router.register('image', image.views.ImageViewSet, basename='image')

router.register('stats', views.AnalyticsViewSet, basename='analytics')
router.register('campaign', views.CampaignViewSet, basename='campaign')
router.register('shortener', url_shorter.views.UrlShorterViewSet, basename='shortener')

urlpatterns = router.urls

urlpatterns += [
    path('token', auth_views.obtain_auth_token)
]