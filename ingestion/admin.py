from django.contrib import admin
from ingestion.models import Campaign, Analytics
from lib.admin import ReadOnlyAdmin


# Register your models here.

@admin.register(Campaign)
class ReadOnlyCampaignAdmin(ReadOnlyAdmin):
    list_display = ('campaign_id', 'name', 'active', 'site_id', 'schedule_type', 'mailing_list_id', 'fetched_at')
    list_filter = ('active', 'schedule_type', "site_id")
    search_fields = ('name',)

@admin.register(Analytics)
class ReadOnlyAnalyticsAdmin(ReadOnlyAdmin):
    list_display = ("campaign__name", "date", "sent", "opened", "clicked", "subscribed", "unsubscribed",  'fetched_at')
    list_filter = ("campaign__name", "date")
    search_fields = ("campaign__name",)