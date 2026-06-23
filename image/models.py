from django.db import models
from conf import settings


class ImageManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().using(settings.IMAGE_CONFIG.get("DB_NAME"))


class Image(models.Model):
    objects = ImageManager()

    id = models.IntegerField(primary_key=True)
    url = models.URLField(db_column='article_url')
    image_url = models.URLField()
    image_width = models.IntegerField()
    image_height = models.IntegerField()
    image_extension = models.CharField(max_length=255)
    image_weight = models.IntegerField()
    has_video = models.BooleanField()
    source = models.CharField(max_length=255)
    published_at = models.DateTimeField()
    fetched_at = models.DateTimeField()

    class Meta:
        managed = False        # Django non tocca mai la tabella
        db_table = settings.IMAGE_CONFIG.get("DB_TABLE")     # nome reale della tabella nel sqlite