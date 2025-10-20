# apps/admin_api/apps.py
from django.apps import AppConfig
from importlib import import_module

class AdminApiConfig(AppConfig):
    """
    Configuration for the admin_api app.
    - Ensures signals are imported and connected when the app is ready.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.admin_api'

    def ready(self):
        # Import signals module to connect signal handlers
        import_module('apps.admin_api.signals')