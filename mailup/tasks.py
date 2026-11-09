import datetime
import json
import logging

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db import connections
from django.utils import timezone

from mailup import aggregate, models
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
    client = MailUpClient(
        config.get("CLIENT_ID"),
        config.get("CLIENT_SECRET"),
        username=config.get("USERNAME"),
        password=config.get("PASSWORD"),
        refresh_token=config.get("REFRESH_TOKEN"),
        token_store=CacheTokenStore(),
    )
    client._retry_sleep = 0.5
    return client


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
    """Europe/Rome midnight of `day` and of the next day."""
    return aggregate.day_bounds(day)


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


def _message_ids(client: MailUpClient, ml: models.MailingList, sendings) -> set[int]:
    ids = set()
    for sending in sendings:
        message_id = _get(sending, "idMessage")
        if message_id is not None:
            ids.add(int(message_id))
    for item in client.paginate(f"{client.CONSOLE}/Console/List/{ml.list_id}/Emails"):
        message_id = _get(item, "idMessage")
        if message_id is not None:
            ids.add(int(message_id))
    ids.update(
        models.MetricSnapshot.objects.filter(mailing_list=ml).values_list("message_id", flat=True)
    )
    return ids


def close_list(client: MailUpClient, ml: models.MailingList, day: datetime.date):
    """Close one local day for one list.

    Does not delete other days. Returns None when a required call fails and writes
    no public row. The first successful close stores the lifetime snapshot only:
    that total is not a day, so Analytics is left untouched.
    """
    start, end = day_bounds(day)
    try:
        sendings = client.get_send_history(ml.list_id, start, end)
        sent = aggregate.sum_sent_on(sendings, day)
        if sent is None:
            _logger.error(f"MailUp: list {ml.list_id} {day} send history has no recipient count; day not stored")
            return None
        message_ids = _message_ids(client, ml, sendings)
        subscribed = client.count_optins(ml.list_id, start, end)
        unsubscribed = client.count_optins(ml.list_id, start, end, field="Optout_Date")
        current = {message_id: client.get_message_stats(message_id) for message_id in message_ids}
    except MailUpException as e:
        _logger.error(f"MailUp: list {ml.list_id} {day} not stored, fetch failed: {e}")
        return None

    now = timezone.now()
    for message_id, counts in current.items():
        models.MetricSnapshot.objects.update_or_create(
            mailing_list=ml,
            message_id=message_id,
            captured_on=day,
            defaults=counts,
        )
        stamps = [s["StartDate"] for s in sendings if int(_get(s, "idMessage") or 0) == message_id]
        try:
            info = client.get_message(ml.list_id, message_id) or {}
        except MailUpException as e:
            _logger.warning(f"MailUp: subject of message {message_id} not updated: {e}")
            info = {}
        existing = models.Message.objects.filter(message_id=message_id).first()
        defaults = {"mailing_list": ml, "fetched_at": now, **counts}
        subject = (_get(info, "Subject") or "")[:500]
        if subject:
            defaults["subject"] = subject
        if stamps:
            defaults["sent_at"] = max(stamps)
            defaults["sendings"] = len(stamps)
        elif existing is None:
            defaults["sent_at"] = start
        models.Message.objects.update_or_create(message_id=message_id, defaults=defaults)

    opened = clicked = bounced = 0
    dropped = {}
    baseline = False
    gaps = []
    for message_id, counts in current.items():
        previous = (
            models.MetricSnapshot.objects
            .filter(mailing_list=ml, message_id=message_id, captured_on__lt=day)
            .order_by("-captured_on")
            .first()
        )
        if previous is None:
            continue
        baseline = True
        gap = (day - previous.captured_on).days
        if gap > 1:
            gaps.append(f"{message_id}:{gap}d")
        change = aggregate.delta_counts(counts, {
            "opened": previous.opened,
            "clicked": previous.clicked,
            "bounced": previous.bounced,
        })
        opened += change["opened"]
        clicked += change["clicked"]
        bounced += change["bounced"]
        for key, value in change["dropped"].items():
            dropped[f"{message_id}.{key}"] = value

    if not baseline:
        _logger.info(
            f"MailUp: list {ml.list_id} {day} baseline stored (sent={sent}); "
            "no daily row, lifetime totals are not a day"
        )
        return {"date": day.isoformat(), "skipped": "no-baseline", "sent": sent}

    delivered = aggregate.delivered_for(sent, bounced)
    note = (
        "sent=SendHistory.Recipient sum by Europe/Rome StartDate; "
        "opened/clicked/bounced=delta of Message Count/Views,Clicks,Bounces vs previous snapshot; "
        "subscribed/unsubscribed=EmailOptins Optin_Date/Optout_Date; "
        f"delivered=max(0, sent-bounced)={delivered}"
    )
    if bounced > sent:
        note += "; bounced today exceeds sends today (bounces of older dispatches)"
    if dropped:
        note += f"; cumulative decreased, clamped to 0: {dropped}"
    if gaps:
        note += f"; gap since previous snapshot folded into this day: {gaps}"

    row, _created = models.Analytics.objects.update_or_create(
        mailing_list=ml,
        date=day,
        defaults={
            "sent": sent,
            "delivered": delivered,
            "opened": opened,
            "clicked": clicked,
            "bounced": bounced,
            "subscribed": subscribed,
            "unsubscribed": unsubscribed,
            "provenance": note,
            "fetched_at": now,
        },
    )
    _logger.info(f"MailUp: list {ml.list_id} {day} sent={sent} opened={opened} clicked={clicked}")
    return {"date": day.isoformat(), "id": row.id, "sent": sent, "opened": opened, "clicked": clicked}


@shared_task
def ingest_analytics(start=None, end=None):
    """Close one day (default: yesterday in Europe/Rome).

    `start` is accepted so the existing Celery signature stays valid. It does not
    select a range and it does not delete rows already stored.
    """
    try:
        config = get_config()
        day = parse_day(end) or yesterday()
        if start and parse_day(start) != day:
            _logger.info(f"MailUp: not rewriting {start}..{day}; closing {day} only")

        ingest_lists()
        active = list(models.MailingList.objects.filter(active=True))
        _logger.info(f"MailUp: closing {day} for {len(active)} lists")

        closed, skipped, failed = [], [], []
        with get_client(config) as client:
            for ml in active:
                try:
                    result = close_list(client, ml, day)
                except MailUpException as e:
                    _logger.exception(f"MailUp: list {ml.list_id} failed: {e}")
                    failed.append(ml.list_id)
                    continue
                if result is None:
                    failed.append(ml.list_id)
                elif result.get("skipped"):
                    skipped.append(ml.list_id)
                else:
                    closed.append(ml.list_id)

        return {
            "date": day.isoformat(),
            "closed": closed,
            "skipped": skipped,
            "failed": failed,
        }
    finally:
        connections.close_all()
