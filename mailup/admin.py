from django.contrib import admin

from lib.admin import ReadOnlyAdmin
from mailup.models import MailingList, Message, MessageAnalytics, Analytics


@admin.register(MailingList)
class ReadOnlyMailingListAdmin(ReadOnlyAdmin):
    list_display = ('list_id', 'name', 'active', 'site', 'total_active_users', 'fetched_at')
    list_filter = ('active', 'site')
    search_fields = ('name',)


@admin.register(Message)
class ReadOnlyMessageAdmin(ReadOnlyAdmin):
    list_display = ('message_id', 'mailing_list__name', 'subject', 'sent_at', 'sendings', 'sent', 'delivered',
                    'opened', 'clicked', 'bounced', 'unsubscribed', 'fetched_at')
    list_filter = ('mailing_list__name',)
    search_fields = ('subject',)


@admin.register(MessageAnalytics)
class ReadOnlyMessageAnalyticsAdmin(ReadOnlyAdmin):
    list_display = ('message__message_id', 'message__subject', 'mailing_list__name', 'date', 'sent', 'delivered',
                    'clicked', 'bounced', 'unsubscribed', 'fetched_at')
    list_filter = ('mailing_list__name', 'date')
    search_fields = ('message__subject',)


@admin.register(Analytics)
class ReadOnlyAnalyticsAdmin(ReadOnlyAdmin):
    list_display = ('mailing_list__name', 'date', 'sent', 'delivered', 'opened', 'clicked', 'bounced', 'subscribed',
                    'unsubscribed', 'fetched_at')
    list_filter = ('mailing_list__name', 'date')
    search_fields = ('mailing_list__name',)
