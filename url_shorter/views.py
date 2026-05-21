from urllib.parse import urlparse

import httpx
from django.core import validators
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse, response
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from url_shorter.models import UrlShorter


# Create your views here.

def proxy(request, short_slug):
    item = get_object_or_404(UrlShorter, slug=short_slug, is_active=True, )
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
    response['X-Short-URL'] = item.slug

    item.clicks += 1
    item.save()

    return response


def shortener(request):
    if request.method == "POST":
        raw_url = request.POST.get("original_url")
        try:
            validators.URLValidator()(raw_url)
        except validators.ValidationError:
            return JsonResponse({"error": "Invalid URL"}, status=400)
        try:
            item = UrlShorter.objects.create(original_url=raw_url)
        except :
            item = UrlShorter.objects.get(original_url=raw_url)

        return JsonResponse({
            "input_data":{
                "original_url": raw_url,
                "created_at": item.created_at,
            },
            "short_url": request.build_absolute_uri(item.slug),

        })


    else:
        return HttpResponse("Listen to the grumbling of deep space", content_type="text/plain")