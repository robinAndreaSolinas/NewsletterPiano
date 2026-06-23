from django.http import HttpResponseRedirect
from django.urls import reverse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

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

@api_view(["POST"])
def url_shortener(request):
    """
    Examples:
        ```
        {
        "url": "http://example.com"
        }
        ```
    """
    serializer = UrlShorterSerializer(data=request.data, context={"request": request})
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data,)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
