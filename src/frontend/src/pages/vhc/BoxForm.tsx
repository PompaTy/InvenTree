import { t } from '@lingui/core/macro';
import {
  Button,
  Card,
  Group,
  Select,
  SimpleGrid,
  Stack,
  TextInput,
  Textarea
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconDeviceFloppy, IconPackage } from '@tabler/icons-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { ApiEndpoints } from '@lib/enums/ApiEndpoints';
import { apiUrl } from '@lib/functions/Api';
import { PageDetail } from '../../components/nav/PageDetail';
import { useApi } from '../../contexts/ApiContext';
import { showApiErrorMessage } from '../../functions/notifications';
import {
  type VhcBox,
  type VhcLocation,
  type VhcPallet,
  type VhcShipment,
  type VhcTeam,
  apiResults,
  locationLabel
} from './types';

const STATUS_OPTIONS = [
  { value: 'PACKED', label: t`Packed` },
  { value: 'PALLETIZED', label: t`Palletized` },
  { value: 'IN_TRANSIT', label: t`In transit` },
  { value: 'HONDURAS_WAREHOUSE', label: t`Honduras warehouse` },
  { value: 'DISTRIBUTED', label: t`Distributed` },
  { value: 'RETURNED', label: t`Returned` },
  { value: 'LOST', label: t`Lost` },
  { value: 'CLOSED', label: t`Closed / empty` }
];

const SOURCE_OPTIONS = [
  { value: 'DONATION_PURCHASE', label: t`Donation / purchase` },
  { value: 'CONTAINER_ARRIVAL', label: t`Container arrival` },
  { value: 'RETURNED_INVENTORY', label: t`Returned inventory` },
  { value: 'HONDURAS_PURCHASE', label: t`Local Honduras purchase` },
  { value: 'ADJUSTMENT', label: t`Stock adjustment` }
];

interface BoxFormValues {
  box_number: string;
  contents: string;
  team: string;
  other_team_description: string;
  shipment: string | null;
  pallet: string | null;
  current_location: string | null;
  destination: string | null;
  note: string;
  status: string;
  source: string;
}

function nullablePk(value: string | null) {
  return value ? Number(value) : null;
}

export default function BoxForm() {
  const { id } = useParams();
  const boxId = id ? Number(id) : null;
  const editing = boxId !== null;
  const api = useApi();
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [revision, setRevision] = useState<number | null>(null);
  const [teams, setTeams] = useState<VhcTeam[]>([]);
  const [shipments, setShipments] = useState<VhcShipment[]>([]);
  const [pallets, setPallets] = useState<VhcPallet[]>([]);
  const [locations, setLocations] = useState<VhcLocation[]>([]);

  const form = useForm<BoxFormValues>({
    initialValues: {
      box_number: '',
      contents: '',
      team: '',
      other_team_description: '',
      shipment: null,
      pallet: null,
      current_location: null,
      destination: null,
      note: '',
      status: 'PACKED',
      source: 'DONATION_PURCHASE'
    },
    validate: {
      box_number: (value) =>
        value && !/^\d{6}$/.test(value) ? t`Use exactly six digits` : null,
      contents: (value) => (value.trim() ? null : t`Contents are required`),
      team: (value) => (value ? null : t`Team is required`)
    }
  });

  useEffect(() => {
    Promise.all([
      api.get(apiUrl(ApiEndpoints.vhc_team_list), { params: { active: true, limit: 1000 } }),
      api.get(apiUrl(ApiEndpoints.vhc_shipment_list), { params: { limit: 1000 } }),
      api.get(apiUrl(ApiEndpoints.vhc_pallet_list), { params: { limit: 1000 } }),
      api.get(apiUrl(ApiEndpoints.stock_location_list), { params: { limit: 1000 } })
    ])
      .then(([teamResponse, shipmentResponse, palletResponse, locationResponse]) => {
        const loadedTeams = apiResults<VhcTeam>(teamResponse.data);
        const loadedLocations = apiResults<VhcLocation>(locationResponse.data);
        setTeams(loadedTeams);
        setShipments(apiResults<VhcShipment>(shipmentResponse.data));
        setPallets(apiResults<VhcPallet>(palletResponse.data));
        setLocations(loadedLocations);

        if (!editing) {
          if (loadedTeams.length === 1) {
            form.setFieldValue('team', String(loadedTeams[0].pk));
          }
          const vaWarehouse = loadedLocations.find(
            (location) => location.name.toLowerCase() === 'va warehouse'
          );
          if (vaWarehouse) {
            form.setFieldValue('current_location', String(vaWarehouse.pk));
          }
        }
      })
      .catch((error) => showApiErrorMessage({ error, title: t`Could not load box choices` }));
  }, [editing]);

  useEffect(() => {
    if (!boxId) return;
    api
      .get<VhcBox>(apiUrl(ApiEndpoints.vhc_box_list, boxId))
      .then(({ data }) => {
        setRevision(data.revision);
        form.setValues({
          box_number: data.box_number,
          contents: data.contents,
          team: String(data.team),
          other_team_description: data.other_team_description,
          shipment: data.shipment ? String(data.shipment) : null,
          pallet: data.pallet ? String(data.pallet) : null,
          current_location: data.current_location ? String(data.current_location) : null,
          destination: data.destination ? String(data.destination) : null,
          note: data.note,
          status: data.status,
          source: data.source
        });
      })
      .catch((error) => showApiErrorMessage({ error, title: t`Could not load box` }));
  }, [boxId]);

  const palletOptions = useMemo(
    () =>
      pallets
        .filter((pallet) => !form.values.shipment || pallet.shipment === Number(form.values.shipment))
        .map((pallet) => ({ value: String(pallet.pk), label: pallet.display_name })),
    [pallets, form.values.shipment]
  );

  const selectedTeam = teams.find((team) => String(team.pk) === form.values.team);

  const save = form.onSubmit((values) => {
    setSaving(true);
    const payload = {
      ...values,
      box_number: values.box_number.trim(),
      contents: values.contents.trim(),
      team: Number(values.team),
      shipment: nullablePk(values.shipment),
      pallet: nullablePk(values.pallet),
      current_location: nullablePk(values.current_location),
      destination: nullablePk(values.destination),
      ...(revision !== null ? { revision } : {})
    };
    const request = editing
      ? api.patch<VhcBox>(apiUrl(ApiEndpoints.vhc_box_list, boxId), payload)
      : api.post<VhcBox>(apiUrl(ApiEndpoints.vhc_box_list), payload);

    request
      .then(({ data }) => {
        notifications.show({
          color: 'green',
          title: editing ? t`Box updated` : t`Box packed`,
          message: t`Box ${data.box_number} was saved`
        });
        navigate(`/boxes/${data.pk}`);
      })
      .catch((error) => showApiErrorMessage({ error, title: t`Could not save box` }))
      .finally(() => setSaving(false));
  });

  return (
    <Stack>
      <PageDetail
        title={editing ? t`Edit box` : t`Pack a box`}
        subtitle={editing ? form.values.box_number : t`Record a packed box and its starting location`}
        icon={<IconPackage />}
      />
      <Card withBorder p='md'>
        <form onSubmit={save}>
          <Stack>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <TextInput
                label={t`Box number`}
                description={editing ? undefined : t`Leave blank to assign the next annual number`}
                maxLength={6}
                inputMode='numeric'
                {...form.getInputProps('box_number')}
              />
              <Select
                label={t`Team`}
                required
                searchable
                data={teams.map((team) => ({ value: String(team.pk), label: team.name }))}
                {...form.getInputProps('team')}
              />
            </SimpleGrid>
            {selectedTeam?.code === 'OTHER' && (
              <TextInput label={t`Other team`} {...form.getInputProps('other_team_description')} />
            )}
            <Textarea label={t`Contents`} required minRows={3} maxLength={500} {...form.getInputProps('contents')} />
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <Select
                label={t`Shipment`}
                clearable
                searchable
                data={shipments.map((shipment) => ({ value: String(shipment.pk), label: shipment.reference }))}
                {...form.getInputProps('shipment')}
                onChange={(value) => {
                  form.setFieldValue('shipment', value);
                  form.setFieldValue('pallet', null);
                }}
              />
              <Select label={t`Pallet`} clearable searchable disabled={!form.values.shipment} data={palletOptions} {...form.getInputProps('pallet')} />
              <Select
                label={t`Current location`}
                clearable
                searchable
                data={locations.map((location) => ({ value: String(location.pk), label: locationLabel(location) }))}
                {...form.getInputProps('current_location')}
              />
              <Select
                label={t`Destination`}
                clearable
                searchable
                data={locations.map((location) => ({ value: String(location.pk), label: locationLabel(location) }))}
                {...form.getInputProps('destination')}
              />
              <Select label={t`Source`} data={SOURCE_OPTIONS} {...form.getInputProps('source')} />
              <Select label={t`Status`} data={STATUS_OPTIONS} {...form.getInputProps('status')} />
            </SimpleGrid>
            <Textarea label={t`Note`} minRows={2} maxLength={500} {...form.getInputProps('note')} />
            <Group justify='flex-end'>
              <Button variant='default' onClick={() => navigate(editing ? `/boxes/${boxId}` : '/boxes')}>
                {t`Cancel`}
              </Button>
              <Button type='submit' loading={saving} leftSection={<IconDeviceFloppy />}>
                {t`Save box`}
              </Button>
            </Group>
          </Stack>
        </form>
      </Card>
    </Stack>
  );
}
