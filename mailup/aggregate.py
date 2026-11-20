"""Pure rules for one MailUp day. No HTTP and no database."""
from __future__ import annotations

import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")

# Cumulative fields stored on MetricSnapshot. `delivered` is sent - bounced at snapshot time.
METRIC_KEYS = ("sent", "delivered", "opened", "clicked", "bounced", "unsubscribed")
# Newsletter goes out at 06:01 Europe/Rome. A close before 07:00 belongs to the previous day.
SEND_READY = datetime.time(7, 0)


def day_bounds(day: datetime.date, zone: datetime.tzinfo = ROME):
    """Half-open local day [start, end) as aware datetimes.

    Midnight exists on both DST transition days (the overlap and the gap are at 02:00–03:00).
    """
    start = datetime.datetime.combine(day, datetime.time.min, tzinfo=zone)
    end = datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time.min, tzinfo=zone)
    return start, end


def local_day(moment: datetime.datetime, zone: datetime.tzinfo = ROME) -> datetime.date:
    if moment.tzinfo is None:
        raise ValueError("StartDate must be timezone-aware")
    return moment.astimezone(zone).date()


def sending_recipients(item: dict):
    """Per-dispatch recipient count. Missing field is unknown, not zero."""
    if "Recipient" in item and item["Recipient"] is not None:
        return int(item["Recipient"])
    if "Recipients" in item and item["Recipients"] is not None:
        return int(item["Recipients"])
    return None


def sum_sent_on(sendings, day: datetime.date, zone: datetime.tzinfo = ROME):
    """Sum recipient counts of dispatches that started on `day`.

    Returns None if any in-day row has no recipient count (do not pretend it was zero).
    An empty in-day set is a real zero.
    """
    total = 0
    for item in sendings:
        if local_day(item["StartDate"], zone) != day:
            continue
        count = sending_recipients(item)
        if count is None:
            return None
        total += count
    return total


def close_day(moment: datetime.datetime, zone: datetime.tzinfo = ROME) -> datetime.date:
    """Rome date whose 06:01 send is already inside `moment`.

    Before 07:00 the day's newsletter has not gone out yet, so the close belongs to yesterday.
    """
    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    local = moment.astimezone(zone)
    if local.time() < SEND_READY:
        return local.date() - datetime.timedelta(days=1)
    return local.date()


def snapshot_delivered(sent: int, bounced: int) -> int:
    """Cumulative delivered stored on a snapshot: recipients minus bounces, never negative."""
    return max(0, int(sent) - int(bounced))


def delta_counts(current: dict, previous: dict | None):
    """Growth of one message between two cumulative snapshots, on the same fields.

    None means there is no baseline: the caller must not treat the lifetime total as a day.
    A cumulative that shrinks contributes 0 and is listed in `dropped`. The new lower
    value is what the caller stores, so the next day starts from the corrected base.
    """
    if previous is None:
        return None
    dropped = {}
    out = {}
    for key in METRIC_KEYS:
        change = int(current[key]) - int(previous[key])
        if change < 0:
            dropped[key] = change
            change = 0
        out[key] = change
    out["dropped"] = dropped
    return out


def message_day(message_id, current: dict, previous: dict | None, gap_days: int):
    """One message's row for the day: delta of its own cumulative snapshots.

    Returns None without a baseline (first snapshot: the lifetime total is not a day).
    `warnings` names a clamped decrease or a gap folded into this day.
    """
    change = delta_counts(current, previous)
    if change is None:
        return None
    warnings = []
    if change["dropped"]:
        warnings.append(f"cumulative decreased, clamped to 0: {change['dropped']}")
    if gap_days > 1:
        warnings.append(f"gap since previous snapshot folded into this day: {gap_days} days")
    return {"fields": {key: change[key] for key in METRIC_KEYS}, "warnings": warnings}


def platform_rates(sent, delivered, opened, clicked, unsubscribed) -> dict:
    """UI percentages. Denominator of opens, clicks and unsubscribes is delivered (recapitate)."""
    def pct(part, whole):
        if not whole:
            return None
        return (Decimal(part) / Decimal(whole) * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "open_rate": pct(opened, delivered),
        "click_rate": pct(clicked, delivered),
        "unsub_rate": pct(unsubscribed, delivered),
        "delivery_rate": pct(delivered, sent),
        "click_to_open": pct(clicked, opened),
    }


def delivered_for(sent: int, bounced: int) -> int:
    """Glossary delivered is sent minus bounces. Never negative.

    Bounces observed today can belong to older dispatches, so this can be 0
    even when mail was sent. That case is recorded by the caller.
    """
    return max(0, int(sent) - int(bounced))
