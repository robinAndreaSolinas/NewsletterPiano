import datetime
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.decorators import action
from rest_framework.response import Response


class DateRangeActionMixin:
    """
    Aggiunge l'action `by_date` al ViewSet.
    Richiede che il ViewSet abbia un queryset con campo `published_at` (default)
    oppure che venga sovrascritto `date_field`.
    """
    date_field = 'published_at'

    def get_date_range_queryset(self, from_date: datetime.date, to_date: datetime.date):
        return self.get_queryset().filter(**{
            f'{self.date_field}__range': (
                from_date,
                to_date + datetime.timedelta(days=1),
            )
        })

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

        data = self.get_date_range_queryset(from_date, to_date)
        return Response(self.get_serializer(data, many=True).data)