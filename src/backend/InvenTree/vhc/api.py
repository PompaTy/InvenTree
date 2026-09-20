"""REST API views for the VHC box inventory workflow."""

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from django.urls import include, path

import django_filters.rest_framework.filters as rest_filters
from django_filters.rest_framework.filterset import FilterSet
from rest_framework import serializers, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

import InvenTree.permissions
from data_exporter.mixins import DataExportViewMixin
from InvenTree.filters import SEARCH_ORDER_FILTER
from InvenTree.mixins import ListAPI, ListCreateAPI, RetrieveUpdateDestroyAPI
from vhc.models import (
    Box,
    BoxEvent,
    BoxEventAction,
    BoxStatus,
    CurrentShipmentWindow,
    Pallet,
    Shipment,
    Team,
)
from vhc.serializers import (
    BoxBulkMoveSerializer,
    BoxEventSerializer,
    BoxMoveSerializer,
    BoxSerializer,
    BoxStatusSerializer,
    CurrentShipmentWindowSerializer,
    PalletSerializer,
    RevisionConflict,
    ShipmentSerializer,
    TeamSerializer,
)


class VhcAuthenticatedApi:
    """Allow authenticated VHC operators to use workflow endpoints."""

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]


class VhcCapabilities(VhcAuthenticatedApi, APIView):
    """Describe the custom contract for the authenticated client."""

    def get(self, request, *args, **kwargs):
        """Return capabilities without depending on the upstream API version."""
        staff = bool(request.user.is_staff)
        return Response(
            {
                'version': 1,
                'features': {
                    'boxes': True,
                    'box_scan': True,
                    'bulk_move': True,
                    'structured_item_history': True,
                    'shipment_windows': True,
                },
                'actions': {
                    'read': True,
                    'create_box': True,
                    'edit_box': True,
                    'move_box': True,
                    'change_box_status': True,
                    'bulk_move': True,
                    'delete_box': True,
                    'manage_shipments': True,
                    'manage_pallets': True,
                    'manage_teams': staff,
                    'manage_shipment_windows': staff,
                },
                'stock_fields': [
                    'size',
                    'sterile',
                    'expiry_date',
                    'expiry_label',
                    'vhc_box',
                ],
                'stock_ownership': 'box',
                'item_removal': 'deletes_linked_stock',
                'revision_required': ['edit', 'move', 'status', 'bulk_move'],
                'bulk_revision_field': 'revisions',
                'sterility_choices': ['', 'S', 'NS'],
                'expiry_labels': {'S': 'ER', 'NS': 'N/A'},
            }
        )


class TeamFilter(FilterSet):
    """Filters for VHC teams."""

    active = rest_filters.BooleanFilter()

    class Meta:
        """Model metadata and serializer fields."""

        model = Team
        fields = ['active']


class TeamList(ListCreateAPI):
    """List and create VHC teams."""

    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [InvenTree.permissions.IsStaffOrReadOnlyScope]
    filterset_class = TeamFilter
    filter_backends = SEARCH_ORDER_FILTER
    search_fields = ['name', 'code']
    ordering_fields = ['display_order', 'name']


class TeamDetail(RetrieveUpdateDestroyAPI):
    """Retrieve or modify a team."""

    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [InvenTree.permissions.IsStaffOrReadOnlyScope]


class ShipmentList(VhcAuthenticatedApi, DataExportViewMixin, ListCreateAPI):
    """List and create shipments."""

    queryset = Shipment.objects.all()
    serializer_class = ShipmentSerializer
    filter_backends = SEARCH_ORDER_FILTER
    search_fields = ['reference', 'notes']
    ordering_fields = ['year', 'reference', 'status', 'departure_date', 'arrival_date']
    filterset_fields = ['year', 'kind', 'status']


class ShipmentDetail(VhcAuthenticatedApi, RetrieveUpdateDestroyAPI):
    """Retrieve or modify a shipment."""

    queryset = Shipment.objects.all()
    serializer_class = ShipmentSerializer


class PalletList(VhcAuthenticatedApi, ListCreateAPI):
    """List and create pallets."""

    queryset = Pallet.objects.select_related('shipment')
    serializer_class = PalletSerializer
    filter_backends = SEARCH_ORDER_FILTER
    search_fields = ['shipment__reference', 'notes']
    ordering_fields = ['shipment', 'number']
    filterset_fields = ['shipment', 'number']


class PalletDetail(VhcAuthenticatedApi, RetrieveUpdateDestroyAPI):
    """Retrieve or modify a pallet."""

    queryset = Pallet.objects.select_related('shipment')
    serializer_class = PalletSerializer


class CurrentShipmentWindowDetail(GenericAPIView):
    """Read, create, or clear automatic shipment assignment windows."""

    serializer_class = CurrentShipmentWindowSerializer
    permission_classes = [InvenTree.permissions.IsStaffOrReadOnlyScope]

    def get_queryset(self):
        """Return configured shipment windows."""
        return CurrentShipmentWindow.objects.select_related(
            'shipment', 'updated_by'
        ).order_by('start_date', 'end_date', 'shipment__reference')

    def get(self, request, *args, **kwargs):
        """Read the configured shipment windows."""
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        """Create a shipment and its automatic assignment window."""
        shipment_name = request.data.get('shipment_name', '').strip()
        if not shipment_name:
            return Response(
                {'shipment_name': 'Shipment name is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        shipment, _created = Shipment.objects.get_or_create(reference=shipment_name)
        serializer = self.get_serializer(
            data={
                'shipment': shipment.pk,
                'start_date': request.data.get('start_date'),
                'end_date': request.data.get('end_date'),
            }
        )
        serializer.is_valid(raise_exception=True)
        window = serializer.save(updated_by=request.user)
        return Response(
            self.get_serializer(window).data, status=status.HTTP_201_CREATED
        )

    @transaction.atomic
    def put(self, request, *args, **kwargs):
        """Update an existing shipment window."""
        instance = get_object_or_404(self.get_queryset(), pk=kwargs['pk'])
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        window = serializer.save(updated_by=request.user)
        return Response(self.get_serializer(window).data)

    def delete(self, request, *args, **kwargs):
        """Clear one shipment window, or all windows if no pk is provided."""
        if 'pk' in kwargs:
            get_object_or_404(self.get_queryset(), pk=kwargs['pk']).delete()
        else:
            CurrentShipmentWindow.objects.all().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BoxFilter(FilterSet):
    """Filters for the VHC box inventory."""

    active = rest_filters.BooleanFilter(method='filter_active')

    class Meta:
        """Model metadata and serializer fields."""

        model = Box
        fields = [
            'box_number',
            'team',
            'shipment',
            'pallet',
            'current_location',
            'destination',
            'status',
            'source',
        ]

    def filter_active(self, queryset, name, value):
        """Filter terminal box states."""
        if value is True:
            return queryset.exclude(status__in=[BoxStatus.LOST, BoxStatus.CLOSED])
        if value is False:
            return queryset.filter(status__in=[BoxStatus.LOST, BoxStatus.CLOSED])
        return queryset


BOX_QUERYSET = Box.objects.select_related(
    'team',
    'shipment',
    'pallet',
    'current_location',
    'destination',
    'created_by',
    'updated_by',
).prefetch_related('items__part', 'items__stock_item')


class BoxList(VhcAuthenticatedApi, DataExportViewMixin, ListCreateAPI):
    """Search, export, and create VHC boxes."""

    queryset = BOX_QUERYSET
    serializer_class = BoxSerializer
    filterset_class = BoxFilter
    filter_backends = SEARCH_ORDER_FILTER
    search_fields = [
        'box_number',
        'contents',
        'note',
        'team__name',
        'shipment__reference',
        'current_location__name',
        'current_location__pathstring',
        'destination__name',
        'destination__pathstring',
        'items__part__name',
        'items__part__IPN',
    ]
    ordering_fields = [
        'box_number',
        'created',
        'updated',
        'status',
        'team__name',
        'shipment__reference',
        'current_location__pathstring',
        'destination__pathstring',
    ]


class BoxDetail(VhcAuthenticatedApi, RetrieveUpdateDestroyAPI):
    """Retrieve, update, or delete a VHC box."""

    queryset = BOX_QUERYSET
    serializer_class = BoxSerializer

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """Serialize deletion with edits and report protected linked stock."""
        self.queryset = Box.objects.select_for_update()
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            raise serializers.ValidationError(
                {
                    'items': 'Linked stock is in use. Resolve its protected relationships before deleting the box.'
                }
            )


class BoxEventList(VhcAuthenticatedApi, DataExportViewMixin, ListAPI):
    """Read-only audit history for VHC boxes."""

    queryset = BoxEvent.objects.select_related(
        'box', 'user', 'from_location', 'to_location'
    )
    serializer_class = BoxEventSerializer
    filter_backends = SEARCH_ORDER_FILTER
    filterset_fields = ['box', 'action', 'user']
    search_fields = ['box__box_number', 'notes', 'user__username']
    ordering_fields = ['timestamp', 'action']


def event_action_for_status(box_status):
    """Map box status updates to audit event actions."""
    return {
        BoxStatus.DISTRIBUTED: BoxEventAction.DISTRIBUTED,
        BoxStatus.RETURNED: BoxEventAction.RETURNED,
        BoxStatus.LOST: BoxEventAction.LOST,
        BoxStatus.CLOSED: BoxEventAction.CLOSED,
        BoxStatus.PALLETIZED: BoxEventAction.PALLETIZED,
    }.get(box_status, BoxEventAction.EDITED)


class BoxMove(VhcAuthenticatedApi, GenericAPIView):
    """Move a box and create an audit event."""

    queryset = Box.objects.all()
    serializer_class = BoxMoveSerializer

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        """Move a single box."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        box = get_object_or_404(Box.objects.select_for_update(), pk=pk)
        self.check_object_permissions(request, box)
        supplied_revision = serializer.validated_data.get('revision')
        if supplied_revision != box.revision:
            raise RevisionConflict()

        old_location = box.current_location
        old_status = box.status
        box.current_location = serializer.validated_data['location']
        if 'status' in serializer.validated_data:
            box.status = serializer.validated_data['status']
        box.updated_by = request.user
        box.revision += 1
        box.full_clean()
        box.save()
        BoxSerializer.sync_stock_locations(
            box, request.user, serializer.validated_data.get('notes', '')
        )
        BoxEvent.objects.create(
            box=box,
            action=BoxEventAction.MOVED,
            user=request.user,
            from_location=old_location,
            to_location=box.current_location,
            notes=serializer.validated_data.get('notes', ''),
            changes={'status': {'from': old_status, 'to': box.status}},
        )
        return Response(BoxSerializer(box, context={'request': request}).data)


class BoxStatusUpdate(VhcAuthenticatedApi, GenericAPIView):
    """Perform a controlled box lifecycle action."""

    queryset = Box.objects.all()
    serializer_class = BoxStatusSerializer

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        """Update a box status and audit the action."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        box = get_object_or_404(Box.objects.select_for_update(), pk=pk)
        self.check_object_permissions(request, box)
        supplied_revision = serializer.validated_data.get('revision')
        if supplied_revision != box.revision:
            raise RevisionConflict()

        old_status = box.status
        box.status = serializer.validated_data['status']
        box.updated_by = request.user
        box.revision += 1
        box.save(update_fields=['status', 'updated_by', 'revision', 'updated'])
        BoxEvent.objects.create(
            box=box,
            action=event_action_for_status(box.status),
            user=request.user,
            notes=serializer.validated_data.get('notes', ''),
            changes={'status': {'from': old_status, 'to': box.status}},
        )
        return Response(BoxSerializer(box, context={'request': request}).data)


class BoxBulkMove(VhcAuthenticatedApi, GenericAPIView):
    """Move multiple boxes in one transaction."""

    queryset = Box.objects.all()
    serializer_class = BoxBulkMoveSerializer

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        """Move all selected boxes."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data['boxes']
        boxes = list(Box.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
        if len(boxes) != len(set(ids)):
            return Response(
                {'boxes': 'One or more selected boxes do not exist.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        revisions = serializer.validated_data['revisions']
        for box in boxes:
            self.check_object_permissions(request, box)
            if revisions[str(box.pk)] != box.revision:
                raise RevisionConflict()

        for box in boxes:
            old_location = box.current_location
            old_status = box.status
            box.current_location = serializer.validated_data['location']
            if 'status' in serializer.validated_data:
                box.status = serializer.validated_data['status']
            box.updated_by = request.user
            box.revision += 1
            box.save()
            BoxSerializer.sync_stock_locations(
                box, request.user, serializer.validated_data.get('notes', '')
            )
            BoxEvent.objects.create(
                box=box,
                action=BoxEventAction.MOVED,
                user=request.user,
                from_location=old_location,
                to_location=box.current_location,
                notes=serializer.validated_data.get('notes', ''),
                changes={'status': {'from': old_status, 'to': box.status}},
            )

        return Response(
            BoxSerializer(boxes, many=True, context={'request': request}).data
        )


class BoxScan(VhcAuthenticatedApi, ListAPI):
    """Resolve a scanned six-digit barcode to a box."""

    serializer_class = BoxSerializer

    def get_queryset(self):
        """Return the exact scanned box, if present."""
        barcode = self.request.query_params.get('barcode', '').strip()
        return BOX_QUERYSET.filter(box_number=barcode)


vhc_api_urls = [
    path('capabilities/', VhcCapabilities.as_view(), name='api-vhc-capabilities'),
    path(
        'team/',
        include(
            [
                path('<int:pk>/', TeamDetail.as_view(), name='api-vhc-team-detail'),
                path('', TeamList.as_view(), name='api-vhc-team-list'),
            ]
        ),
    ),
    path(
        'shipment/',
        include(
            [
                path(
                    '<int:pk>/',
                    ShipmentDetail.as_view(),
                    name='api-vhc-shipment-detail',
                ),
                path('', ShipmentList.as_view(), name='api-vhc-shipment-list'),
            ]
        ),
    ),
    path(
        'pallet/',
        include(
            [
                path('<int:pk>/', PalletDetail.as_view(), name='api-vhc-pallet-detail'),
                path('', PalletList.as_view(), name='api-vhc-pallet-list'),
            ]
        ),
    ),
    path(
        'current-shipment/',
        include(
            [
                path(
                    '<int:pk>/',
                    CurrentShipmentWindowDetail.as_view(),
                    name='api-vhc-current-shipment-detail',
                ),
                path(
                    '',
                    CurrentShipmentWindowDetail.as_view(),
                    name='api-vhc-current-shipment',
                ),
            ]
        ),
    ),
    path('box/scan/', BoxScan.as_view(), name='api-vhc-box-scan'),
    path('box/bulk-move/', BoxBulkMove.as_view(), name='api-vhc-box-bulk-move'),
    path(
        'box/<int:pk>/',
        include(
            [
                path('move/', BoxMove.as_view(), name='api-vhc-box-move'),
                path('status/', BoxStatusUpdate.as_view(), name='api-vhc-box-status'),
                path('', BoxDetail.as_view(), name='api-vhc-box-detail'),
            ]
        ),
    ),
    path('box/', BoxList.as_view(), name='api-vhc-box-list'),
    path('event/', BoxEventList.as_view(), name='api-vhc-box-event-list'),
]
