import datetime
import json
import logging
from collections import defaultdict

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db import transaction, connections
from django.utils import timezone

from mailup import models
from var.lib.mailup import MailUpClient, MailUpException

_logger = logging.getLogger(__name__.split(".")[0])

TOKEN_CACHE_KEY = "mailup:oauth_token"
TOKEN_CACHE_TIMEOUT = 60 * 60 * 24 * 30

yesterday = lambda: timezone.localdate() - datetime.timedelta(days=1)


class CacheTokenStore:
    """Shares the OAuth tokens between web, worker and beat through the Django cache (Redis)."""

    def get(self):
        return cache.get(TOKEN_CACHE_KEY)

    def set(self, token):
        cache.set(TOKEN_CACHE_KEY, token, timeout=TOKEN_CACHE_TIMEOUT)


def get_config() -> dict:
    config = dict(settings.MAILUP)
    try:
        secrets = json.loads(settings.SECRET_KEYS.read_text() or "{}").get("mailup", {})
    except (OSError, ValueError):
        secrets = {}

    for key, value in secrets.items():
        if not config.get(key.upper()):
            config[key.upper()] = value
    return config


def get_client(config: dict = None) -> MailUpClient:
    config = config or get_config()
    return MailUpClient(
        config.get("CLIENT_ID"),
        config.get("CLIENT_SECRET"),
        username=config.get("USERNAME"),
        password=config.get("PASSWORD"),
        refresh_token=config.get("REFRESH_TOKEN"),
        token_store=CacheTokenStore(),
    )


SITE_ALIASES = {
    "quotidiano nazionale": "qn",
    "il resto del carlino": "rdc",
    "la nazione": "naz",
    "il giornale": "gio",
    "carlino": "rdc",
    "nazione": "naz",
    "giornale": "gio",
    "luxury": "lux",
    "gio": "gio",
    "rdc": "rdc",
    "naz": "naz",
    "lux": "lux",
    "qn": "qn",
}


def guess_site(name: str = "", company: str = "") -> str:
    """Derive the newspaper code from the MailUp list name/company; default qn."""
    text = f"{name} {company}".lower()
    for token, code in sorted(SITE_ALIASES.items(), key=lambda item: -len(item[0])):
        if token in text:
            return code
    return "qn"


def parse_day(value) -> datetime.date | None:
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(str(value)[:10], fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date {value!r}: expected YYYYMMDD or YYYY-MM-DD")


def day_bounds(day: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    """Local (TIME_ZONE) midnight of `day` and of the following day, as aware datetimes."""
    start = timezone.make_aware(datetime.datetime.combine(day, datetime.time.min))
    end = timezone.make_aware(datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time.min))
    return start, end


def _get(item: dict, key: str, default=None):
    """MailUp is not consistent with key casing across endpoints (idList / IdList)."""
    lowered = {k.lower(): v for k, v in item.items()}
    return lowered.get(key.lower(), default)


@shared_task
def ingest_lists():
    try:
        config = get_config()

        with get_client(config) as client:
            remote = client.get_lists()
            existing = dict(models.MailingList.objects.values_list("list_id", "id"))
            now = timezone.now()
            remote_ids = set()

            bulk_lists = []
            for item in remote:
                list_id = _get(item, "idList")
                if list_id is None:
                    continue
                list_id = int(list_id)
                remote_ids.add(list_id)
                name = (_get(item, "Name") or "").strip()
                bulk_lists.append(models.MailingList(
                    list_id=list_id,
                    name=name,
                    description=_get(item, "Description") or "",
                    list_guid=_get(item, "listGuid") or "",
                    site=guess_site(name, _get(item, "Company") or ""),
                    active=True,
                    fetched_at=now,
                ))

            models.MailingList.objects.bulk_create(
                [ml for ml in bulk_lists if ml.list_id not in existing]
            )
            models.MailingList.objects.bulk_update(
                [
                    models.MailingList(
                        id=existing[ml.list_id], name=ml.name, description=ml.description, list_guid=ml.list_guid,
                        site=ml.site, active=True, fetched_at=now,
                    )
                    for ml in bulk_lists
                    if ml.list_id in existing
                ],
                fields=["name", "description", "list_guid", "site", "active", "fetched_at"],
            )
            if remote_ids:
                models.MailingList.objects.exclude(list_id__in=remote_ids).update(active=False)

            active = list(models.MailingList.objects.filter(active=True))
            for ml in active:
                try:
                    ml.total_active_users = client.count_list_recipients(ml.list_id)
                    ml.total_users = client.count_all_recipients(ml.list_id)
                except MailUpException as e:
                    _logger.warning(f"MailUp: unable to count users of list {ml.list_id}: {e}")
            models.MailingList.objects.bulk_update(active, fields=["total_users", "total_active_users"])

        _logger.info(f"MailUp: synced {len(bulk_lists)} lists, {len(active)} active")
        return [ml.list_id for ml in active]
    finally:
        connections.close_all()


def _ingest_list(client: MailUpClient, ml: models.MailingList, days: list[datetime.date]):
    range_start, _ = day_bounds(days[0])
    _, range_end = day_bounds(days[-1])

    sendings_by_message = defaultdict(list)
    for sending in client.get_send_history(ml.list_id, range_start, range_end):
        sendings_by_message[int(_get(sending, "idMessage"))].append(sending)

    messages = []
    daily = defaultdict(lambda: defaultdict(int))

    # MailUp statistics are per message and cumulative over all its sendings:
    # the message is dated on its latest sending in range
    for message_id, sendings in sendings_by_message.items():
        sent_at = max(s["StartDate"] for s in sendings)
        stats = client.get_message_stats(message_id)
        info = client.get_message(ml.list_id, message_id) or {}

        messages.append(models.Message(
            mailing_list=ml,
            message_id=message_id,
            subject=(_get(info, "Subject") or "")[:500],
            sent_at=sent_at,
            sendings=len(sendings),
            fetched_at=timezone.now(),
            **stats,
        ))

        day = timezone.localtime(sent_at).date()
        for key, value in stats.items():
            daily[day][key] += value

    analytics = []
    for day in days:
        start, end = day_bounds(day)
        values = daily.get(day, {})

        try:
            subscribed = client.count_optins(ml.list_id, start, end)
            unsubscribed = client.count_optins(ml.list_id, start, end, field="Optout_Date")
        except MailUpException as e:
            _logger.warning(f"MailUp: opt-in/out not available for list {ml.list_id} on {day}: {e}")
            subscribed, unsubscribed = 0, values.get("unsubscribed", 0)

        analytics.append(models.Analytics(
            mailing_list=ml,
            date=day,
            sent=values.get("sent", 0),
            delivered=values.get("delivered", 0),
            opened=values.get("opened", 0),
            clicked=values.get("clicked", 0),
            bounced=values.get("bounced", 0),
            subscribed=subscribed,
            unsubscribed=unsubscribed,
        ))

    return messages, analytics


@shared_task
def ingest_analytics(start=None, end=None):
    try:
        config = get_config()
        end = parse_day(end) or yesterday()
        start = parse_day(start)
        if not start:
            latest = models.Analytics.objects.order_by("-date").values_list("date", flat=True).first()
            start = latest or end
        if start > end:
            raise ValueError(f"start ({start}) is after end ({end})")

        days = [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]

        ingest_lists()
        active = list(models.MailingList.objects.filter(active=True))

        _logger.info(f"MailUp: ingesting analytics for {len(active)} lists, range {start} - {end}")

        bulk_messages, bulk_analytics, done = [], [], []
        with get_client(config) as client:
            for ml in active:
                try:
                    messages, analytics = _ingest_list(client, ml, days)
                except MailUpException as e:
                    _logger.exception(f"MailUp: ingestion failed for list {ml.list_id}: {e}")
                    continue
                bulk_messages += messages
                bulk_analytics += analytics
                done.append(ml.id)

        with transaction.atomic():
            models.Message.objects.bulk_create(
                bulk_messages,
                update_conflicts=True,
                unique_fields=["message_id"],
                update_fields=["mailing_list", "subject", "sent_at", "sendings", "sent", "delivered", "opened",
                               "clicked", "bounced", "unsubscribed", "fetched_at"],
                batch_size=100,
            )

            _logger.info(f"MailUp: deleting existing analytics for {start} - {end}")
            models.Analytics.objects.filter(mailing_list_id__in=done, date__gte=start, date__lte=end).delete()
            models.Analytics.objects.bulk_create(bulk_analytics, batch_size=100)

        _logger.info(f"MailUp: ingested {len(bulk_messages)} messages and {len(bulk_analytics)} analytics")
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "lists": len(done),
            "failed_lists": len(active) - len(done),
            "messages": len(bulk_messages),
            "analytics": len(bulk_analytics),
        }
    finally:
        connections.close_all()
