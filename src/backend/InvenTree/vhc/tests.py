"""Tests for the VHC box inventory workflow."""

from datetime import date

from django.urls import reverse

from InvenTree.unit_test import InvenTreeAPITestCase
from part.models import Part
from stock.models import StockItem, StockLocation
from vhc.models import (
    Box, BoxEvent, BoxEventAction, BoxItem, Pallet, Shipment, Team,
)


class VhcBoxApiTests(InvenTreeAPITestCase):
    """Exercise box creation, scanning, movement, and concurrency controls."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.team = Team.objects.create(
            name='General Medicine', code='GENERAL_MEDICINE', color='#228BE6'
        )
        cls.va_location = StockLocation.objects.create(name='VA Warehouse')
        cls.hn_location = StockLocation.objects.create(name='Honduras Warehouse')
        cls.shipment = Shipment.objects.create(reference='Container 2026-1')
        cls.other_shipment = Shipment.objects.create(reference='Container 2026-2')
        cls.pallet = Pallet.objects.create(shipment=cls.shipment, number=1)
        cls.bandages = Part.objects.create(
            name='Bandages', description='Sterile wound dressings'
        )

    def create_box(self):
        """Create a box through the public API."""
        return self.post(
            reverse('api-vhc-box-list'),
            {
                'items': [{'part': self.bandages.pk, 'quantity': 12}],
                'team': self.team.pk,
                'current_location': self.va_location.pk,
                'source': 'DONATION_PURCHASE',
            },
            expected_code=201,
        )

    def test_create_and_scan_box(self):
        """A created box receives an annual number and initial audit event."""
        response = self.create_box()
        box = Box.objects.get(pk=response.data['pk'])

        self.assertRegex(box.box_number, rf'^{date.today().year % 100:02d}\d{{4}}$')
        self.assertEqual(box.created_by, self.user)
        self.assertEqual(box.events.count(), 1)
        self.assertEqual(box.events.get().action, BoxEventAction.CREATED)

        scan = self.get(
            reverse('api-vhc-box-scan'),
            {'barcode': box.box_number},
            expected_code=200,
        )
        self.assertEqual(len(scan.data), 1)
        self.assertEqual(scan.data[0]['pk'], box.pk)

    def test_create_box_updates_part_stock(self):
        """Structured items create dedicated native stock records."""
        response = self.create_box()
        box = Box.objects.get(pk=response.data['pk'])
        box_item = BoxItem.objects.select_related('stock_item').get(box=box)

        self.assertEqual(box_item.part, self.bandages)
        self.assertEqual(box_item.quantity, 12)
        self.assertEqual(box_item.stock_item.quantity, 12)
        self.assertEqual(box_item.stock_item.location, self.va_location)
        self.assertEqual(response.data['items'][0]['part_detail']['name'], 'Bandages')
        self.assertEqual(box.contents, 'Bandages (12)')

    def test_unknown_item_creates_part_and_stock(self):
        """An unmatched item name creates a reusable part and stock record."""
        response = self.post(
            reverse('api-vhc-box-list'),
            {
                'items': [{'part_name': 'Trauma shears', 'quantity': 4}],
                'team': self.team.pk,
                'current_location': self.va_location.pk,
            },
            expected_code=201,
        )

        part = Part.objects.get(name='Trauma shears')
        box_item = BoxItem.objects.get(box_id=response.data['pk'], part=part)
        stock_item = StockItem.objects.get(pk=box_item.stock_item_id)
        self.assertEqual(stock_item.quantity, 4)
        self.assertEqual(stock_item.location, self.va_location)

    def test_edit_box_updates_quantity(self):
        """Editing a line item performs a native stocktake."""
        response = self.create_box()
        box = Box.objects.get(pk=response.data['pk'])
        self.patch(
            reverse('api-vhc-box-detail', kwargs={'pk': box.pk}),
            {
                'items': [{'part': self.bandages.pk, 'quantity': 20}],
                'revision': box.revision,
            },
            expected_code=200,
        )

        box_item = BoxItem.objects.select_related('stock_item').get(box=box)
        self.assertEqual(box_item.quantity, 20)
        self.assertEqual(box_item.stock_item.quantity, 20)

    def test_box_requires_items(self):
        """A box cannot be created without at least one structured item."""
        response = self.post(
            reverse('api-vhc-box-list'),
            {'team': self.team.pk},
            expected_code=400,
        )
        self.assertIn('items', response.data)

    def test_move_box_records_history(self):
        """Moving a box updates its location and leaves an audit trail."""
        box = Box.objects.get(pk=self.create_box().data['pk'])
        response = self.post(
            reverse('api-vhc-box-move', kwargs={'pk': box.pk}),
            {
                'location': self.hn_location.pk,
                'status': 'IN_TRANSIT',
                'notes': 'Loaded for shipment',
                'revision': box.revision,
            },
            expected_code=200,
        )

        box.refresh_from_db()
        self.assertEqual(box.current_location, self.hn_location)
        self.assertEqual(box.status, 'IN_TRANSIT')
        self.assertEqual(
            box.items.get().stock_item.location, self.hn_location
        )
        self.assertEqual(response.data['revision'], 2)
        event = BoxEvent.objects.filter(box=box, action=BoxEventAction.MOVED).get()
        self.assertEqual(event.from_location, self.va_location)
        self.assertEqual(event.to_location, self.hn_location)

    def test_stale_revision_is_rejected(self):
        """Lifecycle actions reject edits made from stale screens."""
        box = Box.objects.get(pk=self.create_box().data['pk'])
        response = self.post(
            reverse('api-vhc-box-status', kwargs={'pk': box.pk}),
            {'status': 'CLOSED', 'revision': box.revision + 1},
            expected_code=409,
        )
        self.assertIn('revision', response.data)

    def test_pallet_must_match_shipment(self):
        """The selected pallet must belong to the selected shipment."""
        response = self.post(
            reverse('api-vhc-box-list'),
            {
                'items': [{'part': self.bandages.pk, 'quantity': 1}],
                'team': self.team.pk,
                'shipment': self.other_shipment.pk,
                'pallet': self.pallet.pk,
            },
            expected_code=400,
        )
        self.assertIn('pallet', response.data)
