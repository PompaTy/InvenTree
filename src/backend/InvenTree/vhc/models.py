"""Database models for the VHC box inventory workflow."""

from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

import InvenTree.models
from stock.models import StockLocation


HEX_COLOR_VALIDATOR = RegexValidator(
    regex=r'^#[0-9A-Fa-f]{6}$', message=_('Enter a color in #RRGGBB format')
)
BOX_NUMBER_VALIDATOR = RegexValidator(
    regex=r'^\d{6}$', message=_('Box number must contain exactly six digits')
)


def current_year():
    """Return the current local year for model field defaults."""
    return date.today().year




class Team(InvenTree.models.InvenTreeModel):
    """A VHC packing team and its label color."""

    name = models.CharField(max_length=100, unique=True, verbose_name=_('Name'))
    code = models.CharField(
        max_length=30,
        unique=True,
        validators=[RegexValidator(r'^[A-Z0-9_]+$')],
        verbose_name=_('Code'),
    )
    color = models.CharField(
        max_length=7,
        default='#228BE6',
        validators=[HEX_COLOR_VALIDATOR],
        verbose_name=_('Sticker color'),
    )
    active = models.BooleanField(default=True, verbose_name=_('Active'))
    display_order = models.PositiveSmallIntegerField(
        default=0, verbose_name=_('Display order')
    )

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = _('VHC Team')
        verbose_name_plural = _('VHC Teams')

    def __str__(self):
        return self.name


class ShipmentStatus(models.TextChoices):
    """Lifecycle states for a shipment."""

    PLANNING = 'PLANNING', _('Planning')
    PACKING = 'PACKING', _('Packing')
    IN_TRANSIT = 'IN_TRANSIT', _('In transit')
    ARRIVED = 'ARRIVED', _('Arrived')
    CLOSED = 'CLOSED', _('Closed')


class ShipmentKind(models.TextChoices):
    """Supported shipment types."""

    CONTAINER = 'CONTAINER', _('Container')
    TRUNK = 'TRUNK', _('Trunk')
    OTHER = 'OTHER', _('Other')


class Shipment(InvenTree.models.InvenTreeModel):
    """A container, trunk, or other grouped shipment."""

    reference = models.CharField(
        max_length=100, unique=True, verbose_name=_('Reference')
    )
    year = models.PositiveSmallIntegerField(default=current_year)
    kind = models.CharField(
        max_length=20, choices=ShipmentKind.choices, default=ShipmentKind.CONTAINER
    )
    status = models.CharField(
        max_length=20,
        choices=ShipmentStatus.choices,
        default=ShipmentStatus.PLANNING,
    )
    departure_date = models.DateField(blank=True, null=True)
    arrival_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True, max_length=500)

    class Meta:
        ordering = ['-year', 'reference']
        verbose_name = _('VHC Shipment')
        verbose_name_plural = _('VHC Shipments')

    def __str__(self):
        return self.reference


class Pallet(InvenTree.models.InvenTreeModel):
    """A numbered pallet within a shipment."""

    shipment = models.ForeignKey(
        Shipment, on_delete=models.CASCADE, related_name='pallets'
    )
    number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(99)]
    )
    notes = models.TextField(blank=True, max_length=500)

    class Meta:
        ordering = ['shipment', 'number']
        constraints = [
            models.UniqueConstraint(
                fields=['shipment', 'number'], name='unique_vhc_pallet_per_shipment'
            )
        ]
        verbose_name = _('VHC Pallet')
        verbose_name_plural = _('VHC Pallets')

    def __str__(self):
        return f'{self.shipment.reference} / Pallet {self.number:02d}'


class BoxStatus(models.TextChoices):
    """Operational state of a VHC box."""

    PACKED = 'PACKED', _('Packed')
    PALLETIZED = 'PALLETIZED', _('Palletized')
    IN_TRANSIT = 'IN_TRANSIT', _('In transit')
    HONDURAS_WAREHOUSE = 'HONDURAS_WAREHOUSE', _('Honduras warehouse')
    DISTRIBUTED = 'DISTRIBUTED', _('Distributed')
    RETURNED = 'RETURNED', _('Returned')
    LOST = 'LOST', _('Lost')
    CLOSED = 'CLOSED', _('Closed / empty')


class BoxSource(models.TextChoices):
    """Source of box inventory."""

    DONATION_PURCHASE = 'DONATION_PURCHASE', _('Donation / purchase')
    CONTAINER_ARRIVAL = 'CONTAINER_ARRIVAL', _('Container arrival')
    RETURNED_INVENTORY = 'RETURNED_INVENTORY', _('Returned inventory')
    HONDURAS_PURCHASE = 'HONDURAS_PURCHASE', _('Local Honduras purchase')
    ADJUSTMENT = 'ADJUSTMENT', _('Stock adjustment')


class BoxSequence(InvenTree.models.InvenTreeModel):
    """Race-safe sequence used to allocate annual box numbers."""

    year = models.PositiveSmallIntegerField(unique=True)
    next_value = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name = _('VHC Box Number Sequence')

    @classmethod
    @transaction.atomic
    def next_number(cls, year=None):
        """Allocate the next available YYNNNN box number."""
        year = year or date.today().year
        sequence, _created = cls.objects.select_for_update().get_or_create(year=year)
        value = sequence.next_value

        while value <= 9990:
            number = f'{year % 100:02d}{value:04d}'
            if not Box.objects.filter(box_number=number).exists():
                sequence.next_value = value + 1
                sequence.save(update_fields=['next_value'])
                return number
            value += 1

        raise ValidationError(_('No box numbers remain for this year'))


class Box(InvenTree.models.InvenTreeAttachmentMixin, InvenTree.models.InvenTreeModel):
    """A physical VHC inventory box."""

    box_number = models.CharField(
        max_length=6,
        blank=True,
        unique=True,
        validators=[BOX_NUMBER_VALIDATOR],
        verbose_name=_('Box number'),
    )
    contents = models.TextField(max_length=500, verbose_name=_('Contents'))
    team = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name='boxes', verbose_name=_('Team')
    )
    other_team_description = models.CharField(
        max_length=100, blank=True, verbose_name=_('Other team description')
    )
    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.SET_NULL,
        related_name='boxes',
        blank=True,
        null=True,
    )
    pallet = models.ForeignKey(
        Pallet,
        on_delete=models.SET_NULL,
        related_name='boxes',
        blank=True,
        null=True,
    )
    current_location = models.ForeignKey(
        StockLocation,
        on_delete=models.SET_NULL,
        related_name='vhc_boxes',
        blank=True,
        null=True,
        verbose_name=_('Current location'),
    )
    destination = models.ForeignKey(
        StockLocation,
        on_delete=models.SET_NULL,
        related_name='vhc_destination_boxes',
        blank=True,
        null=True,
        verbose_name=_('Destination'),
    )
    note = models.TextField(blank=True, max_length=500, verbose_name=_('Note'))
    status = models.CharField(
        max_length=30, choices=BoxStatus.choices, default=BoxStatus.PACKED
    )
    source = models.CharField(
        max_length=30,
        choices=BoxSource.choices,
        default=BoxSource.DONATION_PURCHASE,
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='vhc_boxes_created',
        blank=True,
        null=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='vhc_boxes_updated',
        blank=True,
        null=True,
    )
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['-created', '-pk']
        verbose_name = _('VHC Box')
        verbose_name_plural = _('VHC Boxes')

    def __str__(self):
        return self.box_number

    @staticmethod
    def get_api_url():
        return reverse('api-vhc-box-list')

    @property
    def barcode(self):
        return self.box_number

    def clean(self):
        """Validate relationships between shipment and pallet."""
        super().clean()
        if self.pallet and self.shipment and self.pallet.shipment_id != self.shipment_id:
            raise ValidationError({
                'pallet': _('Selected pallet does not belong to the selected shipment')
            })
        if self.pallet and not self.shipment:
            self.shipment = self.pallet.shipment


class BoxEventAction(models.TextChoices):
    """Audited box actions."""

    CREATED = 'CREATED', _('Created')
    EDITED = 'EDITED', _('Edited')
    MOVED = 'MOVED', _('Moved')
    PALLETIZED = 'PALLETIZED', _('Palletized')
    DISTRIBUTED = 'DISTRIBUTED', _('Distributed')
    RETURNED = 'RETURNED', _('Returned')
    LOST = 'LOST', _('Marked lost')
    CLOSED = 'CLOSED', _('Closed / empty')


class BoxEvent(InvenTree.models.InvenTreeModel):
    """Immutable audit event for a VHC box."""

    box = models.ForeignKey(Box, on_delete=models.CASCADE, related_name='events')
    action = models.CharField(max_length=20, choices=BoxEventAction.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    from_location = models.ForeignKey(
        StockLocation,
        on_delete=models.SET_NULL,
        related_name='+',
        blank=True,
        null=True,
    )
    to_location = models.ForeignKey(
        StockLocation,
        on_delete=models.SET_NULL,
        related_name='+',
        blank=True,
        null=True,
    )
    notes = models.CharField(max_length=500, blank=True)
    changes = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-timestamp', '-pk']
        verbose_name = _('VHC Box Event')
        verbose_name_plural = _('VHC Box Events')

    def __str__(self):
        return f'{self.box.box_number}: {self.get_action_display()}'
