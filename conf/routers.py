from conf import settings


class ReadOnlyRouter:
    _db = settings.IMAGE_CONFIG.get("DB_NAME")

    def db_for_read(self, model, **hints):
        if not model._meta.managed and model._meta.app_label == 'images':
            return self._db
        return None

    def db_for_write(self, model, **hints):
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == self._db:
            return False  # blocca qualsiasi migrate su questo DB
        return None