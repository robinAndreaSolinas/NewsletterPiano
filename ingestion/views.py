import datetime
import json
from collections import defaultdict
from typing import Iterable
import logging
from django.conf import settings
from scheduler import job
from var.lib import pianoESP as piano
from ingestion import models
from django.utils import timezone


# Create your views here.

__KEYS = json.loads(settings.SECRET_KEYS.read_text())
_logger = logging.getLogger(__name__.split(".")[0])

yesterday = lambda: timezone.now().date() - datetime.timedelta(days=1)

def _get_all_campaigns(only_active=True):
    cp = set()
    for k in __KEYS.get("items", []):
        client = piano.ClientESP(k.get("id"), k.get("api_key"))
        cp |= set(client.get_all_campaigns(only_active))

    return {c
            for c in cp
            if (not only_active or c.active) and c.schedule_type == "regular"
            }


def _get_alluser_campaigns(only_active=True):
    users = {}
    for k in __KEYS.get("items", []):
        client = piano.ClientESP(k.get("id"), k.get("api_key"))
        users.update(
            client.get_all_subscribers(
                client.get_all_mailing_lists(only_active)
            )
        )
    return users


def ingest_campaigns():
    # Recupera tutte le campagne (attive e non)
    all_remote_campaign = {c for c in _get_all_campaigns(only_active=False) if c.schedule_type == "regular"}
    all_users = _get_alluser_campaigns()

    _logger.debug(f"Starting to ingest {len(all_remote_campaign)} remote campaigns")

    bulk_campaigns = []
    for c in all_remote_campaign:
        mailing_list_id = c.get_mailing_list()[0].id if c.get_mailing_list() else None
        if not mailing_list_id:
            continue
        users = all_users.get(str(mailing_list_id), {})

        bulk_campaigns.append(
            models.Campaign(
                campaign_id=c.id,
                site_id=c.site_id,
                name=c.friendly_name,
                active=c.active,  # Passa il valore reale (True o False)
                schedule_type=c.schedule_type,
                mailing_list_id=mailing_list_id,
                total_users=users.get("squad_users", 0),
                total_active_users=users.get("squad_users_active", 0),
                fetched_at=timezone.now(),
            )
        )

    # Esegue l'upsert nel database
    models.Campaign.objects.bulk_create(
        bulk_campaigns,
        update_conflicts=True,
        unique_fields=["campaign_id"],
        update_fields=[
            "site_id",
            "name",
            "mailing_list_id",
            "total_users",
            "total_active_users",
            "fetched_at",
            "active"  # FONDAMENTALE: permette a Django di aggiornare lo stato se cambia in False
        ],
    )

    _logger.info(f"Ingested {len(bulk_campaigns)} campaigns")

    # Mantiene il valore di ritorno originale filtrando solo quelle attive
    active_remote_campaign = tuple(c for c in all_remote_campaign if c.active)
    return active_remote_campaign

def stats_refining(stats, available_groups: Iterable[str] = None):

    def rawrefine(raw):
        if not raw or not isinstance(raw, dict):
            return {}
        refined_stats = defaultdict(dict)
        for grp, type in raw.items():
            if grp not in set(available_groups or ["deliverability", "performance"]):
                continue

            for stat in type.get("total", {}).get("byDate", []):
                key = stat.get("key")
                if not key:
                    continue

                values = {
                    datetime.datetime.fromtimestamp(entry.get("x") // 1000).date(): entry.get("y")
                    for entry in stat.get("values", [])
                    if entry.get("x") is not None
                }

                refined_stats[key] = values

        return dict(refined_stats) if refined_stats else {}

    def reorganize(stats):
        organized_stats = defaultdict(dict)
        for key, values in stats.items():
            for date, value in values.items():
                organized_stats[date][key] = value
        return dict(organized_stats)

    return reorganize(rawrefine(stats))


@job("cron", hour=1)
def ingest_analytics(start:datetime.datetime = None, end:datetime.datetime = None):
    start = start or models.Analytics.objects.order_by("-date").values("date").first().get("date", yesterday())
    end = end or yesterday()
    bulk_analytics = []
    remote_campaigns = ingest_campaigns() ## ingest campaigns before analytics
    exit(124)

    _logger.info(f"Starting to ingest analytics for {len(remote_campaigns)} campaigns")
    _logger.info(f"Analytics range: {start} - {end}")
    _logger.info(f"Deleting existing analytics for {start} - {end}")
    models.Analytics.objects.filter(date__gte=start, date__lte=end).delete()

    for c in remote_campaigns:
        stats = c.get_stats(start, end)
        c_id = models.Campaign.objects.filter(campaign_id=c.id).first().id
        stats = stats_refining(stats)
        mailing_list = c.get_mailing_list()[0]

        # * mailing list stats
        subs_by_date =stats_refining(
            mailing_list.get_stats(start, end),
            available_groups=("mailingListActivity",)
        )

        for date, values in stats.items():
            values.update(subs_by_date.get(date, {}))
            bulk_analytics.append(models.Analytics(
                campaign_id=c_id,
                date=date,
                sent=values.get("sent",0),
                opened=values.get("open",0),
                clicked=values.get("click",0),
                subscribed=values.get("subAdded",0),
                unsubscribed=values.get("subRemoved",0),
            ))

    _logger.info(f"Ingested {len(bulk_analytics)} analytics")
    models.Analytics.objects.bulk_create(bulk_analytics, batch_size=100)