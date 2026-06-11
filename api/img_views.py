import datetime
from urllib.parse import urlparse

from django.http import JsonResponse

from api.models import Image


def img_view(request, from_date, to_date=None):
    from_date = datetime.datetime.strptime(from_date, "%Y%m%d").date()
    to_date = datetime.datetime.strptime(to_date, "%Y%m%d").date() if to_date else from_date

    imgs = Image.objects.filter(
        published_at__range=(from_date, to_date + datetime.timedelta(days=1)),
    ).values()

    imgs = [
        {**{k: v for k, v in row.items() if k != 'id'}, 'domain': urlparse(row['url']).netloc}
        for row in imgs
    ]

    data = {
        "from": from_date,
        "to": to_date,
        "data": imgs or []
    }

    return JsonResponse(data, status=200 if imgs else 404)