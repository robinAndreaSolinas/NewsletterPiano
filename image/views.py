from .serializers import ImageSerializer
from .models import Image
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
import datetime

class ImageViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Image.objects.all()
    serializer_class = ImageSerializer
    lookup_field = 'url'

    @action(detail=False, methods=['get'], url_path=r'(?P<from_date>\d{8})(/(?P<to_date>\d{8}))?')
    def by_date(self, request, from_date, to_date = None, **kwargs):
        from_date = datetime.datetime.strptime(from_date, "%Y%m%d").date()
        to_date = datetime.datetime.strptime(to_date, "%Y%m%d").date() if to_date else from_date

        data = Image.objects.filter(
            published_at__range=(from_date, to_date + datetime.timedelta(days=1)),
        ).values()


        return Response(self.get_serializer(data, many=True).data)

