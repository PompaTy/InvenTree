"""Django admin registration for VHC inventory."""

from django.contrib import admin

from vhc.models import Box, BoxEvent, BoxItem, BoxSequence, Pallet, Shipment, Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    """Admin configuration for teams."""

    list_display = ['name', 'code', 'color', 'active', 'display_order']
    list_filter = ['active']
    search_fields = ['name', 'code']


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    """Admin configuration for shipments."""

    list_display = ['reference', 'year', 'kind', 'status', 'departure_date', 'arrival_date']
    list_filter = ['year', 'kind', 'status']
    search_fields = ['reference', 'notes']


@admin.register(Pallet)
class PalletAdmin(admin.ModelAdmin):
    """Admin configuration for pallets."""

    list_display = ['shipment', 'number']
    list_filter = ['shipment']
    search_fields = ['shipment__reference']
    autocomplete_fields = ['shipment']

class BoxItemInline(admin.TabularInline):
    """Structured part and stock records contained in a box."""

    model = BoxItem
    extra = 0
    autocomplete_fields = ['part', 'stock_item']
    readonly_fields = ['created', 'updated']


class BoxEventInline(admin.TabularInline):
    """Read-only box event history."""

    model = BoxEvent
    extra = 0
    can_delete = False
    readonly_fields = [
        'action', 'user', 'timestamp', 'from_location', 'to_location', 'notes', 'changes'
    ]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Box)
class BoxAdmin(admin.ModelAdmin):
    """Admin configuration for boxes."""

    list_display = [
        'box_number', 'team', 'status', 'shipment', 'pallet',
        'current_location', 'updated',
    ]
    list_filter = ['status', 'source', 'team', 'shipment']
    search_fields = ['box_number', 'contents', 'items__part__name', 'note']
    autocomplete_fields = ['team', 'shipment', 'pallet', 'current_location', 'destination']
    readonly_fields = [
        'contents', 'created', 'updated', 'created_by', 'updated_by', 'revision'
    ]
    inlines = [BoxItemInline, BoxEventInline]


@admin.register(BoxEvent)
class BoxEventAdmin(admin.ModelAdmin):
    """Read-only audit event administration."""

    list_display = ['box', 'action', 'user', 'timestamp', 'from_location', 'to_location']
    list_filter = ['action', 'timestamp']
    search_fields = ['box__box_number', 'notes', 'user__username']
    readonly_fields = [
        'box', 'action', 'user', 'timestamp', 'from_location', 'to_location',
        'notes', 'changes',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BoxSequence)
class BoxSequenceAdmin(admin.ModelAdmin):
    """Sequence inspection for administrators."""

    list_display = ['year', 'next_value']
