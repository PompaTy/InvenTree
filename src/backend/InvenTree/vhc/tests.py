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
        cls.assignRole('stock.view')
        cls.team = Team.objects.create(
            name='General Medicine', code='GENERAL_MEDICINE', color='#228BE6'
        )
        cls.other_team = Team.objects.create(
            name='Surgery', code='SURGERY', color='#FA5252'
        )
        cls.va_location = StockLocation.objects.create(name='VA Warehouse')
        cls.hn_location = StockLocation.objects.create(name='Honduras Warehouse')
        cls.shipment = Shipment.objects.create(reference='Container 2026-1')
        cls.other_shipment = Shipment.objects.create(reference='Container 2026-2')
        cls.pallet = Pallet.objects.create(shipment=cls.shipment, number=1)
        cls.bandages = Part.objects.create(
            name='Bandages', description='Sterile wound dressings'
        )

    def create_box(self, team=None):
        """Create a box through the public API."""
        return self.post(
            reverse('api-vhc-box-list'),
            {
                'items': [
                    {
                        'part': self.bandages.pk,
                        'quantity': 12,
                        'size': 'Large',
                        'sterile': 'S',
                        'expiry_date': '2027-06-30',
                    }
                ],
                'team': (team or self.team).pk,
                'current_location': self.va_location.pk,
                'source': 'DONATION_PURCHASE',
            },
            expected_code=201,
        )

    def ordered_box_numbers(self, ordering):
        """Return VHC box numbers for a requested API ordering."""
        response = self.get(
            reverse('api-vhc-box-list'),
            {'ordering': ordering},
            expected_code=200,
        )

        return [box['box_number'] for box in response.data]

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
        self.assertEqual(box_item.size, 'Large')
        self.assertEqual(box_item.sterile, 'S')
        self.assertEqual(box_item.expiry_date, date(2027, 6, 30))
        self.assertEqual(box_item.stock_item.size, 'Large')
        self.assertEqual(box_item.stock_item.sterile, 'S')
        self.assertEqual(box_item.stock_item.expiry_date, date(2027, 6, 30))
        self.assertEqual(response.data['items'][0]['part_detail']['name'], 'Bandages')
        self.assertEqual(response.data['items'][0]['size'], 'Large')
        self.assertEqual(response.data['items'][0]['sterile'], 'S')
        self.assertEqual(response.data['items'][0]['expiry_date'], '2027-06-30')
        self.assertEqual(box.contents, 'Bandages (12)')

        stock_response = self.get(
            reverse('api-stock-list'),
            {'part': self.bandages.pk},
            expected_code=200,
        )
        stock_data = next(
            item
            for item in stock_response.data
            if item['pk'] == box_item.stock_item_id
        )
        self.assertEqual(
            stock_data['vhc_box'],
            {
                'pk': box.pk,
                'box_number': box.box_number,
                'team_detail': {
                    'pk': self.team.pk,
                    'name': 'General Medicine',
                    'code': 'GENERAL_MEDICINE',
                    'color': '#228BE6',
                    'active': True,
                },
            },
        )
        self.assertEqual(stock_data['size'], 'Large')
        self.assertEqual(stock_data['sterile'], 'S')
        self.assertEqual(stock_data['expiry_date'], '2027-06-30')

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

    def test_stock_table_orders_by_box_number(self):
        """Stock rows can be ordered by their linked VHC box number."""
        first_box = Box.objects.get(pk=self.create_box().data['pk'])
        second_box = Box.objects.get(pk=self.create_box().data['pk'])

        ascending = self.get(
            reverse('api-stock-list'),
            {'part': self.bandages.pk, 'ordering': 'box'},
            expected_code=200,
        )
        descending = self.get(
            reverse('api-stock-list'),
            {'part': self.bandages.pk, 'ordering': '-box'},
            expected_code=200,
        )

        self.assertEqual(
            [item['vhc_box']['box_number'] for item in ascending.data],
            [first_box.box_number, second_box.box_number],
        )
        self.assertEqual(
            [item['vhc_box']['box_number'] for item in descending.data],
            [second_box.box_number, first_box.box_number],
        )

    def test_stock_table_orders_by_team_name(self):
        """Stock rows can be ordered by their linked VHC team name."""
        general_box = Box.objects.get(pk=self.create_box(team=self.team).data['pk'])
        surgery_box = Box.objects.get(
            pk=self.create_box(team=self.other_team).data['pk']
        )

        ascending = self.get(
            reverse('api-stock-list'),
            {'part': self.bandages.pk, 'ordering': 'team'},
            expected_code=200,
        )
        descending = self.get(
            reverse('api-stock-list'),
            {'part': self.bandages.pk, 'ordering': '-team'},
            expected_code=200,
        )

        self.assertEqual(
            [item['vhc_box']['box_number'] for item in ascending.data],
            [general_box.box_number, surgery_box.box_number],
        )
        self.assertEqual(
            [item['vhc_box']['box_number'] for item in descending.data],
            [surgery_box.box_number, general_box.box_number],
        )

    def test_box_table_orders_by_related_fields(self):
        """Box rows can be ordered by related table columns."""
        general_box = Box.objects.get(pk=self.create_box(team=self.team).data['pk'])
        surgery_box = Box.objects.get(
            pk=self.create_box(team=self.other_team).data['pk']
        )

        general_box.shipment = self.shipment
        general_box.current_location = self.va_location
        general_box.destination = self.hn_location
        general_box.save()

        surgery_box.shipment = self.other_shipment
        surgery_box.current_location = self.hn_location
        surgery_box.destination = self.va_location
        surgery_box.save()

        ordering_cases = [
            ('team__name', [general_box.box_number, surgery_box.box_number]),
            (
                'shipment__reference',
                [general_box.box_number, surgery_box.box_number],
            ),
            (
                'current_location__pathstring',
                [surgery_box.box_number, general_box.box_number],
            ),
            (
                'destination__pathstring',
                [general_box.box_number, surgery_box.box_number],
            ),
        ]

        for ordering, box_numbers in ordering_cases:
            with self.subTest(ordering=ordering):
                self.assertEqual(self.ordered_box_numbers(ordering), box_numbers)
                self.assertEqual(
                    self.ordered_box_numbers(f'-{ordering}'),
                    list(reversed(box_numbers)),
                )

    def test_edit_box_updates_quantity(self):
        """Editing a line item performs a native stocktake."""
        response = self.create_box()
        box = Box.objects.get(pk=response.data['pk'])
        self.patch(
            reverse('api-vhc-box-detail', kwargs={'pk': box.pk}),
            {
                'items': [
                    {
                        'part': self.bandages.pk,
                        'quantity': 20,
                        'size': 'Medium',
                        'sterile': 'NS',
                        'expiry_date': '2028-01-15',
                    }
                ],
                'revision': box.revision,
            },
            expected_code=200,
        )

        box_item = BoxItem.objects.select_related('stock_item').get(box=box)
        self.assertEqual(box_item.quantity, 20)
        self.assertEqual(box_item.size, 'Medium')
        self.assertEqual(box_item.sterile, 'NS')
        self.assertEqual(box_item.expiry_date, date(2028, 1, 15))
        self.assertEqual(box_item.stock_item.quantity, 20)
        self.assertEqual(box_item.stock_item.size, 'Medium')
        self.assertEqual(box_item.stock_item.sterile, 'NS')
        self.assertEqual(box_item.stock_item.expiry_date, date(2028, 1, 15))

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
