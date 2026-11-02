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
    sendings = models.IntegerField(default=1)
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


class Analytics(models.Model):
    """Daily record per list, same shape as `ingestion.Analytics` plus delivered/bounced."""
    mailing_list = models.ForeignKey(MailingList, on_delete=models.DO_NOTHING, null=True, related_name="analytics")
    date = models.DateField()
    sent = models.BigIntegerField(default=0)
    delivered = models.BigIntegerField(default=0)
    opened = models.BigIntegerField(default=0)
    clicked = models.BigIntegerField(default=0)
    bounced = models.BigIntegerField(default=0)
    subscribed = models.BigIntegerField(default=0)
    unsubscribed = models.BigIntegerField(default=0)
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
