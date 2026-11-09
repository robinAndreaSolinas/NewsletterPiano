"""Pure rules for one MailUp day. No HTTP and no database."""
from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")

COUNT_KEYS = ("opened", "clicked", "bounced")


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


def delta_counts(current: dict, previous: dict | None):
    """Day-over-day growth of lifetime counters.

    None means there is no baseline: the caller must not store zeros.
    A later cumulative that shrinks contributes 0 and is listed in `dropped`.
    """
    if previous is None:
        return None
    dropped = {}
    out = {}
    for key in COUNT_KEYS:
        change = int(current[key]) - int(previous[key])
        if change < 0:
            dropped[key] = change
            change = 0
        out[key] = change
    out["dropped"] = dropped
    return out


def delivered_for(sent: int, bounced: int) -> int:
    """Glossary delivered is sent minus bounces. Never negative.

    Bounces observed today can belong to older dispatches, so this can be 0
    even when mail was sent. That case is recorded by the caller.
    """
    return max(0, int(sent) - int(bounced))
