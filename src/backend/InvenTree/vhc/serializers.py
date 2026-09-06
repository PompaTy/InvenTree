"""REST API serializers for VHC inventory."""

from decimal import Decimal

from django.db import transaction

from rest_framework import serializers
from rest_framework.fields import empty

from data_exporter.mixins import DataExportSerializerMixin
from InvenTree.serializers import InvenTreeModelSerializer
from part.models import Part
from stock.models import StockItem, StockLocation, StockSterility
from vhc.models import (
    Box,
    BoxEvent,
    BoxEventAction,
    BoxItem,
    BoxSequence,
    BoxStatus,
    CurrentShipmentWindow,
    Pallet,
    Shipment,
    Team,
)


class TeamSerializer(InvenTreeModelSerializer):
    """Serializer for a packing team."""

    class Meta:
        model = Team
        fields = ['pk', 'name', 'code', 'color', 'active', 'display_order']


class ShipmentSerializer(InvenTreeModelSerializer):
    """Serializer for a shipment."""

    status_text = serializers.CharField(source='get_status_display', read_only=True)
    kind_text = serializers.CharField(source='get_kind_display', read_only=True)

    class Meta:
        model = Shipment
        fields = [
            'pk',
            'reference',
            'year',
            'kind',
            'kind_text',
            'status',
            'status_text',
            'departure_date',
            'arrival_date',
            'notes',
        ]


class PalletSerializer(InvenTreeModelSerializer):
    """Serializer for a pallet."""

    shipment_detail = ShipmentSerializer(source='shipment', read_only=True)
    display_name = serializers.CharField(source='__str__', read_only=True)

    class Meta:
        model = Pallet
        fields = ['pk', 'shipment', 'shipment_detail', 'number', 'display_name', 'notes']


class CurrentShipmentWindowSerializer(InvenTreeModelSerializer):
    """Serializer for the automatic box shipment assignment window."""

    shipment_detail = ShipmentSerializer(source='shipment', read_only=True)
    updated_by_name = serializers.CharField(
        source='updated_by.username', read_only=True, allow_null=True
    )

    class Meta:
        model = CurrentShipmentWindow
        fields = [
            'pk',
            'shipment',
            'shipment_detail',
            'start_date',
            'end_date',
            'updated',
            'updated_by',
            'updated_by_name',
        ]
        read_only_fields = ['updated', 'updated_by']

    def validate(self, attrs):
        """Ensure the date range is valid."""
        start_date = attrs.get(
            'start_date', getattr(self.instance, 'start_date', None)
        )
        end_date = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({
                'end_date': 'End date must be on or after the start date.'
            })
        return attrs


class VhcLocationSerializer(InvenTreeModelSerializer):
    """Small stock-location representation used by VHC screens."""

    class Meta:
        model = StockLocation
        fields = ['pk', 'name', 'pathstring', 'external']

class BoxPartSerializer(InvenTreeModelSerializer):
    """Compact part representation for a box line item."""

    class Meta:
        model = Part
        fields = ['pk', 'name', 'description', 'IPN', 'revision', 'units']
        read_only_fields = fields


class BoxItemSerializer(serializers.Serializer):
    """Nested input and output representation for a box line item."""

    pk = serializers.IntegerField(read_only=True)
    part = serializers.PrimaryKeyRelatedField(
        queryset=Part.objects.all(), required=False, allow_null=True
    )
    part_name = serializers.CharField(
        write_only=True, required=False, allow_blank=False, max_length=100
    )
    part_detail = BoxPartSerializer(source='part', read_only=True)
    stock_item = serializers.PrimaryKeyRelatedField(read_only=True)
    quantity = serializers.DecimalField(
        max_digits=15, decimal_places=5, min_value=Decimal('0.00001')
    )
    size = serializers.CharField(
        required=False, allow_blank=True, max_length=100, default=''
    )
    sterile = serializers.ChoiceField(
        choices=StockSterility.choices, required=False, allow_blank=True, default=''
    )
    expiry_date = serializers.DateField(
        required=False, allow_null=True, default=None
    )
    expiry_label = serializers.ChoiceField(choices=['ER', 'N/A'], required=False, allow_blank=True, default='')
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)

    def validate(self, attrs):
        """Require either an existing part selection or a new part name."""
        label = attrs.get('expiry_label', '')
        if label and (attrs.get('expiry_date') or label != {'S': 'ER', 'NS': 'N/A'}.get(attrs.get('sterile'))):
            raise serializers.ValidationError({'expiry_label': 'Use ER for sterile items or N/A for non-sterile items, or enter a date without a label.'})
        if attrs.get('part') is None:
            name = attrs.get('part_name', '').strip()
            if not name:
                raise serializers.ValidationError({
                    'part_name': 'Select an existing part or enter a new part name.'
                })
            attrs['part_name'] = name
        return attrs


class BoxSerializer(DataExportSerializerMixin, InvenTreeModelSerializer):
    """Serializer for a VHC inventory box."""

    box_number = serializers.CharField(
        required=False, allow_blank=True, max_length=6
    )
    team_detail = TeamSerializer(source='team', read_only=True)
    shipment_detail = ShipmentSerializer(source='shipment', read_only=True)
    pallet_detail = PalletSerializer(source='pallet', read_only=True)
    current_location_detail = VhcLocationSerializer(
        source='current_location', read_only=True
    )
    destination_detail = VhcLocationSerializer(source='destination', read_only=True)
    items = BoxItemSerializer(many=True, read_only=True)
    status_text = serializers.CharField(source='get_status_display', read_only=True)
    source_text = serializers.CharField(source='get_source_display', read_only=True)
    barcode = serializers.CharField(read_only=True)
    created_by_name = serializers.CharField(
        source='created_by.username', read_only=True, allow_null=True
    )
    updated_by_name = serializers.CharField(
        source='updated_by.username', read_only=True, allow_null=True
    )

    export_child_fields = [
        'team_detail.name',
        'shipment_detail.reference',
        'pallet_detail.number',
        'current_location_detail.pathstring',
        'destination_detail.pathstring',
    ]

    class Meta:
        model = Box
        fields = [
            'pk',
            'box_number',
            'barcode',
            'contents',
            'items',
            'team',
            'team_detail',
            'other_team_description',
            'shipment',
            'shipment_detail',
            'pallet',
            'pallet_detail',
            'current_location',
            'current_location_detail',
            'destination',
            'destination_detail',
            'note',
            'status',
            'status_text',
            'source',
            'source_text',
            'created',
            'updated',
            'created_by',
            'created_by_name',
            'updated_by',
            'updated_by_name',
            'revision',
        ]
        read_only_fields = [
            'barcode',
            'contents',
            'created',
            'updated',
            'created_by',
            'updated_by',
        ]
        extra_kwargs = {'box_number': {'required': False, 'allow_blank': True}}

    def validate(self, attrs):
        """Validate revision and pallet-to-shipment consistency."""
        instance = self.instance
        incoming_revision = attrs.get('revision')
        if instance and incoming_revision is not None and incoming_revision != instance.revision:
            raise serializers.ValidationError({
                'revision': 'This box was changed by another user. Reload and try again.'
            })

        pallet = attrs.get('pallet', getattr(instance, 'pallet', None))
        shipment = attrs.get('shipment', getattr(instance, 'shipment', None))
        if pallet and shipment and pallet.shipment_id != shipment.pk:
            raise serializers.ValidationError({
                'pallet': 'Selected pallet does not belong to the selected shipment.'
            })
        if pallet and not shipment:
            attrs['shipment'] = pallet.shipment

        return attrs

    def run_validation(self, data=empty):
        """Validate nested items separately from the Box model instance."""
        items_input = empty
        if isinstance(data, dict) and 'items' in data:
            data = data.copy()
            items_input = data.pop('items')

        validated_data = super().run_validation(data)
        if self.instance is None and items_input is empty:
            raise serializers.ValidationError({
                'items': 'Add at least one item to the box.'
            })
        if items_input is not empty:
            item_serializer = BoxItemSerializer(
                data=items_input, many=True, context=self.context
            )
            item_serializer.is_valid(raise_exception=True)
            if not item_serializer.validated_data:
                raise serializers.ValidationError({
                    'items': 'Add at least one item to the box.'
                })
            validated_data['items'] = item_serializer.validated_data
        return validated_data

    def _resolve_part(self, item_data, user):
        """Resolve an existing part, or create one from a new item name."""
        part = item_data.get('part')
        if part is None:
            name = item_data['part_name'].strip()
            matches = Part.objects.select_for_update().filter(name__iexact=name)
            match_count = matches.count()
            if match_count > 1:
                raise serializers.ValidationError({
                    'items': f'Multiple parts are named "{name}". Select the intended part from the suggestions.'
                })
            part = matches.first()
            if part is None:
                part = Part(
                    name=name,
                    description='Created automatically from VHC box inventory',
                    creation_user=user,
                )
                part.save()

        if part.virtual:
            raise serializers.ValidationError({
                'items': f'Virtual part "{part.name}" cannot be added to stock.'
            })
        return part

    @staticmethod
    def _stock_note(box):
        return f'Inventory assigned to VHC box {box.box_number}'

    @staticmethod
    def _format_quantity(quantity):
        return format(quantity, 'f').rstrip('0').rstrip('.')

    @classmethod
    def sync_stock_locations(cls, box, user, notes=''):
        """Keep each line item's native stock record at the box location."""
        stock_note = notes or cls._stock_note(box)
        for box_item in box.items.select_related('stock_item'):
            stock_item = box_item.stock_item
            if stock_item.location_id == box.current_location_id:
                continue
            if box.current_location is not None:
                stock_item.move(box.current_location, stock_note, user)
            else:
                stock_item.location = None
                stock_item.save(user=user, notes=stock_note)

    def _sync_items(self, box, items_data, user):
        """Synchronize nested line items and their dedicated stock records."""
        existing = {
            item.part_id: item
            for item in box.items.select_related('part', 'stock_item')
        }
        retained_ids = []
        selected_parts = set()
        stock_note = self._stock_note(box)

        for item_data in items_data:
            part = self._resolve_part(item_data, user)
            if part.pk in selected_parts:
                raise serializers.ValidationError({
                    'items': f'Part "{part.name}" is listed more than once.'
                })
            selected_parts.add(part.pk)
            quantity = item_data['quantity']
            size = item_data.get('size', '').strip()
            sterile = item_data.get('sterile', '')
            expiry_date = item_data.get('expiry_date')
            expiry_label = item_data.get('expiry_label', '')
            box_item = existing.get(part.pk)

            if box_item is None:
                stock_item = StockItem(
                    part=part,
                    quantity=quantity,
                    location=box.current_location,
                    size=size,
                    sterile=sterile,
                    expiry_date=expiry_date,
                    expiry_label=expiry_label,
                )
                stock_item.save(user=user, notes=stock_note)
                box_item = BoxItem.objects.create(
                    box=box,
                    part=part,
                    stock_item=stock_item,
                    quantity=quantity,
                    size=size,
                    sterile=sterile,
                    expiry_date=expiry_date,
                    expiry_label=expiry_label,
                )
            else:
                stock_item = box_item.stock_item
                if stock_item.quantity != quantity:
                    stock_item.stocktake(quantity, user, notes=stock_note)

                stock_item.size = size
                stock_item.sterile = sterile
                stock_item.expiry_date = expiry_date
                stock_item.expiry_label = expiry_label
                stock_item.save(user=user, notes=stock_note)

                box_item.quantity = quantity
                box_item.size = size
                box_item.sterile = sterile
                box_item.expiry_date = expiry_date
                box_item.expiry_label = expiry_label
                box_item.save(
                    update_fields=[
                        'quantity',
                        'size',
                        'sterile',
                        'expiry_date',
                        'expiry_label',
                        'updated',
                    ]
                )

            retained_ids.append(box_item.pk)

        box.items.exclude(pk__in=retained_ids).delete()
        self.sync_stock_locations(box, user)

        summary = ', '.join(
            f'{item.part.name} ({self._format_quantity(item.quantity)})'
            for item in box.items.select_related('part')
        )[:500]
        Box.objects.filter(pk=box.pk).update(contents=summary)
        box.contents = summary

    @transaction.atomic
    def create(self, validated_data):
        """Create a box, its parts, stock records, and initial audit event."""
        items_data = validated_data.pop('items')
        request = self.context.get('request')
        user = request.user if request and request.user.is_authenticated else None
        if not validated_data.get('box_number'):
            validated_data['box_number'] = BoxSequence.next_number()
        if not validated_data.get('shipment'):
            current_window = CurrentShipmentWindow.current_for_date()
            if current_window:
                validated_data['shipment'] = current_window.shipment
        validated_data['created_by'] = user
        validated_data['updated_by'] = user
        validated_data['revision'] = 1
        box = super().create(validated_data)
        self._sync_items(box, items_data, user)
        BoxEvent.objects.create(
            box=box,
            action=BoxEventAction.CREATED,
            user=user,
            changes={'items': box.contents},
        )
        return box

    @transaction.atomic
    def update(self, instance, validated_data):
        """Update a box, its line items, native stock, and audit history."""
        request = self.context.get('request')
        user = request.user if request and request.user.is_authenticated else None
        items_data = validated_data.pop('items', None)
        relationship_fields = {
            'team', 'shipment', 'pallet', 'current_location', 'destination'
        }
        tracked_fields = [
            'box_number', 'team', 'shipment', 'pallet', 'current_location',
            'destination', 'note', 'status', 'source',
        ]
        changes = {}
        for field in tracked_fields:
            if field in validated_data:
                old = (
                    getattr(instance, f'{field}_id')
                    if field in relationship_fields
                    else getattr(instance, field)
                )
                new_value = validated_data[field]
                new = new_value.pk if hasattr(new_value, 'pk') else new_value
                if old != new:
                    changes[field] = {'from': old, 'to': new}

        old_contents = instance.contents
        validated_data.pop('revision', None)
        validated_data['updated_by'] = user
        validated_data['revision'] = instance.revision + 1
        box = super().update(instance, validated_data)

        if items_data is not None:
            self._sync_items(box, items_data, user)
        else:
            self.sync_stock_locations(box, user)

        if old_contents != box.contents:
            changes['items'] = {'from': old_contents, 'to': box.contents}
        if changes:
            BoxEvent.objects.create(
                box=box, action=BoxEventAction.EDITED, user=user, changes=changes
            )
        return box

class BoxEventSerializer(DataExportSerializerMixin, InvenTreeModelSerializer):
    """Read-only serializer for box history."""

    action_text = serializers.CharField(source='get_action_display', read_only=True)
    user_name = serializers.CharField(source='user.username', read_only=True)
    from_location_detail = VhcLocationSerializer(source='from_location', read_only=True)
    to_location_detail = VhcLocationSerializer(source='to_location', read_only=True)

    class Meta:
        model = BoxEvent
        fields = [
            'pk', 'box', 'action', 'action_text', 'user', 'user_name',
            'timestamp', 'from_location', 'from_location_detail', 'to_location',
            'to_location_detail', 'notes', 'changes',
        ]
        read_only_fields = fields


class BoxMoveSerializer(serializers.Serializer):
    """Input for moving a box to another location."""

    location = serializers.PrimaryKeyRelatedField(queryset=StockLocation.objects.all())
    status = serializers.ChoiceField(choices=BoxStatus.choices, required=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
    revision = serializers.IntegerField(required=False)


class BoxStatusSerializer(serializers.Serializer):
    """Input for a controlled box status change."""

    status = serializers.ChoiceField(choices=BoxStatus.choices)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
    revision = serializers.IntegerField(required=False)


class BoxBulkMoveSerializer(BoxMoveSerializer):
    """Input for moving multiple boxes."""

    boxes = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
