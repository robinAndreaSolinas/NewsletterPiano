import base64
import csv
import datetime
import json
import os
import re
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command, CommandError
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from ingestion.models import Analytics as PianoAnalytics, Campaign as PianoCampaign
from mailup import aggregate, models, tasks
from var.lib.mailup import MailUpClient, MailUpException, MailUpAuthException, parse_date, format_filter_date

UTC = datetime.timezone.utc


class FakeMailUp:
    """In-memory MailUp REST API served through httpx.MockTransport."""

    def __init__(self):
        self.lists = [
            {"idList": 1, "Name": "QN Mattina", "Description": "", "listGuid": "g-1", "Company": ""},
            {"idList": 2, "Name": "QN Sera", "Description": "", "listGuid": "g-2", "Company": ""},
            {"idList": 3, "Name": "La Nazione interne", "Description": "", "listGuid": "g-3", "Company": ""},
        ]
        # (message_id, StartDate, Recipient) — Recipient is the per-dispatch count, not a lifetime total
        self.history = {
            1: [(101, "2026-10-30 05:00:00Z", 1000), (102, "2026-10-31 05:00:00Z", 1010),
                (103, "2026-10-31 23:30:00Z", 1020)],
            2: [(201, "2026-10-30 17:00:00Z", 500)],
        }
        self.subjects = {101: "Mattina 30", 102: "Mattina 31", 103: "Mattina 1 nov", 201: "Sera 30"}
        self.stats = {
            101: dict(SendingRecipients=1000, Recipients=1000, Views=400, Clicks=50, Bounces=10, Unsubscriptions=3),
            102: dict(SendingRecipients=1010, Recipients=1000, Views=420, Clicks=60, Bounces=10, Unsubscriptions=2),
            103: dict(SendingRecipients=1020, Recipients=1015, Views=100, Clicks=5, Bounces=5, Unsubscriptions=1),
            201: dict(SendingRecipients=500, Recipients=495, Views=200, Clicks=20, Bounces=5, Unsubscriptions=4),
        }
        self.optins = {
            1: [("2026-10-30 10:00:00Z", None), ("2026-10-30 12:00:00Z", "2026-10-31 08:00:00Z"),
                ("2026-10-31 22:59:59Z", None), ("2026-10-31 23:00:00Z", None)],
            2: [("2026-10-30 09:00:00Z", None)],
        }
        self.recipients = {1: 3, 2: 1, 3: 0}
        self.page_size_limit = None
        self.reject_orderby = False
        self.fail_lists = set()
        self.sendouts = {}
        self.status_once = {}
        self.token_counter = 0
        self.expired_tokens = set()
        self.refuse_client_credentials = False
        self.requests = []

    def _page(self, items, params):
        size = int(params.get("pageSize", 20))
        number = int(params.get("pageNumber", 0))
        if self.page_size_limit:
            size = min(size, self.page_size_limit)
        chunk = items[number * size:(number + 1) * size]
        return {"IsPaginated": True, "Items": chunk, "PageNumber": number, "PageSize": size,
                "Skipped": number * size, "TotalElementsCount": len(items)}

    @staticmethod
    def _filter_range(filterby):
        field = filterby.split()[0]
        start, end = [parse_date(v) for v in re.findall(r"#([^#]+)#", filterby)]
        return field, start, end

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        params = {k: v[0] for k, v in parse_qs(request.url.query.decode()).items()}

        if path == "/Authorization/OAuth/Token":
            body = parse_qs(request.content.decode())
            grant = body.get("grant_type", [""])[0]
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Basic "):
                return httpx.Response(400, json={"error": "invalid_client"})
            try:
                cid, secret = base64.b64decode(auth.split()[1]).decode().split(":", 1)
            except (ValueError, IndexError):
                return httpx.Response(400, json={"error": "invalid_client"})
            if cid != "cid" or secret != "csecret":
                return httpx.Response(400, json={"error": "invalid_client"})
            if grant == "client_credentials" and self.refuse_client_credentials:
                return httpx.Response(400, json={"error": "unsupported_grant_type"})
            if grant == "password" and body.get("password") != ["secret"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            if grant not in ("client_credentials", "password", "refresh_token"):
                return httpx.Response(400, json={"error": "unsupported_grant_type"})
            self.token_counter += 1
            return httpx.Response(200, json={"access_token": f"token-{self.token_counter}",
                                             "refresh_token": f"refresh-{self.token_counter}",
                                             "expires_in": 900})

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] in self.expired_tokens:
            return httpx.Response(401, json={"error": "unauthorized"})

        for key, code in list(self.status_once.items()):
            if key in path:
                del self.status_once[key]
                return httpx.Response(code, text="retry-me")

        console = "/API/v1.1/Rest/ConsoleService.svc/Console"
        stats = "/API/v1.1/Rest/MailStatisticsService.svc"

        if path == f"{console}/User/Lists":
            return httpx.Response(200, json=self._page(self.lists, params))

        if m := re.fullmatch(rf"{console}/List/(\d+)/Email/(\d+)/SendHistory", path):
            total = self.sendouts.get(int(m.group(2)), 1)
            page = self._page([], params)
            page["TotalElementsCount"] = total
            return httpx.Response(200, json=page)

        if m := re.fullmatch(rf"{console}/List/(\d+)/Emails/SendHistory", path):
            list_id = int(m.group(1))
            if list_id in self.fail_lists:
                return httpx.Response(500, text="subscriber@example.com")
            if self.reject_orderby and "orderby" in params:
                return httpx.Response(400, text="orderby not supported")
            items = [{"idMessage": mid, "StartDate": d, "EndDate": d, "Recipient": n, "Sender": "", "Tags": ""}
                     for mid, d, n in self.history.get(list_id, [])]
            reverse = params.get("orderby") == "StartDate desc"
            items.sort(key=lambda i: i["StartDate"], reverse=reverse)
            return httpx.Response(200, json=self._page(items, params))

        if m := re.fullmatch(rf"{console}/List/(\d+)/Emails", path):
            list_id = int(m.group(1))
            if list_id in self.fail_lists:
                return httpx.Response(500, text="subscriber@example.com")
            ids = [row[0] for row in self.history.get(list_id, [])]
            if "filterby" in params:
                ids = [int(params["filterby"].split("==")[1])]
            items = [{"idMessage": message_id, "Subject": self.subjects.get(message_id, ""), "idList": list_id}
                     for message_id in ids]
            return httpx.Response(200, json=self._page(items, params))

        if m := re.fullmatch(rf"{console}/List/(\d+)/Recipients/EmailOptins", path):
            rows = self.optins.get(int(m.group(1)), [])
            if "filterby" in params:
                field, start, end = self._filter_range(params["filterby"])
                idx = 0 if field == "Optin_Date" else 1
                rows = [r for r in rows if r[idx] and start <= parse_date(r[idx]) < end]
            return httpx.Response(200, json=self._page([{"Status": "x"} for _ in rows], params))

        if m := re.fullmatch(rf"{stats}/List/(\d+)/Count/Recipients", path):
            return httpx.Response(200, json=self.recipients.get(int(m.group(1)), 0))

        if m := re.fullmatch(rf"{stats}/Message/(\d+)/List/(Views|Clicks)", path):
            # TotalElementsCount is the unique readers / unique clickers. No recipient address.
            key = m.group(2)
            total = self.stats.get(int(m.group(1)), {}).get(key, 0)
            page = self._page([], params)
            page["TotalElementsCount"] = total
            return httpx.Response(200, json=page)

        if m := re.fullmatch(rf"{stats}/Message/(\d+)/Count/(\w+)", path):
            return httpx.Response(200, json=self.stats.get(int(m.group(1)), {}).get(m.group(2), 0))

        return httpx.Response(404, text=f"not found {path}")

    def client(self, client_secret="csecret", token_store=None, username=None, password=None):
        http = httpx.Client(base_url=MailUpClient.ENDPOINT, transport=httpx.MockTransport(self.handler))
        return MailUpClient("cid", client_secret, username=username, password=password,
                            http_client=http, token_store=token_store)


class ParseDateTest(SimpleTestCase):

    def test_formats(self):
        expected = datetime.datetime(2014, 11, 27, 10, 35, 49, tzinfo=UTC)
        self.assertEqual(parse_date("2014-11-27 10:35:49Z"), expected)
        self.assertEqual(parse_date("2014-11-27T10:35:49Z"), expected)
        self.assertEqual(parse_date("2014-11-27T11:35:49+01:00"), expected)
        self.assertEqual(parse_date("/Date(1417084549000)/"), expected)
        self.assertIsNone(parse_date(""))

    def test_filter_literal_is_utc(self):
        rome = datetime.timezone(datetime.timedelta(hours=1))
        self.assertEqual(format_filter_date(datetime.datetime(2026, 11, 1, tzinfo=rome)), "#2026-10-31 23:00:00Z#")

    def test_guess_site(self):
        self.assertEqual(tasks.guess_site("QN Mattina"), "qn")
        self.assertEqual(tasks.guess_site("La Nazione interne"), "naz")
        self.assertEqual(tasks.guess_site("Resto del Carlino"), "rdc")
        self.assertEqual(tasks.guess_site("Promo"), "qn")


class MailUpClientTest(SimpleTestCase):

    def setUp(self):
        self.fake = FakeMailUp()

    def test_incomplete_credentials(self):
        with self.assertRaises(MailUpAuthException):
            MailUpClient("cid", "")

    def test_wrong_secret(self):
        with self.assertRaises(MailUpAuthException):
            self.fake.client(client_secret="wrong").get_lists()

    def test_password_fallback_when_client_credentials_refused(self):
        self.fake.refuse_client_credentials = True
        lists = self.fake.client(username="m12345", password="secret").get_lists()
        self.assertEqual(len(lists), 3)
        grants = [parse_qs(r.content.decode()).get("grant_type", [""])[0]
                  for r in self.fake.requests if r.url.path.endswith("/Token")]
        self.assertEqual(grants[0], "client_credentials")
        self.assertEqual(grants[1], "password")

    def test_client_credentials_alone_if_refused(self):
        self.fake.refuse_client_credentials = True
        with self.assertRaises(MailUpAuthException):
            self.fake.client().get_lists()

    def test_bearer_and_token_reuse(self):
        client = self.fake.client()
        client.get_lists()
        client.get_lists()
        self.assertEqual(self.fake.token_counter, 1)
        self.assertEqual(self.fake.requests[-1].headers["Authorization"], "Bearer token-1")

    def test_refresh_on_401(self):
        client = self.fake.client()
        client.get_lists()
        self.fake.expired_tokens.add("token-1")
        client.get_lists()
        token_calls = [r for r in self.fake.requests if r.url.path.endswith("/Token")]
        self.assertIn("grant_type=refresh_token", token_calls[-1].content.decode())
        self.assertEqual(self.fake.requests[-1].headers["Authorization"], "Bearer token-2")

    def test_pagination(self):
        self.fake.page_size_limit = 2
        self.assertEqual([i["idList"] for i in self.fake.client().get_lists()], [1, 2, 3])

    def test_send_history_range(self):
        client = self.fake.client()
        history = client.get_send_history(1, datetime.datetime(2026, 10, 31, tzinfo=UTC),
                                          datetime.datetime(2026, 11, 1, tzinfo=UTC))
        self.assertEqual([h["idMessage"] for h in history], [103, 102])
        self.assertEqual(history[0]["StartDate"], datetime.datetime(2026, 10, 31, 23, 30, tzinfo=UTC))

    def test_send_history_without_orderby(self):
        self.fake.reject_orderby = True
        history = self.fake.client().get_send_history(1, datetime.datetime(2026, 10, 31, tzinfo=UTC))
        self.assertEqual(sorted(h["idMessage"] for h in history), [102, 103])

    def test_message_stats(self):
        self.assertEqual(self.fake.client().get_message_stats(101), {
            "sent": 1000, "delivered": 990, "opened": 400, "clicked": 50, "bounced": 10, "unsubscribed": 3,
        })

    def test_count_optins(self):
        client = self.fake.client()
        start = datetime.datetime(2026, 10, 30, tzinfo=UTC)
        end = datetime.datetime(2026, 10, 31, tzinfo=UTC)
        self.assertEqual(client.count_optins(1, start, end), 2)
        self.assertEqual(client.count_optins(1, end, end + datetime.timedelta(days=1), field="Optout_Date"), 1)

    def test_http_error(self):
        self.fake.fail_lists.add(1)
        with self.assertRaises(MailUpException) as caught:
            self.fake.client().get_send_history(1)
        self.assertNotIn("subscriber@example.com", str(caught.exception))
        self.assertIn("500", str(caught.exception))

    def test_retries_rate_limit_then_reads(self):
        self.fake.status_once["/User/Lists"] = 429
        self.assertEqual(len(self.fake.client().get_lists()), 3)

    def test_empty_page(self):
        self.fake.lists = []
        self.assertEqual(self.fake.client().get_lists(), [])

    def test_malformed_count_is_not_zero(self):
        self.fake.stats[101]["Views"] = {"unexpected": True}
        with self.assertRaises(MailUpException):
            self.fake.client().get_message_stats(101)

    def test_missing_total_is_not_zero(self):
        payload = json.loads(Path(__file__).with_name("fixtures").joinpath("malformed_pages.json").read_text())

        def handler(request):
            if request.url.path.endswith("/Token"):
                return httpx.Response(200, json={"access_token": "t", "expires_in": 900, "refresh_token": "r"})
            return httpx.Response(200, json=payload["missing_total"])

        client = MailUpClient("cid", "csecret", http_client=httpx.Client(
            base_url=MailUpClient.ENDPOINT, transport=httpx.MockTransport(handler)))
        client._token_store.set({"access_token": "t", "expires_at": 10**12})
        with self.assertRaises(MailUpException):
            client.count_optins(1, datetime.datetime(2026, 11, 1, tzinfo=UTC), datetime.datetime(2026, 11, 2, tzinfo=UTC))

    def test_recorded_send_history_fixture(self):
        page = json.loads(
            Path(__file__).with_name("fixtures").joinpath("qnmedia_send_history_2026-11-02.json").read_text()
        )
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                first = dict(page)
                first["Items"] = page["Items"][:2]
                first["PageSize"] = 2
                return httpx.Response(200, json=first)
            rest = dict(page)
            rest["Items"] = page["Items"][2:]
            rest["PageNumber"] = 1
            rest["PageSize"] = 2
            return httpx.Response(200, json=rest)

        client = MailUpClient("cid", "csecret", http_client=httpx.Client(
            base_url=MailUpClient.ENDPOINT, transport=httpx.MockTransport(handler)))
        client._token_store.set({"access_token": "t", "expires_at": 10**12})
        history = client.get_send_history(18)
        self.assertEqual(len(history), len(page["Items"]))
        day = datetime.date(2026, 10, 26)
        of_1390 = [item for item in history if item["idMessage"] == 1390 and aggregate.local_day(item["StartDate"]) == day]
        self.assertEqual(aggregate.sum_sent_on(of_1390, day), 3)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    TIME_ZONE="Europe/Rome",
)
class IngestionTest(TestCase):

    def setUp(self):
        cache.clear()
        self.fake = FakeMailUp()
        patcher = patch.object(tasks, "get_client", side_effect=lambda config=None: self.fake.client(
            token_store=tasks.CacheTokenStore()))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ingest_lists(self):
        self.assertEqual(sorted(tasks.ingest_lists()), [1, 2, 3])
        self.assertEqual(models.MailingList.objects.count(), 3)
        qn = models.MailingList.objects.get(list_id=1)
        self.assertEqual((qn.name, qn.site, qn.active, qn.total_active_users, qn.total_users),
                         ("QN Mattina", "qn", True, 3, 0))
        nazione = models.MailingList.objects.get(list_id=3)
        self.assertEqual((nazione.site, nazione.active), ("naz", True))

    def test_lists_follow_remote(self):
        tasks.ingest_lists()
        models.MailingList.objects.filter(list_id=1).update(active=False)
        self.fake.lists = self.fake.lists[:2]
        self.fake.lists[0]["Name"] = "QN Mattina nuova"

        self.assertEqual(sorted(tasks.ingest_lists()), [1, 2])
        qn = models.MailingList.objects.get(list_id=1)
        self.assertEqual((qn.name, qn.active, qn.site), ("QN Mattina nuova", True, "qn"))
        self.assertFalse(models.MailingList.objects.get(list_id=3).active)

    def test_nov4_other_newsletters_are_removed_and_sendings_are_zero(self):
        tasks.ingest_lists()
        ml = models.MailingList.objects.get(list_id=1)
        models.Analytics.objects.create(
            mailing_list=ml, date=datetime.date(2026, 11, 4),
            sent=356662, delivered=356662, opened=14977, clicked=782,
            bounced=12936, subscribed=401002, unsubscribed=365431,
        )
        models.Message.objects.create(
            mailing_list=ml, message_id=1390, subject="Prima dell'Alba",
            sent_at=timezone.now(), sendings=14,
        )
        tasks.ingest_analytics(end="20261030")
        self.assertFalse(models.Analytics.objects.filter(date="2026-11-04", sent=356662).exists())
        self.assertEqual(models.Message.objects.get(message_id=1390).sendings, 0)

    def test_first_close_does_not_store_lifetime_as_a_day(self):
        result = tasks.ingest_analytics(end="20261030")
        self.assertEqual(result["date"], "2026-10-30")
        self.assertEqual(result["failed"], [])
        self.assertFalse(models.Analytics.objects.exists())
        self.assertEqual(models.MetricSnapshot.objects.filter(mailing_list__list_id=1).count(), 3)
        message = models.Message.objects.get(message_id=101)
        self.assertEqual((message.sent, message.delivered, message.bounced), (1000, 990, 10))
        self.assertNotEqual(message.sent, message.delivered)

    def test_second_close_is_the_delta_not_the_lifetime(self):
        tasks.ingest_analytics(end="20261030")
        self.fake.stats[101]["Views"] = 407
        self.fake.stats[101]["Clicks"] = 55
        self.fake.stats[101]["Bounces"] = 12
        tasks.ingest_analytics(end="20261031")

        row = models.Analytics.objects.get(mailing_list__list_id=1, date="2026-10-31")
        self.assertEqual((row.sent, row.opened, row.clicked, row.bounced), (0, 0, 120, 2))
        self.assertEqual(row.delivered, 0)
        self.assertEqual((row.subscribed, row.unsubscribed), (1, 1))
        self.assertIn("SendingRecipients", row.provenance)
        self.assertFalse(models.Analytics.objects.filter(date="2026-10-30").exists())

        sera = models.Analytics.objects.get(mailing_list__list_id=2, date="2026-10-31")
        self.assertEqual((sera.sent, sera.opened, sera.clicked), (0, 0, 20))

    def test_ingest_is_idempotent(self):
        tasks.ingest_analytics(end="20261030")
        self.fake.stats[101]["Views"] = 450
        tasks.ingest_analytics(end="20261031")
        tasks.ingest_analytics(end="20261031")
        self.assertEqual(models.Analytics.objects.filter(mailing_list__list_id=1, date="2026-10-31").count(), 1)
        self.assertEqual(models.Analytics.objects.get(mailing_list__list_id=1, date="2026-10-31").opened, 0)
        self.fake.stats[101]["Views"] = 999
        tasks.ingest_analytics(end="20261031")
        self.assertEqual(models.Analytics.objects.get(mailing_list__list_id=1, date="2026-10-31").opened, 0)
        self.assertEqual(models.Message.objects.get(message_id=101).opened, 0)
        self.assertEqual(models.MetricSnapshot.objects.filter(message_id=101, captured_on="2026-10-31").count(), 1)

    def test_failed_fetch_does_not_write_zeros(self):
        tasks.ingest_lists()
        ml = models.MailingList.objects.get(list_id=1)
        kept = models.Analytics.objects.create(
            mailing_list=ml, date=datetime.date(2026, 11, 1),
            sent=6, opened=1, clicked=0, subscribed=6, unsubscribed=7,
        )
        self.fake.fail_lists.add(1)
        result = tasks.ingest_analytics(end="20261031")
        self.assertIn(1, result["failed"])
        kept.refresh_from_db()
        self.assertEqual((kept.sent, kept.subscribed, kept.unsubscribed), (6, 6, 7))
        self.assertFalse(models.Analytics.objects.filter(mailing_list=ml, date="2026-10-31").exists())

    def test_decreasing_cumulative_does_not_go_negative(self):
        tasks.ingest_analytics(end="20261030")
        self.fake.stats[102]["Views"] = 100
        tasks.ingest_analytics(end="20261031")
        row = models.Analytics.objects.get(mailing_list__list_id=1, date="2026-10-31")
        self.assertEqual(row.opened, 0)
        self.assertGreaterEqual(row.opened, 0)
        self.assertIn("clamped to 0", row.provenance)

    def test_opens_after_the_send_stay_on_the_observation_day(self):
        tasks.ingest_analytics(end="20261030")
        self.fake.stats[101]["Views"] = 1868
        self.fake.stats[101]["Clicks"] = 1850
        tasks.ingest_analytics(end="20261031")
        row = models.Analytics.objects.get(mailing_list__list_id=1, date="2026-10-31")
        self.assertEqual(row.sent, 0)
        self.assertEqual((row.opened, row.clicked), (0, 1915))
        self.assertLessEqual(row.delivered, row.sent)

    def test_screenshot_totals_are_not_written_on_one_day(self):
        tasks.ingest_lists()
        ml = models.MailingList.objects.get(list_id=1)
        models.Analytics.objects.create(
            mailing_list=ml, date=datetime.date(2026, 11, 1), sent=0, subscribed=6, unsubscribed=7,
        )
        models.Analytics.objects.create(
            mailing_list=ml, date=datetime.date(2026, 11, 2), sent=0, subscribed=7, unsubscribed=0,
        )
        models.Analytics.objects.create(
            mailing_list=ml, date=datetime.date(2026, 11, 3), sent=0, subscribed=9, unsubscribed=3,
        )
        self.fake.history[1] = [
            (1390, "2026-11-04 05:01:00Z", 71211),
            (1400, "2026-11-04 23:52:00Z", 400945),
        ]
        self.fake.subjects[1390] = "Prima dell'Alba"
        self.fake.subjects[1400] = "Errore invio"
        self.fake.stats[1390] = dict(
            SendingRecipients=356662, Recipients=356662, Views=14977, Clicks=782, Bounces=12936, Unsubscriptions=0,
        )
        self.fake.stats[1400] = dict(
            SendingRecipients=400945, Recipients=400945, Views=1, Clicks=1, Bounces=15074, Unsubscriptions=0,
        )
        tasks.ingest_analytics(end="20261104")
        self.assertFalse(models.Analytics.objects.filter(date="2026-11-04").exists())
        self.assertFalse(models.Message.objects.filter(message_id=1400).exists())
        self.assertTrue(models.MetricSnapshot.objects.filter(message_id=1390, captured_on="2026-11-04").exists())
        for day, subscribed, unsubscribed in (
            (datetime.date(2026, 11, 1), 6, 7),
            (datetime.date(2026, 11, 2), 7, 0),
            (datetime.date(2026, 11, 3), 9, 3),
        ):
            row = models.Analytics.objects.get(mailing_list=ml, date=day)
            self.assertEqual((row.sent, row.subscribed, row.unsubscribed), (0, subscribed, unsubscribed))
        self.assertFalse(models.Analytics.objects.filter(sent=356662).exists())

    @patch.object(tasks, "default_close_day", return_value=datetime.date(2026, 11, 1))
    def test_default_closes_the_send_day_only(self, _):
        tasks.ingest_lists()
        ml = models.MailingList.objects.get(list_id=1)
        models.Analytics.objects.create(
            mailing_list=ml, date=datetime.date(2026, 10, 30), sent=6, subscribed=6, unsubscribed=7,
        )
        result = tasks.ingest_analytics()
        self.assertEqual(result["date"], "2026-11-01")
        kept = models.Analytics.objects.get(mailing_list=ml, date="2026-10-30")
        self.assertEqual((kept.sent, kept.subscribed, kept.unsubscribed), (6, 6, 7))
        self.assertFalse(models.Analytics.objects.filter(date="2026-11-01").exists())

    def test_excluded_ids_do_not_land_in_the_database(self):
        self.fake.history[1] = [
            (1400, "2026-11-04 23:52:00Z", 400945),
            (1388, "2026-11-04 05:01:00Z", 3),
            (1395, "2026-11-04 05:01:00Z", 1),
            (1398, "2026-11-04 05:01:00Z", 1),
            (1397, "2026-11-04 05:01:00Z", 1),
            (1390, "2026-11-04 05:01:00Z", 35317),
        ]
        for message_id in (1400, 1388, 1395, 1398, 1397, 1390):
            self.fake.subjects[message_id] = f"msg {message_id}"
            self.fake.stats[message_id] = dict(
                SendingRecipients=10, Recipients=10, Views=1, Clicks=1, Bounces=1, Unsubscriptions=0,
            )
        tasks.ingest_lists()
        tasks.ingest_analytics(end="20261104")
        saved = set(
            models.Message.objects.filter(mailing_list__list_id=1).values_list("message_id", flat=True)
        )
        self.assertEqual(saved, {1390, 1397})
        self.assertFalse(
            models.MetricSnapshot.objects.filter(mailing_list__list_id=1)
            .exclude(message_id__in=saved)
            .exists()
        )
        self.assertFalse(models.Analytics.objects.filter(date="2026-11-04").exists())

    def test_daily_sent_is_the_cumulative_delta_without_excluded_messages(self):
        self.fake.history[1] = [
            (1390, "2026-11-09 05:01:00Z", 35317),
            (1400, "2026-11-04 23:52:00Z", 400945),
            (1397, "2026-11-09 05:01:00Z", 1),
        ]
        self.fake.stats[1390] = dict(
            SendingRecipients=177285, Recipients=177285, Views=3000, Clicks=2900, Bounces=400, Unsubscriptions=100,
        )
        self.fake.stats[1400] = dict(
            SendingRecipients=400945, Recipients=400945, Views=1, Clicks=1, Bounces=15074, Unsubscriptions=0,
        )
        self.fake.stats[1397] = dict(
            SendingRecipients=5, Recipients=5, Views=1, Clicks=0, Bounces=0, Unsubscriptions=0,
        )
        tasks.ingest_lists()
        tasks.ingest_analytics(end="20261108")
        self.fake.stats[1390].update(
            SendingRecipients=212602, Views=4024, Clicks=4007, Bounces=838, Unsubscriptions=435,
        )
        self.fake.stats[1400]["SendingRecipients"] = 900000
        tasks.ingest_analytics(end="20261109")
        row = models.Analytics.objects.get(mailing_list__list_id=1, date="2026-11-09")
        self.assertEqual(row.sent, 35317)
        self.assertEqual(row.bounced, 438)
        self.assertEqual(row.delivered, row.sent - row.bounced)
        self.assertNotEqual(row.sent, row.delivered)
        self.assertLess(row.delivered, row.sent)
        self.fake.stats[1390]["SendingRecipients"] = 999999
        tasks.ingest_analytics(end="20261109")
        row.refresh_from_db()
        self.assertEqual(row.sent, 35317)

    def test_skipped_day_is_named_and_not_invented(self):
        tasks.ingest_lists()
        tasks.ingest_analytics(end="20261030")
        tasks.ingest_analytics(end="20261101")
        row = models.Analytics.objects.get(mailing_list__list_id=1, date="2026-11-01")
        self.assertIn("gap since previous snapshot", row.provenance)
        self.assertFalse(models.Analytics.objects.filter(mailing_list__list_id=1, date="2026-10-31").exists())

    def test_start_is_ignored_and_does_not_raise(self):
        result = tasks.ingest_analytics("20261102", "20261101")
        self.assertEqual(result["date"], "2026-11-01")

    def test_command(self):
        out = StringIO()
        with patch("mailup.management.commands.mailup.get_client", side_effect=lambda: self.fake.client()):
            call_command("mailup", "check", stdout=out)
            self.assertIn("3 liste visibili", out.getvalue())
            self.assertIn("QN Sera", out.getvalue())

            call_command("mailup", "analytics", "--start", "20261030", "--end", "20261031", "--sync", stdout=out)
            self.assertFalse(models.Analytics.objects.filter(date="2026-10-30").exists())
            self.assertIn("Deprecato", out.getvalue())

            ml = models.MailingList.objects.get(list_id=1)
            wrong = models.Analytics.objects.create(
                mailing_list=ml, date=datetime.date(2026, 10, 30),
                sent=356662, delivered=356662, opened=14977, clicked=782, bounced=12936,
                subscribed=401002, unsubscribed=365431,
            )
            call_command("mailup", "backfill", "--start", "20261030", "--end", "20261031", "--dry-run", stdout=out)
            wrong.refresh_from_db()
            self.assertEqual((wrong.sent, wrong.subscribed), (356662, 401002))
            self.assertIn("[DRY RUN]", out.getvalue())

        with self.assertRaises(CommandError):
            call_command("mailup", "analytics", "--start", "2026-13-01", "--sync", stdout=out)


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class ApiTest(TestCase):

    def setUp(self):
        user = get_user_model().objects.create_superuser("admin", "a@example.com", "pwd")
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get(user=user).key}")

        piano = PianoCampaign.objects.create(
            campaign_id=557, name="QN Piano", active=True, site_id=557,
            schedule_type="regular", mailing_list_id=10, total_users=99,
        )
        PianoAnalytics.objects.create(
            campaign=piano, date=datetime.date(2026, 10, 30),
            sent=50, opened=10, clicked=2, subscribed=1, unsubscribed=0,
        )

        active = models.MailingList.objects.create(list_id=1, name="QN Mattina", active=True, site="qn", total_users=10)
        inactive = models.MailingList.objects.create(list_id=3, name="Test", active=False, site="qn")
        for day in (30, 31):
            models.Analytics.objects.create(mailing_list=active, date=datetime.date(2026, 10, day), sent=100 + day)
        models.Analytics.objects.create(mailing_list=inactive, date=datetime.date(2026, 10, 30), sent=1)

    def test_requires_auth(self):
        self.assertEqual(APIClient().get("/api/stats").status_code, 401)

    def test_stats_are_on_the_same_route(self):
        data = self.api.get("/api/stats").json()
        self.assertEqual(data["count"], 3)
        sources = {row["source"] for row in data["results"]}
        self.assertEqual(sources, {"piano", "mailup"})
        mailup = next(row for row in data["results"] if row["source"] == "mailup" and row["date"] == "2026-10-31")
        self.assertEqual(mailup, {
            "campaign": "QN Mattina", "date": "2026-10-31", "site": "qn", "source": "mailup",
            "sent": 131, "opened": 0, "clicked": 0, "subscribed": 0, "unsubscribed": 0,
        })
        piano = next(row for row in data["results"] if row["source"] == "piano")
        self.assertEqual((piano["campaign"], piano["site"], piano["sent"]), ("QN Piano", "qn", 50))

    def test_stats_source_filter_and_by_date(self):
        mailup = self.api.get("/api/stats?source=mailup").json()
        self.assertEqual(mailup["count"], 2)
        self.assertTrue(all(row["source"] == "mailup" for row in mailup["results"]))

        piano = self.api.get("/api/stats?source=piano").json()
        self.assertEqual(piano["count"], 1)

        both = self.api.get("/api/stats/20261030").json()
        self.assertEqual({row["source"] for row in both}, {"piano", "mailup"})
        ranged = self.api.get("/api/stats/20261030?to_date=20261031&source=mailup").json()
        self.assertEqual(len(ranged), 2)

    def test_campaigns_are_on_the_same_route(self):
        data = self.api.get("/api/campaign").json()
        self.assertEqual(data["count"], 2)
        by_source = {row["source"]: row for row in data["results"]}
        self.assertEqual(by_source["piano"]["campaign_id"], 557)
        self.assertEqual(by_source["mailup"]["campaign_id"], 1)
        self.assertEqual(by_source["mailup"]["schedule_type"], "regular")

        self.assertEqual(self.api.get("/api/campaign/1").json()["source"], "mailup")
        self.assertEqual(self.api.get("/api/campaign/557").json()["source"], "piano")
        self.assertEqual(self.api.get("/api/mailup/stats").status_code, 404)

    def test_contract_shape_and_types(self):
        stats = self.api.get("/api/stats").json()
        self.assertEqual(set(stats), {"count", "next", "previous", "results"})
        self.assertIsInstance(stats["count"], int)
        row = stats["results"][0]
        self.assertEqual(set(row), {
            "campaign", "date", "site", "source", "sent", "opened", "clicked", "subscribed", "unsubscribed",
        })
        for key in ("sent", "opened", "clicked", "subscribed", "unsubscribed"):
            self.assertIsInstance(row[key], int)
        self.assertIsInstance(row["campaign"], str)
        self.assertIn(row["source"], ("piano", "mailup"))
        self.assertNotIn("provenance", row)
        self.assertNotIn("delivered", row)
        self.assertNotIn("bounced", row)

        by_date = self.api.get("/api/stats/20261030?to_date=20261031").json()
        self.assertIsInstance(by_date, list)
        self.assertTrue(by_date)
        self.assertEqual(set(by_date[0]), set(row))

        campaign = self.api.get("/api/campaign").json()
        self.assertEqual(set(campaign), {"count", "next", "previous", "results"})
        item = campaign["results"][0]
        self.assertEqual(set(item), {
            "campaign_id", "name", "site", "source", "active", "schedule_type",
            "mailing_list_id", "total_users", "total_active_users", "fetched_at",
        })
        self.assertIsInstance(item["campaign_id"], int)
        self.assertIsInstance(item["active"], bool)
        self.assertEqual(self.api.get("/api/stats").status_code, 200)
        self.assertEqual(self.api.get("/api/campaign/99999").status_code, 404)


class AggregateTest(SimpleTestCase):

    def test_empty_day_is_zero_and_missing_recipient_is_unknown(self):
        day = datetime.date(2026, 11, 6)
        self.assertEqual(aggregate.sum_sent_on([], day), 0)
        moment = datetime.datetime(2026, 11, 6, 5, 1, tzinfo=UTC)
        self.assertIsNone(aggregate.sum_sent_on([{"StartDate": moment}], day))
        self.assertEqual(aggregate.sum_sent_on([{"StartDate": moment, "Recipient": 0}], day), 0)

    def _snap(self, **overrides):
        values = {key: 0 for key in aggregate.METRIC_KEYS}
        values.update(overrides)
        return values

    def test_first_snapshot_is_not_a_day(self):
        self.assertIsNone(aggregate.delta_counts(self._snap(opened=1868, clicked=1850), None))

    def test_normal_delta_and_decrease_and_repeat(self):
        previous = self._snap(opened=100, clicked=10, bounced=4, sent=100, delivered=96)
        current = self._snap(opened=110, clicked=10, bounced=1, sent=100, delivered=99)
        first = aggregate.delta_counts(current, previous)
        second = aggregate.delta_counts(current, previous)
        self.assertEqual(first, second)
        self.assertEqual((first["opened"], first["clicked"], first["bounced"]), (10, 0, 0))
        self.assertEqual(first["dropped"]["bounced"], -3)

    def test_homogeneous_recipient_delta(self):
        previous = self._snap(sent=177285, bounced=400, delivered=176885)
        current = self._snap(sent=212602, bounced=838, delivered=211764)
        change = aggregate.delta_counts(current, previous)
        self.assertEqual(change["sent"], 35317)

    def test_platform_rates_from_the_control_totals(self):
        rates = aggregate.platform_rates(212602, 212164, 4024, 4007, 435)
        self.assertEqual(str(rates["open_rate"]), "1.90")
        self.assertEqual(str(rates["click_rate"]), "1.89")
        self.assertEqual(str(rates["unsub_rate"]), "0.21")
        self.assertEqual(str(rates["delivery_rate"]), "99.79")
        self.assertEqual(str(rates["click_to_open"]), "99.58")

    def test_console_aggregate_rates(self):
        # MailUp message screen: Recapitate 247330, Aperture 4657, Clic 4641, Clic totali 7611.
        rates = aggregate.platform_rates(247879, 247330, 4657, 4641, 557)
        self.assertEqual(str(rates["open_rate"]), "1.88")
        self.assertEqual(str(rates["click_rate"]), "1.88")
        self.assertEqual(str(rates["click_to_open"]), "99.66")
        self.assertEqual(str(rates["unsub_rate"]), "0.23")
        totals = aggregate.platform_rates(247879, 247330, 4843, 7611, 557)
        self.assertNotEqual(str(totals["click_rate"]), "1.88")

    def test_fourteen_sends_are_not_multiplied_into_one_day(self):
        sends = []
        for offset in range(14):
            moment = datetime.datetime(2026, 10, 24, 5, 1, tzinfo=UTC) + datetime.timedelta(days=offset)
            sends.append({"StartDate": moment, "idMessage": 1390, "Recipient": 71211})
        day = datetime.date(2026, 11, 6)
        self.assertEqual(aggregate.sum_sent_on(sends, day), 71211)
        self.assertNotEqual(aggregate.sum_sent_on(sends, day), 14 * 71211)
        self.assertIsNone(aggregate.delta_counts(self._snap(opened=1868, clicked=1850, bounced=264), None))

    def test_delivered_never_exceeds_sent(self):
        self.assertEqual(aggregate.delivered_for(71211, 264), 71211 - 264)
        self.assertEqual(aggregate.delivered_for(10, 25), 0)
        self.assertLessEqual(aggregate.delivered_for(10, 25), 10)

    def test_month_and_year_boundary(self):
        start, end = aggregate.day_bounds(datetime.date(2026, 12, 31))
        self.assertEqual(start.date(), datetime.date(2026, 12, 31))
        self.assertEqual(end.year, 2027)
        self.assertEqual(end.month, 1)
        self.assertEqual(end.day, 1)
        self.assertEqual(aggregate.local_day(datetime.datetime(2026, 12, 31, 23, 30, tzinfo=UTC)), datetime.date(2027, 1, 1))

    def test_dst(self):
        spring_start, spring_end = aggregate.day_bounds(datetime.date(2026, 3, 29))
        autumn_start, autumn_end = aggregate.day_bounds(datetime.date(2026, 10, 25))
        # Same-tzinfo subtraction ignores the offset change; compare UTC instants.
        self.assertEqual(int(spring_end.timestamp() - spring_start.timestamp()), 23 * 3600)
        self.assertEqual(int(autumn_end.timestamp() - autumn_start.timestamp()), 25 * 3600)
        late = datetime.datetime(2026, 10, 31, 23, 30, tzinfo=UTC)
        self.assertEqual(aggregate.local_day(late), datetime.date(2026, 11, 1))
        before_send = datetime.datetime(2026, 11, 10, 0, 30, tzinfo=aggregate.ROME)
        after_send = datetime.datetime(2026, 11, 10, 11, 50, tzinfo=aggregate.ROME)
        self.assertEqual(aggregate.close_day(before_send), datetime.date(2026, 11, 9))
        self.assertEqual(aggregate.close_day(after_send), datetime.date(2026, 11, 10))

    def test_csv_control_row_maps_sent_to_recipients(self):
        path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "mailup_1390_sendingreport.csv"
        with path.open(newline="") as handle:
            row = next(csv.DictReader(handle))
        sent = int(row["recipients"])
        delivered = int(row["sent"])
        bounced = int(row["bounce"])
        opened = int(row["opens"])
        clicked = int(row["clicks"])
        unsubscribed = int(row["unsubscribed"])
        self.assertEqual((sent, delivered, bounced, opened, clicked, unsubscribed), (212602, 212164, 438, 4024, 4007, 435))
        self.assertEqual(sent, delivered + bounced)
        self.assertLessEqual(delivered, sent)
        self.assertLessEqual(opened, delivered)
        self.assertLessEqual(clicked, delivered)
        rates = aggregate.platform_rates(sent, delivered, opened, clicked, unsubscribed)
        self.assertEqual(
            (str(rates["open_rate"]), str(rates["click_rate"]), str(rates["unsub_rate"]), str(rates["delivery_rate"]), str(rates["click_to_open"])),
            ("1.90", "1.89", "0.21", "99.79", "99.58"),
        )


@pytest.mark.mailup_live
@unittest.skipUnless(os.environ.get("MAILUP_LIVE") == "1", "set MAILUP_LIVE=1 to call the real MailUp API")
class LiveMailUpTest(SimpleTestCase):
    def test_message_1390_matches_the_platform_or_explains(self):
        evidence = Path("/tmp/mailup_live_evidence")
        evidence.mkdir(exist_ok=True)
        with tasks.get_client() as client:
            counts = client.get_message_stats(1390)
            page = client.call_api(
                f"{client.CONSOLE}/Console/List/18/Email/1390/SendHistory",
                params={"pageSize": 50, "pageNumber": 0},
            )
        redacted = _redact(page)
        (evidence / "message_1390.json").write_text(json.dumps({"counts": counts, "send_history": redacted}, indent=2))
        expected = {"sent": 212602, "delivered": 212164, "bounced": 438, "opened": 4024, "clicked": 4007, "unsubscribed": 435}
        mismatches = {key: (counts.get(key), expected[key]) for key in expected if counts.get(key) != expected[key]}
        self.assertFalse(
            mismatches,
            "1390 non combacia col CSV di controllo. Possibili cause: il cumulativo è cresciuto dopo l'export, "
            "Count/Views è il totale e non gli unici, Count/SendingRecipients non è 'recipients'. "
            f"Differenze {mismatches}. Sendout totali {page.get('TotalElementsCount')}.",
        )
        self.assertEqual(page.get("TotalElementsCount"), 20)


def _redact(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if "email" in key.lower() or "mail" == key.lower():
                out[key] = "[redacted]"
            else:
                out[key] = _redact(item)
        return out
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
