from lib.rest import DateRangeActionMixin
from .serializers import ImageSerializer
from .models import Image
from rest_framework import mixins, viewsets

class ImageViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    DateRangeActionMixin,
    viewsets.GenericViewSet
):
    queryset = Image.objects.order_by("-published_at").all()
    serializer_class = ImageSerializer
    lookup_field = 'url'
