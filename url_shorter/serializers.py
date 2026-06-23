from django.urls import reverse

from . import views
from .models import UrlShorter
from rest_framework import serializers

class UrlShorterSerializer(serializers.ModelSerializer):
    url = serializers.URLField(source="original_url")

    destination_url = serializers.SerializerMethodField()

    def get_destination_url(self, obj):
        request = self.context.get("request")
        print(obj, type(obj))
        path = obj.slug or None

        if path:
            path = reverse(views.proxy, kwargs={"slug": obj.slug})
            return request.build_absolute_uri(path) if request else path
        else:
            return request.build_absolute_uri()

    def create(self, validated_data):
        instance, _ = UrlShorter.objects.get_or_create(**validated_data)
        return instance

    class Meta:
        model = UrlShorter
        fields = (
            "url",
            "slug",
            "created_at",
            "clicks",
            "is_active",
            "destination_url",
        )
        read_only_fields = (
            "slug",
            "created_at",
            "clicks",
            "is_active",
        )
