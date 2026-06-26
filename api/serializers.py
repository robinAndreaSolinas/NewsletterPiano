from rest_framework import serializers

from ingestion.models import Analytics, Campaign

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

    class Meta:
        model = Analytics
        fields = ("campaign",
                  "date",
                  "site",
                  "sent",
                  "opened",
                  "clicked",
                  "subscribed",
                  "unsubscribed",
                  )

class CampaignSerializer(serializers.ModelSerializer):
    site = SiteField(source="*", read_only=True)
    class Meta:
        model = Campaign
        fields = (
                  "campaign_id",
                  "name",
                  "site",
                  "active",
                  "schedule_type",
                  "mailing_list_id",
                  "total_users",
                  "total_active_users",
                  "fetched_at"
                  )