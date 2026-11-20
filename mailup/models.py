from django.db import models


class MailingList(models.Model):
    """A MailUp list: the equivalent of a Piano `Campaign` (one newsletter)."""
    list_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    list_guid = models.CharField(max_length=64, blank=True, default="")
    site = models.CharField(max_length=50, default="qn")
    active = models.BooleanField(default=True)
    total_users = models.BigIntegerField(default=0)
    total_active_users = models.BigIntegerField(default=0)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'MailUp list'
        verbose_name_plural = 'MailUp lists'

    def __str__(self):
        return f"{self.name.title()}"

    def __repr__(self):
        return f"<{self.__class__.__name__}(list_id={self.list_id}, name={self.name}, active={self.active}, site={self.site})>"


class Message(models.Model):
    """A MailUp email message with its lifetime statistics, dated on its latest sending."""
    mailing_list = models.ForeignKey(MailingList, on_delete=models.CASCADE, related_name="messages")
    message_id = models.IntegerField(unique=True)
    subject = models.CharField(max_length=500, blank=True, default="")
    sent_at = models.DateTimeField()
    sendings = models.IntegerField(default=0)
    sent = models.BigIntegerField(default=0)
    delivered = models.BigIntegerField(default=0)
    opened = models.BigIntegerField(default=0)
    clicked = models.BigIntegerField(default=0)
    bounced = models.BigIntegerField(default=0)
    unsubscribed = models.BigIntegerField(default=0)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-sent_at',)
        indexes = [
            models.Index(fields=['mailing_list', 'sent_at']),
        ]
        verbose_name = 'MailUp message'
        verbose_name_plural = 'MailUp messages'

    def __str__(self):
        return f"{self.subject or self.message_id} - {self.sent_at:%Y-%m-%d}"

    @property
    def name(self) -> str:
        """Newsletter name in the API: the subject, or the id when MailUp has no subject."""
        return self.subject or f"Messaggio {self.message_id}"


class Analytics(models.Model):
    """Daily record per list. Legacy: no longer written and no longer served, see `MessageAnalytics`.

    Kept for the history already stored and for the RICOSTRUITO days that close_list must not touch.
    """
    mailing_list = models.ForeignKey(MailingList, on_delete=models.DO_NOTHING, null=True, related_name="analytics")
    date = models.DateField()
    sent = models.BigIntegerField(default=0)
    delivered = models.BigIntegerField(default=0)
    opened = models.BigIntegerField(default=0)
    clicked = models.BigIntegerField(default=0)
    bounced = models.BigIntegerField(default=0)
    subscribed = models.BigIntegerField(default=0)
    unsubscribed = models.BigIntegerField(default=0)
    # Not part of the public API. Which endpoint produced the numbers.
    provenance = models.TextField(blank=True, default="")
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-date',)
        unique_together = ('mailing_list', 'date')
        indexes = [
            models.Index(fields=['mailing_list', 'date']),
        ]
        verbose_name = 'MailUp analytics'
        verbose_name_plural = 'MailUp analytics'

    def __str__(self):
        return f"{self.mailing_list.name.title()} - {self.date}"

    def __repr__(self):
        return f"<{self.__class__.__name__}(mailing_list={self.mailing_list}, date={self.date}, sent={self.sent}, opened={self.opened}, clicked={self.clicked}, subscribed={self.subscribed}, unsubscribed={self.unsubscribed})>"


class MessageAnalytics(models.Model):
    """Daily record per message (one newsletter), served by the API in place of the list rows.

    Values are the growth of the message's lifetime counts between two snapshots.
    `subscribed` stays 0: MailUp opt-ins belong to the list, not to a message.
    `unsubscribed` is the delta of the message's Count/Unsubscriptions.
    """
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="analytics")
    mailing_list = models.ForeignKey(MailingList, on_delete=models.CASCADE, related_name="message_analytics")
    date = models.DateField()
    sent = models.BigIntegerField(default=0)
    delivered = models.BigIntegerField(default=0)
    opened = models.BigIntegerField(default=0)
    clicked = models.BigIntegerField(default=0)
    bounced = models.BigIntegerField(default=0)
    subscribed = models.BigIntegerField(default=0)
    unsubscribed = models.BigIntegerField(default=0)
    # Not part of the public API. Which endpoint produced the numbers.
    provenance = models.TextField(blank=True, default="")
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-date',)
        unique_together = ('message', 'date')
        indexes = [
            models.Index(fields=['mailing_list', 'date']),
            models.Index(fields=['message', 'date']),
        ]
        verbose_name = 'MailUp message analytics'
        verbose_name_plural = 'MailUp message analytics'

    def __str__(self):
        return f"{self.message} - {self.date}"

    def __repr__(self):
        return (f"<{self.__class__.__name__}(message={self.message_id}, date={self.date}, sent={self.sent}, "
                f"clicked={self.clicked}, unsubscribed={self.unsubscribed})>")


class MetricSnapshot(models.Model):
    """Lifetime MailUp counts observed on `captured_on`. Not a daily statistic.

    The daily row is the difference between two snapshots. The first snapshot
    has no difference and must not be copied into Analytics.
    """
    mailing_list = models.ForeignKey(MailingList, on_delete=models.CASCADE, related_name="snapshots")
    message_id = models.IntegerField()
    captured_on = models.DateField()
    sent = models.BigIntegerField(default=0)
    delivered = models.BigIntegerField(default=0)
    opened = models.BigIntegerField(default=0)
    clicked = models.BigIntegerField(default=0)
    bounced = models.BigIntegerField(default=0)
    unsubscribed = models.BigIntegerField(default=0)

    class Meta:
        unique_together = ("mailing_list", "message_id", "captured_on")
        indexes = [
            models.Index(fields=["mailing_list", "message_id", "captured_on"]),
        ]
