import datetime

from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from api.serializers import AnalyticsSerializer, CampaignSerializer
from ingestion.models import Analytics, Campaign


# Create your views here.

class CampaignViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin
):
    queryset = Campaign.objects.filter(active=True).all()
    serializer_class = CampaignSerializer
    lookup_field = 'campaign_id'


class AnalyticsViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Analytics.objects.filter(campaign__active=True).all()
    serializer_class = AnalyticsSerializer
    lookup_field = 'campaign_id'

    @action(detail=False, methods=['get'], url_path=r'(?P<from_date>\d{8})(/(?P<to_date>\d{8}))?$')
    def by_date(self, request, from_date, to_date = None, **kwargs):
        from_date = datetime.datetime.strptime(from_date, "%Y%m%d").date()
        to_date = datetime.datetime.strptime(to_date, "%Y%m%d").date() if to_date else from_date

        data = Analytics.objects.filter(
            campaign__active=True,
            date__range=(from_date, to_date + datetime.timedelta(days=1)),
        )

        return Response(self.get_serializer(data, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        qs = Analytics.objects.filter(campaign_id=kwargs["campaign_id"], campaign__active=True)
        return Response(self.get_serializer(qs, many=True).data)