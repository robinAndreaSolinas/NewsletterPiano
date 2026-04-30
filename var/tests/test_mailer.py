import smtplib
import pytest
from unittest.mock import patch, MagicMock, mock_open, call

from lib.mailer import Email, send


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_email():
    return Email(
        from_address="sender@example.com",
        to="recipient@example.com",
        subject="Test Subject",
        body="Hello, world!",
    )


@pytest.fixture
def full_email():
    return Email(
        from_address="sender@example.com",
        to=["to1@example.com", "to2@example.com"],
        cc=["cc1@example.com"],
        bcc=["bcc1@example.com"],
        subject="Full Email Subject",
        body="<h1>Hello HTML</h1>",
        attachments=["/fake/path/file.txt"],
    )


# ---------------------------------------------------------------------------
# Email.__init__
# ---------------------------------------------------------------------------

class TestEmailInit:

    def test_from_address_string(self, simple_email):
        assert simple_email.from_address == "sender@example.com"

    def test_from_address_list_joined(self):
        email = Email(
            from_address=["Alice <alice@example.com>", "Bob <bob@example.com>"],
            to="recipient@example.com",
        )
        assert email.from_address == "Alice <alice@example.com>, Bob <bob@example.com>"

    def test_to_string_becomes_list(self, simple_email):
        assert simple_email.to == ["recipient@example.com"]

    def test_to_list_preserved(self, full_email):
        assert full_email.to == ["to1@example.com", "to2@example.com"]

    def test_cc_string_becomes_list(self):
        email = Email("a@example.com", "b@example.com", cc="c@example.com")
        assert email.cc == ["c@example.com"]

    def test_cc_list_preserved(self, full_email):
        assert full_email.cc == ["cc1@example.com"]

    def test_cc_default_empty(self, simple_email):
        assert simple_email.cc == []

    def test_bcc_string_becomes_list(self):
        email = Email("a@example.com", "b@example.com", bcc="d@example.com")
        assert email.bcc == ["d@example.com"]

    def test_bcc_list_preserved(self, full_email):
        assert full_email.bcc == ["bcc1@example.com"]

    def test_bcc_default_empty(self, simple_email):
        assert simple_email.bcc == []

    def test_subject_default_empty_string(self):
        email = Email("a@example.com", "b@example.com")
        assert email.subject == ""

    def test_body_default_empty_string(self):
        email = Email("a@example.com", "b@example.com")
        assert email.body == ""

    def test_attachments_default_empty_list(self, simple_email):
        assert simple_email.attachments == []

    def test_attachments_preserved(self, full_email):
        assert full_email.attachments == ["/fake/path/file.txt"]

class TestEmailRecipients:

    def test_recipients_only_to(self, simple_email):
        assert simple_email.recipients == ["recipient@example.com"]

    def test_recipients_to_plus_cc_plus_bcc(self, full_email):
        assert full_email.recipients == [
            "to1@example.com",
            "to2@example.com",
            "cc1@example.com",
            "bcc1@example.com",
        ]

    def test_recipients_order(self):
        email = Email(
            "a@example.com",
            to=["t@example.com"],
            cc=["c@example.com"],
            bcc=["b@example.com"],
        )
        assert email.recipients == ["t@example.com", "c@example.com", "b@example.com"]


# ---------------------------------------------------------------------------
# Email.message  (plain text)
# ---------------------------------------------------------------------------

class TestEmailMessagePlainText:

    def test_message_is_string(self, simple_email):
        assert isinstance(simple_email.message, str)

    def test_message_contains_from(self, simple_email):
        assert "sender@example.com" in simple_email.message

    def test_message_contains_to(self, simple_email):
        assert "recipient@example.com" in simple_email.message

    def test_message_contains_subject(self, simple_email):
        assert "Test Subject" in simple_email.message

    def test_message_plain_content_type(self, simple_email):
        assert "text/plain" in simple_email.message

    def test_message_bcc_not_in_header(self, full_email):
        # BCC must never appear in the serialised message headers
        assert "bcc1@example.com" not in full_email.message

    def test_message_cc_in_header(self, full_email):
        assert "cc1@example.com" in full_email.message

    def test_message_multiple_to_joined(self, full_email):
        assert "to1@example.com" in full_email.message
        assert "to2@example.com" in full_email.message


# ---------------------------------------------------------------------------
# Email.message  (HTML detection)
# ---------------------------------------------------------------------------

class TestEmailMessageHtml:

    def test_html_body_detected(self):
        email = Email(
            "a@example.com",
            "b@example.com",
            body="<p>Hello</p>",
        )
        assert "text/html" in email.message

    def test_plain_body_not_detected_as_html(self, simple_email):
        assert "text/html" not in simple_email.message

    def test_body_with_only_angle_bracket_open(self):
        """A body with '<' but no '>' should fall back to plain text."""
        email = Email("a@example.com", "b@example.com", body="price < 100")
        assert "text/plain" in email.message


# ---------------------------------------------------------------------------
# Email.message  (attachments)
# ---------------------------------------------------------------------------

class TestEmailMessageAttachments:

    def test_attachment_included_when_file_exists(self):
        email = Email(
            "a@example.com",
            "b@example.com",
            attachments=["/fake/report.pdf"],
        )
        fake_data = b"PDF content"
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=fake_data)):
            msg = email.message
        assert "report.pdf" in msg

    def test_attachment_skipped_when_file_missing(self):
        email = Email(
            "a@example.com",
            "b@example.com",
            attachments=["/nonexistent/file.txt"],
        )
        with patch("os.path.exists", return_value=False):
            msg = email.message
        # No attachment boundary should appear beyond the body part
        assert "file.txt" not in msg

    def test_multiple_attachments(self):
        email = Email(
            "a@example.com",
            "b@example.com",
            attachments=["/fake/a.txt", "/fake/b.txt"],
        )
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=b"data")):
            msg = email.message
        assert "a.txt" in msg
        assert "b.txt" in msg


# ---------------------------------------------------------------------------
# send()
# ---------------------------------------------------------------------------

class TestSend:

    def _make_smtp_mock(self):
        smtp_instance = MagicMock()
        smtp_instance.__enter__ = MagicMock(return_value=smtp_instance)
        smtp_instance.__exit__ = MagicMock(return_value=False)
        return smtp_instance

    def test_send_multiple_emails(self, simple_email, full_email):
        smtp_mock = self._make_smtp_mock()
        with patch("smtplib.SMTP", return_value=smtp_mock):
            send(simple_email, full_email, username="u", password="p")
        assert smtp_mock.sendmail.call_count == 2

    def test_starttls_called_when_use_tls_true(self, simple_email):
        smtp_mock = self._make_smtp_mock()
        with patch("smtplib.SMTP", return_value=smtp_mock):
            send(simple_email, use_tls=True)
        smtp_mock.starttls.assert_called_once()

    def test_starttls_not_called_when_use_tls_false(self, simple_email):
        smtp_mock = self._make_smtp_mock()
        with patch("smtplib.SMTP", return_value=smtp_mock):
            send(simple_email, use_tls=False)
        smtp_mock.starttls.assert_not_called()

    def test_login_called_with_credentials(self, simple_email):
        smtp_mock = self._make_smtp_mock()
        with patch("smtplib.SMTP", return_value=smtp_mock):
            send(simple_email, username="myuser", password="mypass")
        smtp_mock.login.assert_called_once_with("myuser", "mypass")

    def test_login_not_called_without_credentials(self, simple_email):
        smtp_mock = self._make_smtp_mock()
        with patch("smtplib.SMTP", return_value=smtp_mock):
            send(simple_email)
        smtp_mock.login.assert_not_called()

    def test_default_smtp_server_and_port(self, simple_email):
        with patch("smtplib.SMTP") as smtp_cls:
            smtp_cls.return_value = self._make_smtp_mock()
            send(simple_email)
        smtp_cls.assert_called_once_with("localhost", 587)

    def test_custom_smtp_server_and_port(self, simple_email):
        with patch("smtplib.SMTP") as smtp_cls:
            smtp_cls.return_value = self._make_smtp_mock()
            send(simple_email, smtp_server="mail.example.com", smtp_port=465)
        smtp_cls.assert_called_once_with("mail.example.com", 465)

    def test_smtp_exception_is_reraised(self, simple_email):
        smtp_mock = self._make_smtp_mock()
        smtp_mock.sendmail.side_effect = smtplib.SMTPException("failure")
        with patch("smtplib.SMTP", return_value=smtp_mock):
            with pytest.raises(smtplib.SMTPException, match="Error sending email"):
                send(simple_email)