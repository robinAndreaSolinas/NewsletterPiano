import json
from django.conf import settings
from django.http import JsonResponse
import datetime
from var.lib.pianoESP import ClientESP
from ingestion.models import Analytics, Campaign

# Create your views here.

def index(request):
    with open(settings.SECRET_KEYS, 'r') as f:
        keys = json.load(f)
    keys = keys.get("items", [])

    client = ClientESP(keys[0]["id"], keys[0]["api_key"])
    campaigns = client.get_all_campaigns()

    an = Analytics.objects.all()
    cp = Campaign.objects.filter(active=True).all()
    print(list(c for c in cp))
    print(list(c for c in an))

    return JsonResponse({"status": "ok", "data": campaigns[0].get_stats(datetime.date.today())})