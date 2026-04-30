from django.db import models


# Create your models here.

class Campaign(models.Model):
    campaign_id = models.IntegerField()
    name = models.CharField(max_length=255)
    active = models.BooleanField()
    site_id = models.IntegerField()
    schedule_type = models.CharField(max_length=255)
    mailing_list_id = models.IntegerField()

    def __str__(self):
        return f"{self.__class__.__name__}(campaign_id={self.campaign_id}, name={self.name}, active={self.active}, site_id={self.site_id}, schedule_type={self.schedule_type}, mailing_list_id={self.mailing_list_id})"


class Analytics(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.SET_NULL, null=True)
    datetime = models.DateTimeField()
    sent = models.BigIntegerField()
    opened = models.BigIntegerField()
    clicked = models.BigIntegerField()
    subscribed = models.BigIntegerField()
    unsubscribed = models.BigIntegerField()

    def __str__(self):
        return f"{self.__class__.__name__}(campaing={self.campaign}, datetime={self.datetime}, sent={self.sent}, opened={self.opened}, clicked={self.clicked}, subscribed={self.subscribed}, unsubscribed={self.unsubscribed})"
