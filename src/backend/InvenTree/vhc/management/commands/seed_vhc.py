"""Seed the initial VHC teams and location hierarchy."""

from django.core.management.base import BaseCommand

from stock.models import StockLocation
from vhc.models import Team


TEAMS = [
    ('OR', 'OR', '#E03131'),
    ('PACU', 'PACU', '#F08C00'),
    ('Anesthesia', 'ANESTHESIA', '#7048E8'),
    ('Rehab', 'REHAB', '#2F9E44'),
    ('Eyeglasses', 'EYEGLASSES', '#1971C2'),
    ('Warehouse & Cleaning', 'WAREHOUSE_CLEANING', '#495057'),
    ('Rural Clinics', 'RURAL_CLINICS', '#0C8599'),
    ('Rural Schools', 'RURAL_SCHOOLS', '#5C940D'),
    ('Kitchen', 'KITCHEN', '#D9480F'),
    ('Personal Items', 'PERSONAL_ITEMS', '#A61E4D'),
    ('Other', 'OTHER', '#868E96'),
]

LOCATIONS = [
    ('VA Warehouse', False),
    ('In Transit', False),
    ('Honduras Warehouse', False),
    ('Hospital ST', True),
    ('Clinic SBJ', True),
    ('VHC Rural Clinics', True),
    ('Rehab St. Margarita', True),
    ('Rehab CRIC', True),
    ('Kitchen / Golf Club', True),
]


class Command(BaseCommand):
    """Create or update VHC reference data."""

    help = 'Seed the VHC packing teams and stock locations'

    def handle(self, *args, **options):
        """Execute the seed operation idempotently."""
        for order, (name, code, color) in enumerate(TEAMS):
            Team.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'color': color,
                    'active': True,
                    'display_order': order,
                },
            )

        root, _created = StockLocation.objects.get_or_create(
            name='VHC', parent=None, defaults={'description': 'VHC inventory locations'}
        )
        for name, external in LOCATIONS:
            StockLocation.objects.update_or_create(
                name=name,
                parent=root,
                defaults={'description': '', 'external': external},
            )

        self.stdout.write(self.style.SUCCESS('VHC teams and locations are ready.'))
