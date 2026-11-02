import datetime

from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from api.serializers import (
    AnalyticsSerializer,
    CampaignSerializer,
    MailUpAnalyticsSerializer,
    MailUpCampaignSerializer,
)
from ingestion.models import Analytics, Campaign
from mailup.models import Analytics as MailUpAnalytics, MailingList as MailUpList

SOURCE_PARAM = OpenApiParameter(
    'source',
    str,
    OpenApiParameter.QUERY,
    required=False,
    enum=['piano', 'mailup'],
    description='Limita i risultati a un provider. Default: entrambi.',
)


class CombinedSourceMixin:
    """Serializes Piano + MailUp rows on the same route, distinguished by `source`."""
    piano_serializer_class = None
    mailup_serializer_class = None
    sort_key = None

    def requested_source(self):
        value = (self.request.query_params.get('source') or '').lower()
        return value if value in ('piano', 'mailup') else None

    def piano_queryset(self):
        raise NotImplementedError

    def mailup_queryset(self):
        raise NotImplementedError

    def filter_piano_dates(self, from_date, to_date):
        raise NotImplementedError

    def filter_mailup_dates(self, from_date, to_date):
        raise NotImplementedError

    def combined_rows(self, piano_qs=None, mailup_qs=None):
        source = self.requested_source()
        rows = []
        if source != 'mailup':
            rows.extend(self.piano_serializer_class(
                self.piano_queryset() if piano_qs is None else piano_qs, many=True
            ).data)
        if source != 'piano':
            rows.extend(self.mailup_serializer_class(
                self.mailup_queryset() if mailup_qs is None else mailup_qs, many=True
            ).data)
        if self.sort_key:
            rows = sorted(rows, key=self.sort_key, reverse=True)
        return rows

    def list(self, request, *args, **kwargs):
        rows = self.combined_rows()
        page = self.paginate_queryset(rows)
        if page is not None:
            return self.get_paginated_response(page)
        return Response(rows)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                'from_date',
                str,
                OpenApiParameter.PATH,
                description='Data inizio (YYYYMMDD)',
                pattern=r'^\d{8}$',
            ),
            OpenApiParameter(
                'to_date',
                str,
                OpenApiParameter.QUERY,
                required=False,
                description='Data fine (YYYYMMDD), default = from_date',
                pattern=r'^\d{8}$',
            ),
            SOURCE_PARAM,
        ]
    )
    @action(detail=False, methods=['get'], url_path=r'(?P<from_date>\d{8})')
    def by_date(self, request, from_date, **kwargs):
        try:
            from_date = datetime.datetime.strptime(from_date, "%Y%m%d").date()
        except ValueError:
            return Response({'detail': 'from_date non valida.'}, status=400)

        to_date_str = request.query_params.get('to_date')
        if to_date_str:
            try:
                to_date = datetime.datetime.strptime(to_date_str, "%Y%m%d").date()
            except ValueError:
                return Response({'detail': 'to_date non valida.'}, status=400)
        else:
            to_date = from_date

        if to_date < from_date:
            return Response({'detail': 'to_date non può essere precedente a from_date.'}, status=400)

        return Response(self.combined_rows(
            piano_qs=self.filter_piano_dates(from_date, to_date),
            mailup_qs=self.filter_mailup_dates(from_date, to_date),
        ))


@extend_schema(parameters=[SOURCE_PARAM])
class CampaignViewSet(
    CombinedSourceMixin,
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    queryset = Campaign.objects.filter(active=True).order_by("-fetched_at").all()
    serializer_class = CampaignSerializer
    piano_serializer_class = CampaignSerializer
    mailup_serializer_class = MailUpCampaignSerializer
    lookup_field = 'campaign_id'
    sort_key = staticmethod(lambda row: row.get("fetched_at") or "")

    def piano_queryset(self):
        return Campaign.objects.filter(active=True).order_by("-fetched_at")

    def mailup_queryset(self):
        return MailUpList.objects.filter(active=True).order_by("-fetched_at")

    def filter_piano_dates(self, from_date, to_date):
        return self.piano_queryset().filter(
            fetched_at__gte=from_date,
            fetched_at__lt=to_date + datetime.timedelta(days=1),
        )

    def filter_mailup_dates(self, from_date, to_date):
        return self.mailup_queryset().filter(
            fetched_at__gte=from_date,
            fetched_at__lt=to_date + datetime.timedelta(days=1),
        )

    def retrieve(self, request, *args, **kwargs):
        campaign_id = kwargs.get(self.lookup_field)
        source = self.requested_source()
        piano = Campaign.objects.filter(active=True, campaign_id=campaign_id).first()
        mailup = MailUpList.objects.filter(active=True, list_id=campaign_id).first()

        if source == 'mailup' or (piano is None and mailup is not None):
            if mailup is None:
                return Response({'detail': 'Non trovato.'}, status=404)
            return Response(MailUpCampaignSerializer(mailup).data)
        if piano is None:
            return Response({'detail': 'Non trovato.'}, status=404)
        return Response(CampaignSerializer(piano).data)


@extend_schema(parameters=[SOURCE_PARAM])
class AnalyticsViewSet(
    CombinedSourceMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Analytics.objects.filter(campaign__active=True).select_related("campaign").order_by("-date").all()
    serializer_class = AnalyticsSerializer
    piano_serializer_class = AnalyticsSerializer
    mailup_serializer_class = MailUpAnalyticsSerializer
    lookup_field = 'campaign_id'
    sort_key = staticmethod(lambda row: (row.get("date") or "", row.get("campaign") or ""))

    def piano_queryset(self):
        return Analytics.objects.filter(campaign__active=True).select_related("campaign").order_by("-date")

    def mailup_queryset(self):
        return MailUpAnalytics.objects.filter(mailing_list__active=True).select_related("mailing_list").order_by("-date")

    def filter_piano_dates(self, from_date, to_date):
        return self.piano_queryset().filter(date__gte=from_date, date__lte=to_date)

    def filter_mailup_dates(self, from_date, to_date):
        return self.mailup_queryset().filter(date__gte=from_date, date__lte=to_date)
