from rest_framework import mixins, viewsets

from api.serializers import AnalyticsSerializer, CampaignSerializer
from ingestion.models import Analytics, Campaign
from lib.rest import DateRangeActionMixin


# Create your views here.

class CampaignViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    DateRangeActionMixin,
):
    queryset = Campaign.objects.filter(active=True).order_by("-fetched_at").all()
    serializer_class = CampaignSerializer
    lookup_field = 'campaign_id'
    date_field = "fetched_at"


class AnalyticsViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    DateRangeActionMixin,
    viewsets.GenericViewSet,
):
    queryset = Analytics.objects.filter(campaign__active=True).order_by("-date").all()
    serializer_class = AnalyticsSerializer
    lookup_field = 'campaign_id'
    date_field = "date"