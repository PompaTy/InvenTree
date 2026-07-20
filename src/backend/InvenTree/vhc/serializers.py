"""REST API serializers for VHC inventory."""

from django.db import transaction

from rest_framework import serializers

from data_exporter.mixins import DataExportSerializerMixin
from InvenTree.serializers import InvenTreeModelSerializer
from stock.models import StockLocation
from vhc.models import (
    Box,
    BoxEvent,
    BoxEventAction,
    BoxSequence,
    BoxStatus,
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


class VhcLocationSerializer(InvenTreeModelSerializer):
    """Small stock-location representation used by VHC screens."""

    class Meta:
        model = StockLocation
        fields = ['pk', 'name', 'pathstring', 'external']


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

    @transaction.atomic
    def create(self, validated_data):
        """Create a box and its initial audit event."""
        request = self.context.get('request')
        user = request.user if request and request.user.is_authenticated else None
        if not validated_data.get('box_number'):
            validated_data['box_number'] = BoxSequence.next_number()
        validated_data['created_by'] = user
        validated_data['updated_by'] = user
        validated_data['revision'] = 1
        box = super().create(validated_data)
        BoxEvent.objects.create(box=box, action=BoxEventAction.CREATED, user=user)
        return box

    @transaction.atomic
    def update(self, instance, validated_data):
        """Update a box and record changed fields."""
        request = self.context.get('request')
        user = request.user if request and request.user.is_authenticated else None
        relationship_fields = {
            'team', 'shipment', 'pallet', 'current_location', 'destination'
        }
        tracked_fields = [
            'box_number', 'contents', 'team', 'shipment', 'pallet',
            'current_location', 'destination', 'note', 'status', 'source',
        ]
        changes = {}
        for field in tracked_fields:
            if field in validated_data:
                old = getattr(instance, f'{field}_id') if field in relationship_fields else getattr(instance, field)
                new_value = validated_data[field]
                new = new_value.pk if hasattr(new_value, 'pk') else new_value
                if old != new:
                    changes[field] = {'from': old, 'to': new}

        validated_data.pop('revision', None)
        validated_data['updated_by'] = user
        validated_data['revision'] = instance.revision + 1
        box = super().update(instance, validated_data)
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
