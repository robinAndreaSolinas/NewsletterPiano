import datetime

from django.db.models import Sum, When, Value, CharField, Case
from django.http import JsonResponse
from ingestion.models import Analytics, Campaign


# Create your views here.

C_site_annotation = {"site": Case(
        When(site_id=594, then=Value("gio")),
        When(site_id=595, then=Value("rdc")),
        When(site_id=596, then=Value("naz")),
        When(site_id=808, then=Value("lux")),
        When(site_id=557, then=Value("qn")),
        default=Value("unknown"),
        output_field=CharField(),
)}
A_site_annotation = {"site": Case(
        When(campaign__site_id=594, then=Value("gio")),
        When(campaign__site_id=595, then=Value("rdc")),
        When(campaign__site_id=596, then=Value("naz")),
        When(campaign__site_id=808, then=Value("lux")),
        When(campaign__site_id=557, then=Value("qn")),
        default=Value("unknown"),
        output_field=CharField(),
)}

def index(request):
    return JsonResponse({"message": "Hello world", "status": "success"})


def get_stats(request, from_date: str = None, to_date: str = None, campaign_id = None):
    to_date = datetime.datetime.strptime(to_date, "%Y%m%d").date() if to_date else datetime.date.today()
    from_date = datetime.datetime.strptime(from_date, "%Y%m%d").date() if from_date else to_date

    order = "-date" if request.GET.get('order') == "desc" else "date"

    if from_date > to_date:
        return JsonResponse({"stats": [], "success": False, "error": "from_date cannot be greater than to_date"}, status=400)

    if campaign_id:
        analytics = Analytics.objects.filter(
            campaign__active=True,
            date__range=(from_date, to_date),
            campaign_id=campaign_id
        ).annotate(**A_site_annotation).values("campaign__name", "site", "date", "sent", "opened", "clicked", "subscribed", "unsubscribed").order_by(order)
    else:
        analytics = Analytics.objects.filter(
            campaign__active=True,
            date__range=(from_date, to_date)
        ).annotate(**A_site_annotation).values("campaign__name", "site", "date", "sent", "opened", "clicked", "subscribed", "unsubscribed").order_by(order)

    valid_response = []
    for a in list(analytics):
        items = {}
        for k,v in a.items():
            if k == "campaign__name":
                items["campaign"] = v
            else:
                items[k] = v
        items["date"] = items["date"].strftime("%Y-%m-%d")
        valid_response.append(items)

    if not valid_response:
        return JsonResponse({"stats": [], "success": True}, status=200)

    return JsonResponse({"stats": list(valid_response), "success": True})


def get_aggregated_stats(request, from_date: str, to_date: str = None, campaign_id: int = None, *args, **kwargs):
    _to_date = datetime.datetime.strptime(to_date, "%Y%m%d").date() if to_date else datetime.date.today()
    from_date = datetime.datetime.strptime(from_date, "%Y%m%d").date()

    if from_date > _to_date:
        return JsonResponse({"stats": [], "success": False, "error": f"from_date cannot be greater than {"to_date" if to_date else "today"}"}, status=400)

    try:
        if campaign_id:
            try:
                campaign = Campaign.objects.get(campaign_id=campaign_id)
            except ValueError:
                campaign = Campaign.objects.get(name=campaign_id)

            analytics = Analytics.objects.filter(
                campaign__active=True,
                date__range=(from_date, _to_date),
                campaign = campaign
            ).values("campaign__name").annotate(
                sent=Sum("sent"),
                opened=Sum("opened"),
                clicked=Sum("clicked"),
                subscribed=Sum("subscribed"),
                unsubscribed=Sum("unsubscribed"),
            )
        else:
            analytics = Analytics.objects.filter(
                campaign__active=True,
                date__range=(from_date, _to_date)
            ).values("campaign__name").annotate(
                sent=Sum("sent"),
                opened=Sum("opened"),
                clicked=Sum("clicked"),
                subscribed=Sum("subscribed"),
                unsubscribed=Sum("unsubscribed"),
            )

    except (Analytics.DoesNotExist, Campaign.DoesNotExist):
        return JsonResponse({"stats": [], "success": False, "error": "Campaign not Found"}, status=404)

    valid_response = []
    for a in list(analytics):
        items = {}
        for k,v in a.items():
            if k == "campaign__name":
                items["campaign"] = v
            else:
                items[k] = v
        if items.get("date"):
            items["date"] = items["date"].strftime("%Y-%m-%d")
        valid_response.append(items)

    if not valid_response:
        return JsonResponse({"stats": [], "success": True}, status=200)

    return JsonResponse({"stats": list(valid_response), "success": True})

def get_users(request):
    campaigns = Campaign.objects.annotate(
        **C_site_annotation
    ).values("name", "site", "fetched_at", "total_users", "total_active_users").all()

    users = []
    for c in campaigns:
        users.append({
            "campaign": c["name"],
            "site": c['site'],
            "date": c["fetched_at"].strftime("%Y-%m-%d"),
            "total_users": c["total_users"],
            "active_users": c["total_active_users"]
        })

    return JsonResponse(users, safe=False)