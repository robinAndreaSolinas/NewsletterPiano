from urllib.parse import urlparse

from rest_framework import serializers
from image.models import Image


class ImageSerializer(serializers.ModelSerializer):

    domain = serializers.SerializerMethodField() # method mapped fields (get_domain)

    def get_domain(self, obj):
        url = obj.url
        if url:
            return urlparse(url).netloc
        return ""

    class Meta:
        model = Image
        fields = (
            "url",
            "image_url",
            "image_width",
            "image_height",
            "image_extension",
            "image_weight",
            "has_video",
            "source",
            "published_at",
            "fetched_at",
            "domain",
        )