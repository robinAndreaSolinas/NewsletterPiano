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
                    # List/{id}/Count/Recipients is the current subscribed count (help: "subscribed recipient").
                    # total_users stays untouched: it is still in the API JSON and is not updated here.
                    ml.total_active_users = client.count_list_recipients(ml.list_id)
                except MailUpException as e:
                    _logger.warning(f"MailUp: unable to count active users of list {ml.list_id}: {e}")
            models.MailingList.objects.bulk_update(active, fields=["total_active_users"])

        _logger.info(f"MailUp: synced {len(bulk_lists)} lists, {len(active)} active")
        return [ml.list_id for ml in active]
    finally:
        connections.close_all()


def excluded_message_ids() -> set[int]:
    raw = settings.MAILUP.get("EXCLUDED_MESSAGE_IDS") or ""
    if isinstance(raw, (list, tuple, set)):
        values = raw
    else:
        values = str(raw).replace(";", ",").split(",")
    ids = set()
    for value in values:
        text = str(value).strip()
        if text:
            ids.add(int(text))
    return ids


def default_close_day(moment: datetime.datetime = None) -> datetime.date:
    moment = moment or timezone.localtime()
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment, timezone.get_current_timezone())
    return aggregate.close_day(moment, aggregate.ROME)


def _snap_dict(snap: models.MetricSnapshot) -> dict:
    return {key: getattr(snap, key) for key in aggregate.METRIC_KEYS}


def _catalog(client: MailUpClient, ml: models.MailingList):
    excluded = excluded_message_ids()
    known = set(models.Message.objects.filter(mailing_list=ml).values_list("message_id", flat=True))
    catalog = []
    for item in client.paginate(f"{client.CONSOLE}/Console/List/{ml.list_id}/Emails"):
        message_id = _get(item, "idMessage")
        if message_id is None:
            continue
        message_id = int(message_id)
        subject = (_get(item, "Subject") or "")[:500]
        created = _get(item, "CreationDate") or ""
        catalog.append((message_id, subject, created))
        _logger.info(f"MailUp: message {message_id} subject={subject!r} created={created}")
        if message_id not in known and message_id not in excluded:
            _logger.warning(
                f"MailUp: message id {message_id} never seen before "
                f"(subject={subject!r}, created={created})"
            )
    return catalog, excluded


def _day_values(ml, day, currents: dict):
    pairs = []
    for message_id, counts in currents.items():
        previous = (
            models.MetricSnapshot.objects
            .filter(mailing_list=ml, message_id=message_id, captured_on__lt=day)
            .order_by("-captured_on")
            .first()
        )
        gap = (day - previous.captured_on).days if previous else None
        pairs.append((message_id, counts, _snap_dict(previous) if previous else None, gap or 0))
    return aggregate.sum_message_deltas(pairs)


# Righe giornaliere ricostruite dopo un'interruzione del job: il job non le riscrive.
RECONSTRUCTED_PREFIX = "RICOSTRUITO"


def close_list(client: MailUpClient, ml: models.MailingList, day: datetime.date, *, dry_run: bool = False):
    """Close one Rome day from cumulative snapshots.

    The first snapshot of a message is stored and does not become the day's value.
    A second run the same day keeps the snapshot already stored, so the row does not
    collapse to zero and does not move if MailUp's cumulative grew later that day.
    A failed fetch writes nothing.
    """
    start, end = day_bounds(day)
    kept = models.Analytics.objects.filter(
        mailing_list=ml, date=day, provenance__startswith=RECONSTRUCTED_PREFIX,
    ).first()
    if kept is not None:
        # Giorno ricostruito a mano (invii esatti da SendHistory): non va sovrascritto né usato come snapshot.
        _logger.info(f"MailUp: list {ml.list_id} {day} is reconstructed, kept as is")
        return {"date": day.isoformat(), "status": "kept", "excluded": [], "warnings": [], "fields": {
            "sent": kept.sent, "delivered": kept.delivered, "opened": kept.opened, "clicked": kept.clicked,
            "bounced": kept.bounced, "subscribed": kept.subscribed, "unsubscribed": kept.unsubscribed,
        }}
    try:
        catalog, excluded = _catalog(client, ml)
        included = [row for row in catalog if row[0] not in excluded]
        excluded_seen = [row[0] for row in catalog if row[0] in excluded]
        for message_id in excluded_seen:
            _logger.info(f"MailUp: message {message_id} excluded")

        preexisting = {}
        missing = []
        for message_id, subject, created in included:
            snap = models.MetricSnapshot.objects.filter(
                mailing_list=ml, message_id=message_id, captured_on=day,
            ).first()
            if snap is not None:
                preexisting[message_id] = _snap_dict(snap)
            else:
                missing.append((message_id, subject, created))

        fetched = {message_id: client.get_message_stats(message_id) for message_id, _subject, _created in missing}
        subscribed = client.count_optins(ml.list_id, start, end)
        unsubscribed = client.count_optins(ml.list_id, start, end, field="Optout_Date")
    except MailUpException as e:
        _logger.error(f"MailUp: list {ml.list_id} {day} not stored, fetch failed: {e}")
        return None

    currents = {**preexisting, **fetched}
    summed = _day_values(ml, day, currents)
    warnings = []
    if summed and summed["dropped"]:
        warnings.append(f"cumulative decreased, clamped to 0: {summed['dropped']}")
        _logger.warning(f"MailUp: list {ml.list_id} {day} {warnings[-1]}")
    if summed and summed["gaps"]:
        warnings.append(f"gap since previous snapshot folded into this day: {summed['gaps']}")
        _logger.warning(f"MailUp: list {ml.list_id} {day} {warnings[-1]}")

    fields = None
    if summed is not None:
        fields = {key: summed[key] for key in aggregate.METRIC_KEYS}
        # Opens are not counted. The API field stays 0. Clicks stay the unique total.
        fields["opened"] = 0
        fields["clicked"] = sum(counts["clicked"] for counts in currents.values())
        fields["subscribed"] = subscribed
        fields["unsubscribed"] = unsubscribed

    result = {
        "date": day.isoformat(),
        "excluded": excluded_seen,
        "warnings": warnings,
        "fields": fields,
    }
    if dry_run:
        result["status"] = "dry-run" if fields else "baseline"
        return result

    now = timezone.now()
    subjects = {message_id: subject for message_id, subject, _created in included}
    for message_id, counts in fetched.items():
        models.MetricSnapshot.objects.create(
            mailing_list=ml, message_id=message_id, captured_on=day, **counts,
        )
        existing = models.Message.objects.filter(message_id=message_id).first()
        defaults = {"mailing_list": ml, "fetched_at": now, **counts}
        if subjects.get(message_id):
            defaults["subject"] = subjects[message_id]
        defaults["opened"] = 0
        defaults["sendings"] = 0
        if existing is None:
            defaults["sent_at"] = start
        models.Message.objects.update_or_create(message_id=message_id, defaults=defaults)

    row = models.Analytics.objects.filter(mailing_list=ml, date=day).first()
    if not fetched and row is not None:
        result["status"] = "unchanged"
        result["fields"] = {
            "sent": row.sent, "delivered": row.delivered, "opened": row.opened, "clicked": row.clicked,
            "bounced": row.bounced, "subscribed": row.subscribed, "unsubscribed": row.unsubscribed,
        }
        return result

    if fields is None:
        _logger.info(
            f"MailUp: list {ml.list_id} {day} baseline stored; "
            "lifetime totals are not written as the day"
        )
        result["status"] = "baseline"
        return result

    note = (
        "sent/bounced/message-unsubscribed=delta of Count/SendingRecipients,Bounces,Unsubscriptions; "
        "opened=0 (opens are not counted); "
        "clicked=unique clickers now (List/Clicks TotalElementsCount); "
        "delivered=delta of (SendingRecipients-Bounces); "
        "analytics subscribed/unsubscribed=EmailOptins Optin_Date/Optout_Date for this Rome day"
    )
    if warnings:
        note += "; " + "; ".join(warnings)
    models.Analytics.objects.update_or_create(
        mailing_list=ml,
        date=day,
        defaults={**fields, "provenance": note, "fetched_at": now},
    )
    _logger.info(
        f"MailUp: list {ml.list_id} {day} sent={fields['sent']} delivered={fields['delivered']} "
        f"opened={fields['opened']}"
    )
    result["status"] = "closed"
    return result


@shared_task
def drop_unrelated_nov4_row():
    """The 4 Nov 2026 row is other newsletters dumped on this list, not this day's send."""
    deleted, _ = models.Analytics.objects.filter(
        date=datetime.date(2026, 11, 4),
        sent=356662,
        delivered=356662,
    ).delete()
    if deleted:
        _logger.info("MailUp: removed 2026-11-04 analytics (other newsletters)")
    models.Analytics.objects.update(opened=0)
    models.Message.objects.update(opened=0, sendings=0)


@shared_task
def ingest_analytics(start=None, end=None, dry_run=False, list_id=None):
    """Close one day. Default is the Rome day whose 06:01 send has already happened.

    `start` is accepted so the existing Celery signature stays valid. It does not
    select a range and it does not delete rows already stored, except the known
    4 Nov 2026 row that belongs to other newsletters.
    """
    try:
        config = get_config()
        day = parse_day(end) or default_close_day()
        if start and parse_day(start) != day:
            _logger.info(f"MailUp: not rewriting {start}..{day}; closing {day} only")

        if not dry_run:
            drop_unrelated_nov4_row()
            ingest_lists()
        active = models.MailingList.objects.filter(active=True)
        if list_id is not None:
            active = active.filter(list_id=int(list_id))
        active = list(active)
        _logger.info(f"MailUp: closing {day} for {len(active)} lists dry_run={dry_run}")

        rows = []
        with get_client(config) as client:
            for ml in active:
                try:
                    result = close_list(client, ml, day, dry_run=dry_run)
                except MailUpException as e:
                    _logger.exception(f"MailUp: list {ml.list_id} failed: {e}")
                    rows.append({"list_id": ml.list_id, "status": "failed"})
                    continue
                if result is None:
                    rows.append({"list_id": ml.list_id, "status": "failed"})
                else:
                    result["list_id"] = ml.list_id
                    rows.append(result)

        failed = [row["list_id"] for row in rows if row.get("status") == "failed"]
        return {"date": day.isoformat(), "rows": rows, "failed": failed, "dry_run": dry_run}
    finally:
        connections.close_all()
