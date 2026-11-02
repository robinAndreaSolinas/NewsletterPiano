from rest_framework import serializers

from ingestion.models import Analytics, Campaign
from mailup.models import Analytics as MailUpAnalytics, MailingList as MailUpList


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
    campaign = serializers.CharField(source="mailing_list.name", read_only=True)
    site = serializers.CharField(source="mailing_list.site", read_only=True)
    source = serializers.SerializerMethodField()

    class Meta:
        model = MailUpAnalytics
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
    campaign_id = serializers.IntegerField(source="list_id", read_only=True)
    mailing_list_id = serializers.IntegerField(source="list_id", read_only=True)
    schedule_type = serializers.SerializerMethodField()
    source = serializers.SerializerMethodField()

    class Meta:
        model = MailUpList
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
