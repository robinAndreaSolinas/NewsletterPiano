from rest_framework import serializers

from ingestion.models import Analytics, Campaign
from mailup.models import Message as MailUpMessage, MessageAnalytics as MailUpMessageAnalytics


class SiteField(serializers.Field):
    SITE_MAP = {
        594: "gio",
        595: "rdc",
        596: "naz",
        808: "lux",
        557: "qn",
    }

    def to_representation(self, obj):
        return self.SITE_MAP.get(obj.site_id, "unknown")


class AnalyticsSerializer(serializers.ModelSerializer):
    campaign = serializers.CharField(source="campaign.name", read_only=True)
    site = SiteField(source="campaign", read_only=True)
    source = serializers.SerializerMethodField()

    class Meta:
        model = Analytics
        fields = ("campaign",
                  "date",
                  "site",
                  "source",
                  "sent",
                  "opened",
                  "clicked",
                  "subscribed",
                  "unsubscribed",
                  )

    def get_source(self, obj):
        return "piano"


class CampaignSerializer(serializers.ModelSerializer):
    site = SiteField(source="*", read_only=True)
    source = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = (
                  "campaign_id",
                  "name",
                  "site",
                  "source",
                  "active",
                  "schedule_type",
                  "mailing_list_id",
                  "total_users",
                  "total_active_users",
                  "fetched_at"
                  )

    def get_source(self, obj):
        return "piano"


class MailUpAnalyticsSerializer(serializers.ModelSerializer):
    """One MailUp message (a single newsletter) per day. `campaign` is the newsletter name."""
    campaign = serializers.CharField(source="message.name", read_only=True)
    site = serializers.CharField(source="mailing_list.site", read_only=True)
    source = serializers.SerializerMethodField()

    class Meta:
        model = MailUpMessageAnalytics
        fields = ("campaign",
                  "date",
                  "site",
                  "source",
                  "sent",
                  "opened",
                  "clicked",
                  "subscribed",
                  "unsubscribed",
                  )

    def get_source(self, obj):
        return "mailup"


class MailUpCampaignSerializer(serializers.ModelSerializer):
    """A MailUp message is a campaign. Subscriber counts are those of the list it is sent to."""
    campaign_id = serializers.IntegerField(source="message_id", read_only=True)
    name = serializers.CharField(read_only=True)
    site = serializers.CharField(source="mailing_list.site", read_only=True)
    active = serializers.BooleanField(source="mailing_list.active", read_only=True)
    mailing_list_id = serializers.IntegerField(source="mailing_list.list_id", read_only=True)
    total_users = serializers.IntegerField(source="mailing_list.total_users", read_only=True)
    total_active_users = serializers.IntegerField(source="mailing_list.total_active_users", read_only=True)
    schedule_type = serializers.SerializerMethodField()
    source = serializers.SerializerMethodField()

    class Meta:
        model = MailUpMessage
        fields = (
                  "campaign_id",
                  "name",
                  "site",
                  "source",
                  "active",
                  "schedule_type",
                  "mailing_list_id",
                  "total_users",
                  "total_active_users",
                  "fetched_at"
                  )

    def get_source(self, obj):
        return "mailup"

    def get_schedule_type(self, obj):
        return "regular"
