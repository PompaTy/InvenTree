"""Regression coverage for the VHC mobile API contract."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, transaction
from django.db.models.deletion import ProtectedError
from django.db.models.query import QuerySet
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse

from rest_framework.test import APIClient

from part.models import Part
from stock.models import StockItem
from users.models import ApiToken
from vhc import tests as existing_tests
from vhc.models import Box, BoxEventAction, BoxItem, Team
from vhc.serializers import BoxSerializer, RevisionConflict


class VhcContractTests(existing_tests.VhcBoxApiTests):
    """Exercise the API with disposable box and stock fixtures."""

    def test_api_token_permissions(self):
        """Mobile-style API tokens retain normal-user and staff permissions."""
        token = ApiToken.objects.create(user=self.user, name='VHC contract test')
        self.logout()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        url = reverse('api-vhc-capabilities')
        self.assertTrue(self.get(url).data['actions']['manage_teams'])
        self.user.is_staff = False
        self.user.save()
        self.assertFalse(self.get(url).data['actions']['manage_teams'])
        self.create_box()
        self.post(reverse('api-vhc-team-list'), {'name': 'Denied'}, expected_code=403)
        self.client.credentials()

    def test_capabilities_and_staff_permissions(self):
        """Advertised staff actions match actual normal-user restrictions."""
        url = reverse('api-vhc-capabilities')
        staff = self.get(url).data
        self.assertEqual(staff['version'], 1)
        self.assertTrue(staff['actions']['manage_teams'])
        self.assertEqual(staff['stock_ownership'], 'box')
        self.user.is_staff = False
        self.user.save()
        normal = self.get(url).data
        self.assertFalse(normal['actions']['manage_teams'])
        self.assertFalse(normal['actions']['manage_shipment_windows'])
        self.assertTrue(normal['actions']['edit_box'])
        self.get(reverse('api-vhc-team-list'))
        self.get(reverse('api-vhc-current-shipment'))
        self.post(
            reverse('api-vhc-team-list'),
            {'name': 'Denied', 'code': 'DENIED'},
            expected_code=403,
        )
        self.post(
            reverse('api-vhc-current-shipment'),
            {
                'shipment_name': 'Denied',
                'start_date': '2026-01-01',
                'end_date': '2026-12-31',
            },
            expected_code=403,
        )
        self.create_box()
        self.logout()
        self.get(url, expected_code=401)
        self.get(reverse('api-vhc-box-list'), expected_code=401)

    def test_edit_revision_is_required_and_conflicts_are_409(self):
        """An edit must not silently replace a newer box."""
        box = self.create_box().data
        url = reverse('api-vhc-box-detail', kwargs={'pk': box['pk']})
        self.patch(url, {'note': 'missing'}, expected_code=400)
        self.patch(url, {'note': 'saved', 'revision': 1})
        self.patch(url, {'note': 'stale', 'revision': 1}, expected_code=409)
        self.assertEqual(Box.objects.get(pk=box['pk']).note, 'saved')

    def test_serializer_rechecks_after_validation(self):
        """A change between validation and saving is rejected under the lock."""
        box = Box.objects.get(pk=self.create_box().data['pk'])
        serializer = BoxSerializer(
            box, data={'note': 'stale', 'revision': 1}, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        Box.objects.filter(pk=box.pk).update(revision=2, note='newer')
        with self.assertRaises(RevisionConflict):
            serializer.save()
        box.refresh_from_db()
        self.assertEqual(box.note, 'newer')

    def test_move_and_status_require_revision_and_missing_box_is_404(self):
        """Movement/lifecycle actions use the same concurrency contract."""
        box = self.create_box().data
        for name, body in [
            ('api-vhc-box-move', {'location': self.hn_location.pk}),
            ('api-vhc-box-status', {'status': 'CLOSED'}),
        ]:
            self.post(reverse(name, kwargs={'pk': box['pk']}), body, expected_code=400)
            self.post(
                reverse(name, kwargs={'pk': 999999}),
                {**body, 'revision': 1},
                expected_code=404,
            )

    def test_bulk_move_requires_exact_revisions_and_is_atomic(self):
        """A stale member rejects every move and every audit/stock change."""
        first = self.create_box().data
        second = self.create_box().data
        url = reverse('api-vhc-box-bulk-move')
        body = {'boxes': [first['pk'], second['pk']], 'location': self.hn_location.pk}
        self.post(url, body, expected_code=400)
        self.post(url, {**body, 'revisions': {str(first['pk']): 1}}, expected_code=400)
        revisions = {str(first['pk']): 1, str(second['pk']): 1}
        Box.objects.filter(pk=second['pk']).update(revision=2)
        self.post(url, {**body, 'revisions': revisions}, expected_code=409)
        for data in [first, second]:
            box = Box.objects.get(pk=data['pk'])
            self.assertEqual(box.current_location, self.va_location)
            self.assertEqual(box.items.get().stock_item.location, self.va_location)
            self.assertEqual(box.events.count(), 1)
        revisions[str(second['pk'])] = 2
        result = self.post(url, {**body, 'revisions': revisions}, expected_code=200)
        self.assertEqual({b['revision'] for b in result.data}, {2, 3})
        for data in result.data:
            box = Box.objects.get(pk=data['pk'])
            self.assertEqual(box.items.get().stock_item.location, self.hn_location)
            self.assertEqual(box.events.filter(action=BoxEventAction.MOVED).count(), 1)

    def test_item_metadata_changes_are_audited(self):
        """Metadata-only edits produce full before/after item history."""
        box = self.create_box().data
        url = reverse('api-vhc-box-detail', kwargs={'pk': box['pk']})
        self.patch(
            url,
            {
                'revision': 1,
                'items': [
                    {
                        'part': self.bandages.pk,
                        'quantity': 12,
                        'size': 'Small',
                        'sterile': 'NS',
                        'expiry_date': None,
                        'expiry_label': 'N/A',
                    }
                ],
            },
        )
        event = Box.objects.get(pk=box['pk']).events.get(action=BoxEventAction.EDITED)
        self.assertEqual(event.changes['items']['from'][0]['size'], 'Large')
        self.assertEqual(event.changes['items']['to'][0]['expiry_label'], 'N/A')
        self.assertEqual(event.changes['items']['to'][0]['sterile'], 'NS')
        self.assertIsNone(event.changes['items']['to'][0]['expiry_date'])

    def test_direct_boxed_stock_changes_are_rejected(self):
        """Native stock forms cannot diverge from the box-owned fields."""
        self.assignRole('stock.change')
        box = self.create_box().data
        item = BoxItem.objects.get(box_id=box['pk'])
        url = reverse('api-stock-detail', kwargs={'pk': item.stock_item_id})
        for field, value in [
            ('size', 'Tiny'),
            ('sterile', 'NS'),
            ('expiry_date', '2030-01-01'),
            ('expiry_label', 'ER'),
        ]:
            response = self.patch(url, {field: value}, expected_code=400)
            self.assertIn(field, response.data)
        self.patch(url, {'notes': 'Ordinary notes remain editable'})
        item.stock_item.refresh_from_db()
        self.assertEqual(item.stock_item.size, 'Large')

    def test_native_stock_actions_cannot_modify_boxed_stock(self):
        """Count, add, remove, and transfer cannot bypass box ownership."""
        self.assignRole('stock.change')
        self.assignRole('stock.add')
        box = self.create_box().data
        stock = BoxItem.objects.get(box_id=box['pk']).stock_item
        count = stock.tracking_info.count()
        for name, extra in [
            ('api-stock-count', {}),
            ('api-stock-add', {}),
            ('api-stock-remove', {}),
            ('api-stock-transfer', {'location': self.hn_location.pk}),
        ]:
            self.post(
                reverse(name),
                {'items': [{'pk': stock.pk, 'quantity': 2}], **extra},
                expected_code=400,
            )
            stock.refresh_from_db()
            self.assertEqual(stock.quantity, 12)
            self.assertEqual(stock.location, self.va_location)
            self.assertEqual(stock.tracking_info.count(), count)

    def test_unboxed_stock_remains_editable(self):
        """The custom restrictions do not affect ordinary stock."""
        self.assignRole('stock.change')
        self.assignRole('stock.add')
        stock = StockItem.objects.create(
            part=self.bandages, quantity=5, location=self.va_location
        )
        self.patch(
            reverse('api-stock-detail', kwargs={'pk': stock.pk}), {'size': 'Small'}
        )
        self.post(
            reverse('api-stock-count'),
            {'items': [{'pk': stock.pk, 'quantity': 7}]},
            expected_code=201,
        )
        stock.refresh_from_db()
        self.assertEqual(stock.size, 'Small')
        self.assertEqual(stock.quantity, 7)

    def test_removal_deletes_only_removed_stock(self):
        """Removing an item deletes its stock and records the complete change."""
        box = self.create_box().data
        old_stock = box['items'][0]['stock_item']
        replacement = Part.objects.create(name='Replacement')
        response = self.patch(
            reverse('api-vhc-box-detail', kwargs={'pk': box['pk']}),
            {'revision': 1, 'items': [{'part': replacement.pk, 'quantity': '1.25000'}]},
        )
        self.assertFalse(StockItem.objects.filter(pk=old_stock).exists())
        new_stock = response.data['items'][0]['stock_item']
        self.assertTrue(StockItem.objects.filter(pk=new_stock).exists())
        event = Box.objects.get(pk=box['pk']).events.get(action=BoxEventAction.EDITED)
        self.assertEqual(event.changes['items']['from'][0]['stock_item'], old_stock)
        self.delete(reverse('api-vhc-box-detail', kwargs={'pk': box['pk']}))
        self.assertFalse(StockItem.objects.filter(pk=new_stock).exists())

    def test_protected_removal_rolls_back_all_changes(self):
        """A protected stock deletion cannot leave a partially edited box."""
        box = self.create_box().data
        old_stock = box['items'][0]['stock_item']
        replacement = Part.objects.create(name='Replacement')
        original_delete = QuerySet.delete

        def protected_stock_delete(queryset):
            if queryset.model is StockItem:
                raise ProtectedError('In use', set())
            return original_delete(queryset)

        with patch.object(QuerySet, 'delete', protected_stock_delete):
            self.patch(
                reverse('api-vhc-box-detail', kwargs={'pk': box['pk']}),
                {
                    'revision': 1,
                    'note': 'Must roll back',
                    'items': [{'part': replacement.pk, 'quantity': 2}],
                },
                expected_code=400,
            )
        record = Box.objects.get(pk=box['pk'])
        self.assertEqual(record.revision, 1)
        self.assertEqual(record.note, '')
        self.assertEqual(record.items.get().stock_item_id, old_stock)
        self.assertFalse(StockItem.objects.filter(part=replacement).exists())
        self.assertEqual(record.events.count(), 1)
        with self.assertRaises(ProtectedError), transaction.atomic():
            StockItem.objects.get(pk=old_stock).delete()

    def test_invalid_shipment_window_does_not_create_orphan_shipment(self):
        """Window validation rolls back the newly created shipment."""
        from vhc.models import Shipment

        self.post(
            reverse('api-vhc-current-shipment'),
            {
                'shipment_name': 'Invalid window',
                'start_date': '2026-12-31',
                'end_date': '2026-01-01',
            },
            expected_code=400,
        )
        self.assertFalse(Shipment.objects.filter(reference='Invalid window').exists())

    def test_contract_examples(self):
        """Capture actual API responses using test-only data for client documentation."""
        examples = {
            'capabilities_staff': self.get(reverse('api-vhc-capabilities')).data
        }
        self.user.is_staff = False
        self.user.save()
        examples['capabilities_operator'] = self.get(
            reverse('api-vhc-capabilities')
        ).data
        box = self.create_box().data
        examples['created_box'] = box
        examples['scan_response'] = self.get(
            reverse('api-vhc-box-scan'), {'barcode': box['box_number']}
        ).data
        url = reverse('api-vhc-box-detail', kwargs={'pk': box['pk']})
        examples['edited_box'] = self.patch(
            url, {'revision': 1, 'note': 'Example edit'}
        ).data
        examples['stale_edit_error'] = self.patch(
            url, {'revision': 1, 'note': 'Stale'}, expected_code=409
        ).data
        examples['staff_action_denied'] = self.post(
            reverse('api-vhc-team-list'), {'name': 'Denied'}, expected_code=403
        ).data
        if output := os.environ.get('VHC_CONTRACT_EXAMPLES'):
            Path(output).write_text(json.dumps(examples, indent=2, default=str) + '\n')


class VhcConcurrentEditTests(TransactionTestCase):
    """Verify actual row locking with separate PostgreSQL connections."""

    @skipUnlessDBFeature('has_select_for_update')
    def test_edit_waits_for_lock_then_rechecks_revision(self):
        """An edit validated before another commit cannot overwrite that commit."""
        user = get_user_model().objects.create_user(username='concurrent-vhc')
        team = Team.objects.create(name='Concurrent', code='CONCURRENT')
        box = Box.objects.create(box_number='260001', team=team)
        entered = Event()
        original = BoxSerializer.update

        def observed_update(serializer, instance, data):
            entered.set()
            return original(serializer, instance, data)

        def edit_box():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(user=user)
                return client.patch(
                    reverse('api-vhc-box-detail', kwargs={'pk': box.pk}),
                    {'revision': 1, 'note': 'Losing edit'},
                    format='json',
                ).status_code
            finally:
                close_old_connections()

        with (
            patch.object(BoxSerializer, 'update', observed_update),
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            with transaction.atomic():
                locked = Box.objects.select_for_update().get(pk=box.pk)
                future = pool.submit(edit_box)
                self.assertTrue(entered.wait(15), 'Edit did not reach the lock')
                with self.assertRaises(TimeoutError):
                    future.result(timeout=0.2)
                locked.revision = 2
                locked.note = 'Winning edit'
                locked.save()
            self.assertEqual(future.result(timeout=15), 409)
        box.refresh_from_db()
        self.assertEqual(box.note, 'Winning edit')
        self.assertEqual(box.revision, 2)
