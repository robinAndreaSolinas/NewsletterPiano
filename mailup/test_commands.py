import datetime
import os
import subprocess
import sys
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.test import TestCase
from django.utils import timezone

from mailup import models, tasks
from mailup.tests import FakeMailUp


class CommandBehaviorTest(TestCase):
    def setUp(self):
        self.fake = FakeMailUp()
        patcher = patch("mailup.tasks.get_client", side_effect=lambda config=None: self.fake.client())
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_dry_run_does_not_write(self):
        before_lists = list(models.MailingList.objects.values())
        before_rows = list(models.MessageAnalytics.objects.values())
        out = StringIO()
        call_command("mailup_sync", "--dry-run", stdout=out)
        self.assertIn("[DRY RUN]", out.getvalue())
        self.assertEqual(list(models.MailingList.objects.values()), before_lists)
        self.assertEqual(list(models.MessageAnalytics.objects.values()), before_rows)

    def test_default_sync_writes_and_a_second_run_does_not_change_it(self):
        call_command("mailup_sync", "--date", "2026-10-30")
        call_command("mailup_sync", "--date", "2026-10-31")
        first = list(models.MessageAnalytics.objects.order_by("id").values())
        call_command("mailup_sync", "--date", "2026-10-31")
        second = list(models.MessageAnalytics.objects.order_by("id").values())
        self.assertEqual(first, second)
        self.assertTrue(first)

    def test_cleanup_requires_yes_without_a_terminal(self):
        mailing_list = models.MailingList.objects.create(list_id=18, name="QNMedia", site="qn")
        models.Message.objects.create(
            mailing_list=mailing_list, message_id=1400, subject="test", sent_at=timezone.now(),
        )
        with self.assertRaises(CommandError):
            call_command("mailup_cleanup")
        self.assertTrue(models.Message.objects.filter(message_id=1400).exists())
        out = StringIO()
        call_command("mailup_cleanup", "--dry-run", stdout=out)
        self.assertIn("[DRY RUN]", out.getvalue())
        self.assertTrue(models.Message.objects.filter(message_id=1400).exists())
        call_command("mailup_cleanup", "--yes")
        self.assertFalse(models.Message.objects.filter(message_id=1400).exists())

    def test_refused_confirmation_writes_nothing(self):
        mailing_list = models.MailingList.objects.create(list_id=18, name="QNMedia", site="qn")
        models.Message.objects.create(
            mailing_list=mailing_list, message_id=1400, subject="test", sent_at=timezone.now(),
        )
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="no"):
            call_command("mailup_cleanup")
        self.assertTrue(models.Message.objects.filter(message_id=1400).exists())

    def test_invalid_dates_and_unknown_ids(self):
        with self.assertRaises(CommandError):
            call_command("mailup_sync", "--date", "2026-13-40")
        with self.assertRaises(CommandError):
            call_command("mailup_sync", "--date", "2099-01-01")
        with self.assertRaises(CommandError):
            call_command("mailup_backfill", "--from", "2026-11-09", "--to", "2026-11-01")
        with self.assertRaises(CommandError):
            call_command("mailup_sync", "--dry-run", "--list-id", "999")

    def test_bad_date_exits_nonzero(self):
        env = os.environ.copy()
        env["DJANGO_SETTINGS_MODULE"] = "test_settings"
        env["PYTHONPATH"] = os.pathsep.join(["/tmp/np_test", env.get("PYTHONPATH", "")])
        result = subprocess.run(
            [sys.executable, "manage.py", "mailup_sync", "--date", "not-a-date"],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non valida", result.stderr + result.stdout)

    def test_deprecated_alias_still_runs(self):
        out = StringIO()
        with patch("mailup.management.commands.mailup.get_client", side_effect=lambda: self.fake.client()):
            call_command("mailup", "check", stdout=out)
        self.assertIn("Deprecato", out.getvalue())
        self.assertIn("liste visibili", out.getvalue())

    def test_failed_fetch_exits_as_an_error(self):
        self.fake.fail_lists.add(1)
        models.MailingList.objects.create(list_id=1, name="QN", site="qn", active=True)
        with self.assertRaises(CommandError):
            call_command("mailup_sync", "--date", "2026-10-31")
        self.assertFalse(models.MessageAnalytics.objects.exists())
