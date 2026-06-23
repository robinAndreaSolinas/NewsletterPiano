import hashlib
import secrets

from django.db import models

# Create your models here.

class UrlShorter(models.Model):
    CODE_SIZE = 6
    original_url = models.URLField(max_length=255)
    slug = models.CharField(max_length=15, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    clicks = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            if not self.slug:
                self.slug = self.generate_slug(self.CODE_SIZE, True)

        return super().save(*args, **kwargs)

    def generate_slug(self, size = CODE_SIZE, is_deterministic=True):
        if is_deterministic:
            return hashlib.sha256(f"{self.original_url}".encode()).hexdigest()[:size + 2]
        else:
            return secrets.token_urlsafe(size)

    class Meta:
        verbose_name_plural = "Url Shortener"
        verbose_name = "Url Shortener"

        db_table = "url_shorter"
