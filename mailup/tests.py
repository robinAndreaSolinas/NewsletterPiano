import base64
import datetime
import re
from io import StringIO
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command, CommandError
from django.test import TestCase, SimpleTestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from ingestion.models import Analytics as PianoAnalytics, Campaign as PianoCampaign
from mailup import models, tasks
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
        self.history = {
            1: [(101, "2026-10-30 05:00:00Z"), (102, "2026-10-31 05:00:00Z"), (103, "2026-10-31 23:30:00Z")],
            2: [(201, "2026-10-30 17:00:00Z")],
        }
        self.subjects = {101: "Mattina 30", 102: "Mattina 31", 103: "Mattina 1 nov", 201: "Sera 30"}
        self.stats = {
            101: dict(SendingRecipients=1000, Recipients=990, Views=400, Clicks=50, Bounces=10, Unsubscriptions=3),
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

        console = "/API/v1.1/Rest/ConsoleService.svc/Console"
        stats = "/API/v1.1/Rest/MailStatisticsService.svc"

        if path == f"{console}/User/Lists":
            return httpx.Response(200, json=self._page(self.lists, params))

        if m := re.fullmatch(rf"{console}/List/(\d+)/Emails/SendHistory", path):
            list_id = int(m.group(1))
            if list_id in self.fail_lists:
                return httpx.Response(500, text="boom")
            if self.reject_orderby and "orderby" in params:
                return httpx.Response(400, text="orderby not supported")
            items = [{"idMessage": mid, "StartDate": d, "EndDate": d, "Recipient": 0, "Sender": "", "Tags": ""}
                     for mid, d in self.history.get(list_id, [])]
            reverse = params.get("orderby") == "StartDate desc"
            items.sort(key=lambda i: i["StartDate"], reverse=reverse)
            return httpx.Response(200, json=self._page(items, params))

        if m := re.fullmatch(rf"{console}/List/(\d+)/Emails", path):
            message_id = int(params["filterby"].split("==")[1])
            items = [{"idMessage": message_id, "Subject": self.subjects.get(message_id, ""), "idList": int(m.group(1))}]
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
        with self.assertRaises(MailUpException):
            self.fake.client().get_send_history(1)


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
                         ("QN Mattina", "qn", True, 3, 4))
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

    def test_ingest_analytics(self):
        result = tasks.ingest_analytics("20261030", "20261101")
        self.assertEqual(result["lists"], 3)
        self.assertEqual(result["messages"], 4)
        self.assertEqual(result["analytics"], 9)

        mattina = {a.date: a for a in models.Analytics.objects.filter(mailing_list__list_id=1)}
        d30, d31, n1 = datetime.date(2026, 10, 30), datetime.date(2026, 10, 31), datetime.date(2026, 11, 1)
        self.assertEqual(set(mattina), {d30, d31, n1})

        self.assertEqual((mattina[d30].sent, mattina[d30].opened, mattina[d30].clicked), (1000, 400, 50))
        self.assertEqual((mattina[d31].sent, mattina[n1].sent), (1010, 1020))
        self.assertEqual([mattina[d].subscribed for d in (d30, d31, n1)], [2, 1, 1])
        self.assertEqual([mattina[d].unsubscribed for d in (d30, d31, n1)], [0, 1, 0])

        message = models.Message.objects.get(message_id=103)
        self.assertEqual((message.subject, message.mailing_list.list_id, message.delivered), ("Mattina 1 nov", 1, 1015))

    def test_ingest_is_idempotent(self):
        tasks.ingest_analytics("20261030", "20261101")
        self.fake.stats[101]["Views"] = 450
        tasks.ingest_analytics("20261030", "20261101")
        self.assertEqual(models.Analytics.objects.count(), 9)
        self.assertEqual(models.Message.objects.count(), 4)
        self.assertEqual(models.Analytics.objects.get(mailing_list__list_id=1, date="2026-10-30").opened, 450)
        self.assertEqual(models.Message.objects.get(message_id=101).opened, 450)

    def test_failed_list_keeps_existing_data(self):
        tasks.ingest_analytics("20261030", "20261101")
        self.fake.fail_lists.add(2)
        result = tasks.ingest_analytics("20261030", "20261101")
        self.assertEqual(result["failed_lists"], 1)
        self.assertEqual(models.Analytics.objects.filter(mailing_list__list_id=2).count(), 3)

    @patch.object(tasks, "yesterday", return_value=datetime.date(2026, 11, 1))
    def test_default_range_starts_from_last_stored_day(self, _):
        tasks.ingest_analytics("20261031", "20261031")
        result = tasks.ingest_analytics()
        self.assertEqual((result["start"], result["end"]), ("2026-10-31", "2026-11-01"))

    def test_invalid_range(self):
        with self.assertRaises(ValueError):
            tasks.ingest_analytics("20261102", "20261101")

    def test_command(self):
        out = StringIO()
        with patch("mailup.management.commands.mailup.get_client", side_effect=lambda: self.fake.client()):
            call_command("mailup", "check", stdout=out)
        self.assertIn("3 liste visibili", out.getvalue())
        self.assertIn("QN Sera", out.getvalue())

        call_command("mailup", "analytics", "--start", "20261030", "--end", "20261031", "--sync", stdout=out)
        self.assertEqual(models.Analytics.objects.count(), 6)

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
