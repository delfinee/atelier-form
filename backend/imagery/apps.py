from django.apps import AppConfig


class ImageryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "imagery"
    verbose_name = "Imagery"

    def ready(self):
        from . import signals  # noqa: F401  (registers cache invalidation)
