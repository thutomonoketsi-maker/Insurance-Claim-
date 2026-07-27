from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

# core/apps.py
from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    
    def ready(self):
        import core.signals  # We'll create this