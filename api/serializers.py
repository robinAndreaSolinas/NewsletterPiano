from rest_framework import serializers

from ingestion.models import Analytics


class AnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analytics
        fields = ('campaign__name', 'date')