import {
  ActionIcon,
  Button,
  Card,
  Divider,
  Group,
  Modal,
  SimpleGrid,
  Stack,
  Text,
  TextInput
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import {
  IconCalendarTime,
  IconDeviceFloppy,
  IconPlus,
  IconTrash
} from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';

import { ApiEndpoints } from '@lib/enums/ApiEndpoints';
import { apiUrl } from '@lib/functions/Api';
import { useApi } from '../../contexts/ApiContext';
import { showApiErrorMessage } from '../../functions/notifications';
import { useUserState } from '../../states/UserState';
import { type VhcCurrentShipmentWindow, apiResults } from './types';

interface ShipmentDraft {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
}

function todayString() {
  return new Date().toISOString().slice(0, 10);
}

function newDraft(): ShipmentDraft {
  return {
    id: Date.now() + Math.floor(Math.random() * 1000),
    name: '',
    start_date: todayString(),
    end_date: todayString()
  };
}

function dateRangeLabel(window: VhcCurrentShipmentWindow) {
  return `${window.start_date} to ${window.end_date}`;
}

export default function CurrentShipmentManager() {
  const api = useApi();
  const user = useUserState();
  const [opened, setOpened] = useState(false);
  const [windows, setWindows] = useState<VhcCurrentShipmentWindow[]>([]);
  const [drafts, setDrafts] = useState<ShipmentDraft[]>([newDraft()]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const loadShipmentWindows = useCallback(() => {
    setLoading(true);
    api
      .get(apiUrl(ApiEndpoints.vhc_current_shipment))
      .then(({ data }) =>
        setWindows(apiResults<VhcCurrentShipmentWindow>(data))
      )
      .catch((error) =>
        showApiErrorMessage({
          error,
          title: 'Could not load shipments'
        })
      )
      .finally(() => setLoading(false));
  }, [api]);

  useEffect(() => {
    if (opened) {
      loadShipmentWindows();
    }
  }, [loadShipmentWindows, opened]);

  if (!user.isStaff()) {
    return null;
  }

  const updateDraft = (id: number, changes: Partial<ShipmentDraft>) => {
    setDrafts((current) =>
      current.map((draft) =>
        draft.id === id ? { ...draft, ...changes } : draft
      )
    );
  };

  const removeDraft = (id: number) => {
    setDrafts((current) =>
      current.length === 1 ? current : current.filter((draft) => draft.id !== id)
    );
  };

  const addDraft = () => {
    setDrafts((current) => [...current, newDraft()]);
  };

  const saveShipments = () => {
    const shipments = drafts.map((draft) => ({
      ...draft,
      name: draft.name.trim()
    }));

    if (shipments.some((draft) => !draft.name)) {
      notifications.show({
        title: 'Shipment name is required',
        message: 'Each shipment needs a name before saving.',
        color: 'red'
      });
      return;
    }

    if (shipments.some((draft) => draft.end_date < draft.start_date)) {
      notifications.show({
        title: 'Check shipment dates',
        message: 'End date must be on or after the start date.',
        color: 'red'
      });
      return;
    }

    setSaving(true);
    Promise.all(
      shipments.map((draft) =>
        api.post(apiUrl(ApiEndpoints.vhc_current_shipment), {
          shipment_name: draft.name,
          start_date: draft.start_date,
          end_date: draft.end_date
        })
      )
    )
      .then((responses) => {
        setWindows((current) => [
          ...current,
          ...responses.map(({ data }) => data as VhcCurrentShipmentWindow)
        ]);
        setDrafts([newDraft()]);
        notifications.show({
          title: 'Shipments saved',
          message: 'New boxes will use these shipments during their date ranges.',
          color: 'green'
        });
      })
      .catch((error) =>
        showApiErrorMessage({
          error,
          title: 'Could not save shipments'
        })
      )
      .finally(() => setSaving(false));
  };

  const deleteWindow = (windowId: number) => {
    setDeletingId(windowId);
    api
      .delete(`${apiUrl(ApiEndpoints.vhc_current_shipment)}${windowId}/`)
      .then(() => {
        setWindows((current) =>
          current.filter((window) => window.pk !== windowId)
        );
        notifications.show({
          title: 'Shipment removed',
          message: 'That shipment date range will no longer assign boxes.',
          color: 'green'
        });
      })
      .catch((error) =>
        showApiErrorMessage({
          error,
          title: 'Could not remove shipment'
        })
      )
      .finally(() => setDeletingId(null));
  };

  return (
    <>
      <Button
        variant='default'
        leftSection={<IconCalendarTime />}
        onClick={() => setOpened(true)}
      >
        Set shipment
      </Button>
      <Modal
        opened={opened}
        onClose={() => setOpened(false)}
        title='Set shipments'
        size='xl'
      >
        <Stack>
          <Text size='sm' c='dimmed'>
            Boxes packed inside a shipment date range will be assigned to that
            shipment automatically.
          </Text>

          <Stack gap='sm'>
            <Group justify='space-between'>
              <Text fw={600}>New shipments</Text>
              <Button
                variant='light'
                leftSection={<IconPlus size={16} />}
                onClick={addDraft}
              >
                Add another shipment
              </Button>
            </Group>
            {drafts.map((draft) => (
              <Card key={draft.id} withBorder p='sm'>
                <Group align='flex-end' wrap='nowrap'>
                  <TextInput
                    label='Shipment name'
                    placeholder='e.g. Container 2026-3'
                    value={draft.name}
                    onChange={(event) =>
                      updateDraft(draft.id, {
                        name: event.currentTarget.value
                      })
                    }
                    style={{ flex: 1 }}
                  />
                  <TextInput
                    label='Start date'
                    required
                    type='date'
                    value={draft.start_date}
                    onChange={(event) =>
                      updateDraft(draft.id, {
                        start_date: event.currentTarget.value
                      })
                    }
                    w={160}
                  />
                  <TextInput
                    label='End date'
                    required
                    type='date'
                    value={draft.end_date}
                    onChange={(event) =>
                      updateDraft(draft.id, {
                        end_date: event.currentTarget.value
                      })
                    }
                    w={160}
                  />
                  <ActionIcon
                    size='lg'
                    variant='subtle'
                    color='red'
                    aria-label='Remove shipment row'
                    disabled={drafts.length === 1}
                    onClick={() => removeDraft(draft.id)}
                  >
                    <IconTrash size={18} />
                  </ActionIcon>
                </Group>
              </Card>
            ))}
            <Group justify='flex-end'>
              <Button
                leftSection={<IconDeviceFloppy size={16} />}
                loading={saving}
                onClick={saveShipments}
              >
                Save shipments
              </Button>
            </Group>
          </Stack>

          <Divider />

          <Stack gap='sm'>
            <Text fw={600}>Created shipments</Text>
            {loading ? (
              <Text c='dimmed'>Loading shipments...</Text>
            ) : windows.length === 0 ? (
              <Text c='dimmed'>No shipment date ranges have been created.</Text>
            ) : (
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                {windows.map((window) => (
                  <Card key={window.pk} withBorder p='sm'>
                    <Group justify='space-between' align='flex-start'>
                      <div>
                        <Text fw={600}>
                          {window.shipment_detail?.reference || 'Shipment'}
                        </Text>
                        <Text size='sm' c='dimmed'>
                          {dateRangeLabel(window)}
                        </Text>
                      </div>
                      <ActionIcon
                        variant='subtle'
                        color='red'
                        aria-label='Remove shipment'
                        loading={deletingId === window.pk}
                        onClick={() => deleteWindow(window.pk)}
                      >
                        <IconTrash size={18} />
                      </ActionIcon>
                    </Group>
                  </Card>
                ))}
              </SimpleGrid>
            )}
          </Stack>

          <Group justify='flex-end'>
            <Button variant='default' onClick={() => setOpened(false)}>
              Close
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
