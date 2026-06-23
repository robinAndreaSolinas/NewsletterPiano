from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from url_shorter import views
from url_shorter.models import UrlShorter


# Register your models here.

@admin.register(UrlShorter)
class UrlShorterAdmin(admin.ModelAdmin):
    date_hierarchy = 'created_at'
    list_display = ('slug','original_url','created_at', 'is_active',)
    list_editable = ('is_active',)
    readonly_fields = ('clicks', 'created_at', 'slug', 'destination_url')

    def changelist_view(self, request, extra_context=None):
        self.request = request
        return super().changelist_view(request, extra_context)

    @admin.display(description="Destination Url")
    def destination_url(self, obj):
        if not obj.slug:
            return "-"
        url = self.request.build_absolute_uri(reverse(views.proxy, kwargs={'slug': obj.slug}))
        return url

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if change and form.is_valid() and 'original_url' in form.changed_data:
            obj.slug = obj.generate_slug()
        super().save_model(request, obj, form, change)