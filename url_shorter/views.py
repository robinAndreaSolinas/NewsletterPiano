from django.http import HttpResponseRedirect
from django.urls import reverse
from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from url_shorter.models import UrlShorter
from url_shorter.serializers import UrlShorterSerializer

# Create your views here.


def proxy(request, slug):
    item = get_object_or_404(UrlShorter, slug=slug, is_active=True)
    path = reverse(proxy, kwargs={'slug': item.slug})
    response = HttpResponseRedirect(item.original_url)
    response['Referrer-Policy'] = 'no-referrer'
    response['X-Content-Type-Options'] = 'nosniff'
    response['X-Frame-Options'] = 'DENY'
    response['X-XSS-Protection'] = '1; mode=block'
    response['X-Robots-Tag'] = ['noindex', 'nofollow', 'noarchive', 'nosnippet', 'noimageindex', 'notranslate']
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    response['X-Redirect-By'] = "URL Shortener"
    response['X-Permitted-Cross-Domain-Policies'] = 'none'
    response['X-Redirect-From'] = request.META.get('HTTP_REFERER', '')
    response['X-Redirect-To'] = item.original_url
    response['X-Path'] = path
    response['X-Short-URL'] = request.build_absolute_uri(path)

    item.clicks += 1
    item.save()

    return response

class UrlShorterViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = UrlShorter.objects.order_by("-created_at").all()
    serializer_class = UrlShorterSerializer
    lookup_field = 'slug'
