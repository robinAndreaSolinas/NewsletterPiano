import json, datetime
from django.conf import settings
from django.http import JsonResponse
from var.lib.pianoESP import ClientESP

# Create your views here.

def index(request):
    with open(settings.SECRET_KEYS, 'r') as f:
        keys = json.load(f)
    keys = keys.get("items", [])

    client = ClientESP(keys[0]["id"], keys[0]["api_key"])
    campaigns = client.get_all_campaigns()

    return JsonResponse(campaigns[0].get_stats(datetime.date.today()))