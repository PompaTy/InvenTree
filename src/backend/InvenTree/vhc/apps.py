"""Application configuration for the VHC inventory app."""

from django.apps import AppConfig


class VhcConfig(AppConfig):
    """Configure the VHC box inventory application."""

    default_auto_field = 'django.db.models.AutoField'
    name = 'vhc'
    verbose_name = 'VHC Inventory'
