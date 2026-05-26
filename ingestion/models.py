from django.db import models


# Create your models here.

class Campaign(models.Model):
    campaign_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    active = models.BooleanField(default=True)
    site_id = models.IntegerField()
    schedule_type = models.CharField(max_length=100)
    mailing_list_id = models.IntegerField()
    total_users = models.BigIntegerField(default=0)
    total_active_users = models.BigIntegerField(default=0)
    fetched_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name.title()}"

    def __repr__(self):
        return f"<{self.__class__.__name__}(campaign_id={self.campaign_id}, name={self.name}, active={self.active}, site_id={self.site_id}, schedule_type={self.schedule_type}, mailing_list_id={self.mailing_list_id})>"


class Analytics(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.DO_NOTHING, null=True)
    date = models.DateField()
    sent = models.BigIntegerField()
    opened = models.BigIntegerField()
    clicked = models.BigIntegerField()
    subscribed = models.BigIntegerField()
    unsubscribed = models.BigIntegerField()
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-date',)
        unique_together = ('campaign', 'date')
        indexes = [
            models.Index(fields=['campaign', 'date']),
        ]
        verbose_name = 'Analytics'
        verbose_name_plural = 'Analytics'

    def __str__(self):
        return f"{self.campaign.name.title()} - {self.date}"

    def __repr__(self):
        return f"<{self.__class__.__name__}(campaing={self.campaign}, date={self.date}, sent={self.sent}, opened={self.opened}, clicked={self.clicked}, subscribed={self.subscribed}, unsubscribed={self.unsubscribed})>"
