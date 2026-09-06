import { t } from '@lingui/core/macro';
import {
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  Modal,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  Title
} from '@mantine/core';
import {
  IconBarcode,
  IconMapPin,
  IconPackage,
  IconPlus,
  IconPrinter
} from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { ActionButton } from '@lib/components/ActionButton';
import { ApiEndpoints } from '@lib/enums/ApiEndpoints';
import { apiUrl } from '@lib/functions/Api';
import useTable from '@lib/hooks/UseTable';
import type { TableColumn } from '@lib/types/Tables';
import { QRCode } from '../../components/barcodes/QRCode';
import { PageDetail } from '../../components/nav/PageDetail';
import { useApi } from '../../contexts/ApiContext';
import { showApiErrorMessage } from '../../functions/notifications';
import { InvenTreeTable } from '../../tables/InvenTreeTable';
import CurrentShipmentManager from './CurrentShipmentManager';
import TeamManager from './TeamManager';
import {
  type VhcBox,
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

function statusColor(status: string) {
  if (status === 'LOST') return 'red';
  if (status === 'CLOSED') return 'gray';
  if (status === 'DISTRIBUTED') return 'green';
  if (status === 'IN_TRANSIT') return 'orange';
  return 'blue';
}

export default function BoxIndex() {
  const navigate = useNavigate();
  const api = useApi();
  const table = useTable('vhc-boxes');
  const [locations, setLocations] = useState<VhcLocation[]>([]);
  const [transferOpened, setTransferOpened] = useState(false);
  const [transferLocation, setTransferLocation] = useState<string | null>(null);
  const [transferStatus, setTransferStatus] = useState<string | null>(null);
  const [transferNotes, setTransferNotes] = useState('');
  const [transferring, setTransferring] = useState(false);

  useEffect(() => {
    api
      .get(apiUrl(ApiEndpoints.stock_location_list), {
        params: { limit: 1000 }
      })
      .then((response) => setLocations(apiResults<VhcLocation>(response.data)))
      .catch((error) =>
        showApiErrorMessage({ error, title: t`Could not load locations` })
      );
  }, [api]);

  const selectedBoxes = table.selectedRecords as VhcBox[];

  const openTransfer = useCallback(() => {
    setTransferLocation(null);
    setTransferStatus(null);
    setTransferNotes('');
    setTransferOpened(true);
  }, []);

  const transferBoxes = useCallback(() => {
    if (!transferLocation || selectedBoxes.length === 0) {
      return;
    }

    setTransferring(true);
    api
      .post(apiUrl(ApiEndpoints.vhc_box_bulk_move), {
        boxes: selectedBoxes.map((box) => box.pk),
        location: Number(transferLocation),
        ...(transferStatus ? { status: transferStatus } : {}),
        notes: transferNotes
      })
      .then(() => {
        notifications.show({
          title: t`Boxes transferred`,
          message: t`Selected boxes were moved to the new location.`,
          color: 'green'
        });
        setTransferOpened(false);
        table.clearSelectedRecords();
        table.refreshTable();
      })
      .catch((error) =>
        showApiErrorMessage({ error, title: t`Could not transfer boxes` })
      )
      .finally(() => setTransferring(false));
  }, [
    api,
    selectedBoxes,
    table.clearSelectedRecords,
    table.refreshTable,
    transferLocation,
    transferNotes,
    transferStatus
  ]);

  const printLabels = useCallback(() => {
    if (selectedBoxes.length > 0) {
      window.print();
    }
  }, [selectedBoxes]);

  const columns: TableColumn<VhcBox>[] = useMemo(
    () => [
      {
        accessor: 'box_number',
        title: t`Box`,
        sortable: true,
        switchable: false,
        render: (record) => (
          <Anchor component={Link} to={`/boxes/${record.pk}`} fw={600}>
            {record.box_number}
          </Anchor>
        )
      },
      {
        accessor: 'contents',
        title: t`Items`,
        render: (record) => <Text lineClamp={2}>{record.contents}</Text>
      },
      {
        accessor: 'team',
        title: t`Team`,
        sortable: true,
        ordering: 'team__name',
        render: (record) => (
          <Badge color={record.team_detail?.color || 'blue'} variant='light'>
            {record.team_detail?.name || '?'}
          </Badge>
        )
      },
      {
        accessor: 'status',
        title: t`Status`,
        sortable: true,
        defaultVisible: false,
        render: (record) => (
          <Badge color={statusColor(record.status)}>{record.status_text}</Badge>
        )
      },
      {
        accessor: 'shipment',
        title: t`Shipment`,
        sortable: true,
        ordering: 'shipment__reference',
        render: (record) => record.shipment_detail?.reference || '?'
      },
      {
        accessor: 'pallet',
        title: t`Pallet`,
        defaultVisible: false,
        render: (record) => record.pallet_detail?.number ?? '?'
      },
      {
        accessor: 'current_location',
        title: t`Current location`,
        sortable: true,
        ordering: 'current_location__pathstring',
        render: (record) => locationLabel(record.current_location_detail)
      },
      {
        accessor: 'destination',
        title: t`Destination`,
        sortable: true,
        ordering: 'destination__pathstring',
        render: (record) => locationLabel(record.destination_detail)
      },
      { accessor: 'updated', title: t`Last updated`, sortable: true, defaultVisible: false }
    ],
    []
  );

  const tableActions = useMemo(
    () => [
      <ActionButton
        key='transfer-boxes'
        disabled={!table.hasSelectedRecords}
        tooltip={t`Transfer selected boxes`}
        icon={<IconMapPin />}
        onClick={openTransfer}
      />,
      <ActionButton
        key='print-box-labels'
        disabled={!table.hasSelectedRecords}
        tooltip={t`Print labels for selected boxes`}
        icon={<IconPrinter />}
        onClick={printLabels}
      />
    ],
    [openTransfer, printLabels, table.hasSelectedRecords]
  );

  return (
    <Stack>
      <style>{`
        .vhc-box-print-labels {
          display: none;
        }

        @media print {
          body * { visibility: hidden !important; }
          .vhc-box-print-labels,
          .vhc-box-print-labels * {
            visibility: visible !important;
          }
          .vhc-box-print-labels {
            display: block !important;
            position: absolute;
            inset: 0;
            width: 100%;
          }
          .vhc-box-print-label {
            break-after: page;
            page-break-after: always;
            border: 0 !important;
          }
        }
      `}</style>
      <PageDetail
        title={t`VHC Boxes`}
        subtitle={t`Pack, locate, move, and audit mission inventory boxes`}
        icon={<IconPackage />}
        actions={[
          <Button key='scan' variant='default' leftSection={<IconBarcode />} onClick={() => navigate('/boxes/scan')}>
            {t`Scan`}
          </Button>,
          <TeamManager key='teams' />,
          <CurrentShipmentManager key='current-shipment' />,
          <Button key='new' leftSection={<IconPlus />} onClick={() => navigate('/boxes/new')}>
            {t`Pack box`}
          </Button>
        ]}
      />
      <InvenTreeTable
        url={apiUrl(ApiEndpoints.vhc_box_list)}
        tableState={table}
        columns={columns}
        props={{
          enableDownload: true,
          enableSelection: true,
          tableActions: tableActions,
          defaultSortColumn: '-updated',
          onRowClick: (record) => navigate(`/boxes/${record.pk}`)
        }}
      />
      <div className='vhc-box-print-labels'>
        {selectedBoxes.map((box) => (
          <Card key={box.pk} p='md' className='vhc-box-print-label'>
            <SimpleGrid cols={2}>
              <Stack>
                <Title order={1}>{box.box_number}</Title>
                <Badge
                  size='xl'
                  variant='filled'
                  color={box.team_detail?.color || 'blue'}
                  style={{ alignSelf: 'flex-start' }}
                >
                  {box.team_detail?.name}
                </Badge>
                <Text size='lg' fw={600}>{box.contents}</Text>
                <Text>{t`Destination`}: {locationLabel(box.destination_detail)}</Text>
              </Stack>
              <QRCode data={box.box_number} margin={1} />
            </SimpleGrid>
          </Card>
        ))}
      </div>
      <Modal
        opened={transferOpened}
        onClose={() => setTransferOpened(false)}
        title={t`Transfer selected boxes`}
      >
        <Stack>
          <Select
            label={t`New location`}
            required
            searchable
            data={locations.map((location) => ({
              value: String(location.pk),
              label: locationLabel(location)
            }))}
            value={transferLocation}
            onChange={setTransferLocation}
          />
          <Select
            label={t`New status`}
            clearable
            data={MOVE_STATUS_OPTIONS}
            value={transferStatus}
            onChange={setTransferStatus}
          />
          <Textarea
            label={t`Movement note`}
            maxLength={500}
            value={transferNotes}
            onChange={(event) => setTransferNotes(event.currentTarget.value)}
          />
          <Group justify='flex-end'>
            <Button variant='default' onClick={() => setTransferOpened(false)}>
              {t`Cancel`}
            </Button>
            <Button
              loading={transferring}
              disabled={!transferLocation || selectedBoxes.length === 0}
              onClick={transferBoxes}
            >
              {t`Transfer boxes`}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
