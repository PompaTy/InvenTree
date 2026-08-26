import { t } from '@lingui/core/macro';
import {
  Anchor,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  Loader,
  Modal,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Textarea,
  Title
} from '@mantine/core';
import { IconEdit, IconMapPin, IconPackage, IconPrinter } from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { ApiEndpoints } from '@lib/enums/ApiEndpoints';
import { apiUrl } from '@lib/functions/Api';
import { QRCode } from '../../components/barcodes/QRCode';
import { PageDetail } from '../../components/nav/PageDetail';
import { useApi } from '../../contexts/ApiContext';
import { showApiErrorMessage } from '../../functions/notifications';
import {
  type VhcBox,
  type VhcBoxEvent,
  type VhcLocation,
  apiResults,
  locationLabel
} from './types';

const MOVE_STATUS_OPTIONS = [
  { value: 'PACKED', label: t`Packed` },
  { value: 'PALLETIZED', label: t`Palletized` },
  { value: 'IN_TRANSIT', label: t`In transit` },
  { value: 'HONDURAS_WAREHOUSE', label: t`Honduras warehouse` },
  { value: 'DISTRIBUTED', label: t`Distributed` },
  { value: 'RETURNED', label: t`Returned` }
];

function Fact({ label, value }: Readonly<{ label: string; value?: string | number | null }>) {
  return (
    <Stack gap={2}>
      <Text size='xs' c='dimmed' tt='uppercase' fw={600}>{label}</Text>
      <Text>{value ?? '?'}</Text>
    </Stack>
  );
}

export default function BoxDetail() {
  const { id } = useParams();
  const boxId = Number(id);
  const api = useApi();
  const navigate = useNavigate();
  const [box, setBox] = useState<VhcBox | null>(null);
  const [events, setEvents] = useState<VhcBoxEvent[]>([]);
  const [locations, setLocations] = useState<VhcLocation[]>([]);
  const [moveOpened, setMoveOpened] = useState(false);
  const [moveLocation, setMoveLocation] = useState<string | null>(null);
  const [moveStatus, setMoveStatus] = useState<string | null>(null);
  const [moveNotes, setMoveNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    Promise.all([
      api.get<VhcBox>(apiUrl(ApiEndpoints.vhc_box_list, boxId)),
      api.get(apiUrl(ApiEndpoints.vhc_box_event_list), { params: { box: boxId, limit: 1000 } }),
      api.get(apiUrl(ApiEndpoints.stock_location_list), { params: { limit: 1000 } })
    ])
      .then(([boxResponse, eventResponse, locationResponse]) => {
        setBox(boxResponse.data);
        setEvents(apiResults<VhcBoxEvent>(eventResponse.data));
        setLocations(apiResults<VhcLocation>(locationResponse.data));
      })
      .catch((error) => showApiErrorMessage({ error, title: t`Could not load box` }));
  }, [api, boxId]);

  useEffect(() => load(), [load]);

  const updateStatus = (status: string) => {
    if (!box) return;
    setSaving(true);
    api
      .post(apiUrl(ApiEndpoints.vhc_box_status, box.pk), { status, revision: box.revision })
      .then(() => load())
      .catch((error) => showApiErrorMessage({ error, title: t`Could not update status` }))
      .finally(() => setSaving(false));
  };

  const moveBox = () => {
    if (!box || !moveLocation) return;
    setSaving(true);
    api
      .post(apiUrl(ApiEndpoints.vhc_box_move, box.pk), {
        location: Number(moveLocation),
        ...(moveStatus ? { status: moveStatus } : {}),
        notes: moveNotes,
        revision: box.revision
      })
      .then(() => {
        setMoveOpened(false);
        setMoveNotes('');
        setMoveStatus(null);
        load();
      })
      .catch((error) => showApiErrorMessage({ error, title: t`Could not move box` }))
      .finally(() => setSaving(false));
  };

  if (!box) return <Loader />;

  return (
    <Stack>
      <style>{`
        @media print {
          body * { visibility: hidden !important; }
          .vhc-box-label, .vhc-box-label * { visibility: visible !important; }
          .vhc-box-label {
            position: absolute;
            inset: 0;
            width: 100%;
            border: 0 !important;
          }
        }
      `}</style>
      <PageDetail
        title={t`Box ${box.box_number}`}
        subtitle={box.contents}
        icon={<IconPackage />}
        badges={[<Badge key='status'>{box.status_text}</Badge>]}
        actions={[
          <Button key='print' variant='default' leftSection={<IconPrinter />} onClick={() => window.print()}>{t`Print label`}</Button>,
          <Button key='edit' variant='default' leftSection={<IconEdit />} onClick={() => navigate(`/boxes/${box.pk}/edit`)}>{t`Edit`}</Button>,
          <Button key='move' leftSection={<IconMapPin />} onClick={() => {
            setMoveLocation(box.current_location ? String(box.current_location) : null);
            setMoveOpened(true);
          }}>{t`Move`}</Button>
        ]}
      />

      <Card withBorder p='md' className='vhc-box-label'>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Stack>
            <Title order={1}>{box.box_number}</Title>
            <Badge size='xl' variant='filled' color={box.team_detail?.color || 'blue'} style={{ alignSelf: 'flex-start' }}>
              {box.team_detail?.name}
            </Badge>
            <Text size='lg' fw={600}>{box.contents}</Text>
            <Text>{t`Destination`}: {locationLabel(box.destination_detail)}</Text>
          </Stack>
          <QRCode data={box.box_number} margin={1} />
        </SimpleGrid>
      </Card>
      <Card withBorder p='md'>
        <Title order={3} mb='md'>{t`Box items`}</Title>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t`Part`}</Table.Th>
              <Table.Th>{t`Description`}</Table.Th>
              <Table.Th>{t`Quantity`}</Table.Th>
              <Table.Th>{t`Size`}</Table.Th>
              <Table.Th>{t`Sterile (S/NS)`}</Table.Th>
              <Table.Th>{t`Expiration date`}</Table.Th>
              <Table.Th>{t`Stock item`}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {box.items.map((item) => (
              <Table.Tr key={item.pk}>
                <Table.Td>
                  <Anchor component={Link} to={`/part/${item.part}`} fw={600}>
                    {item.part_detail.name}
                  </Anchor>
                  {item.part_detail.IPN && <Text size='xs' c='dimmed'>{item.part_detail.IPN}</Text>}
                </Table.Td>
                <Table.Td>{item.part_detail.description || '-'}</Table.Td>
                <Table.Td>{Number(item.quantity).toLocaleString()} {item.part_detail.units || ''}</Table.Td>
                <Table.Td>{item.size || '-'}</Table.Td>
                <Table.Td>{item.sterile || '-'}</Table.Td>
                <Table.Td>{item.expiry_date || '-'}</Table.Td>
                <Table.Td>
                  <Anchor component={Link} to={`/stock/item/${item.stock_item}`}>
                    #{item.stock_item}
                  </Anchor>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>

      <Card withBorder p='md'>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing='lg'>
          <Fact label={t`Current location`} value={locationLabel(box.current_location_detail)} />
          <Fact label={t`Destination`} value={locationLabel(box.destination_detail)} />
          <Fact label={t`Shipment`} value={box.shipment_detail?.reference} />
          <Fact label={t`Pallet`} value={box.pallet_detail?.number} />
          <Fact label={t`Created by`} value={box.created_by_name} />
          <Fact label={t`Last updated by`} value={box.updated_by_name} />
          <Fact label={t`Revision`} value={box.revision} />
        </SimpleGrid>
        {box.note && <><Divider my='md' /><Text>{box.note}</Text></>}
      </Card>

      <Card withBorder p='md'>
        <Group justify='space-between' mb='md'>
          <Title order={3}>{t`Lifecycle`}</Title>
          <Group gap='xs'>
            <Button size='xs' variant='light' loading={saving} onClick={() => updateStatus('DISTRIBUTED')}>{t`Distributed`}</Button>
            <Button size='xs' variant='light' loading={saving} onClick={() => updateStatus('RETURNED')}>{t`Returned`}</Button>
            <Button size='xs' color='red' variant='light' loading={saving} onClick={() => updateStatus('LOST')}>{t`Lost`}</Button>
            <Button size='xs' color='gray' variant='light' loading={saving} onClick={() => updateStatus('CLOSED')}>{t`Close`}</Button>
          </Group>
        </Group>
        <Table striped highlightOnHover>
          <Table.Thead><Table.Tr>
            <Table.Th>{t`When`}</Table.Th><Table.Th>{t`Action`}</Table.Th><Table.Th>{t`Movement`}</Table.Th><Table.Th>{t`User`}</Table.Th><Table.Th>{t`Notes`}</Table.Th>
          </Table.Tr></Table.Thead>
          <Table.Tbody>
            {events.map((event) => (
              <Table.Tr key={event.pk}>
                <Table.Td>{new Date(event.timestamp).toLocaleString()}</Table.Td>
                <Table.Td>{event.action_text}</Table.Td>
                <Table.Td>{event.to_location_detail ? `${locationLabel(event.from_location_detail)} ? ${locationLabel(event.to_location_detail)}` : '?'}</Table.Td>
                <Table.Td>{event.user_name || '?'}</Table.Td>
                <Table.Td>{event.notes || '?'}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>

      <Modal opened={moveOpened} onClose={() => setMoveOpened(false)} title={t`Move box ${box.box_number}`}>
        <Stack>
          <Select
            label={t`New location`}
            required
            searchable
            data={locations.map((location) => ({ value: String(location.pk), label: locationLabel(location) }))}
            value={moveLocation}
            onChange={setMoveLocation}
          />
          <Select label={t`New status`} clearable data={MOVE_STATUS_OPTIONS} value={moveStatus} onChange={setMoveStatus} />
          <Textarea label={t`Movement note`} maxLength={500} value={moveNotes} onChange={(event) => setMoveNotes(event.currentTarget.value)} />
          <Group justify='flex-end'>
            <Button variant='default' onClick={() => setMoveOpened(false)}>{t`Cancel`}</Button>
            <Button loading={saving} disabled={!moveLocation} onClick={moveBox}>{t`Move box`}</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
