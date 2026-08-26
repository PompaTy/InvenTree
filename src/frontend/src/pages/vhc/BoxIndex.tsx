import { t } from '@lingui/core/macro';
import { Anchor, Badge, Button, Group, Stack, Text } from '@mantine/core';
import { IconBarcode, IconPackage, IconPlus } from '@tabler/icons-react';
import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { ApiEndpoints } from '@lib/enums/ApiEndpoints';
import { apiUrl } from '@lib/functions/Api';
import useTable from '@lib/hooks/UseTable';
import type { TableColumn } from '@lib/types/Tables';
import { PageDetail } from '../../components/nav/PageDetail';
import { InvenTreeTable } from '../../tables/InvenTreeTable';
import TeamManager from './TeamManager';
import { type VhcBox, locationLabel } from './types';

function statusColor(status: string) {
  if (status === 'LOST') return 'red';
  if (status === 'CLOSED') return 'gray';
  if (status === 'DISTRIBUTED') return 'green';
  if (status === 'IN_TRANSIT') return 'orange';
  return 'blue';
}

export default function BoxIndex() {
  const navigate = useNavigate();
  const table = useTable('vhc-boxes');

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
        render: (record) => (
          <Badge color={statusColor(record.status)}>{record.status_text}</Badge>
        )
      },
      {
        accessor: 'shipment',
        title: t`Shipment`,
        render: (record) => record.shipment_detail?.reference || '?'
      },
      {
        accessor: 'pallet',
        title: t`Pallet`,
        render: (record) => record.pallet_detail?.number ?? '?'
      },
      {
        accessor: 'current_location',
        title: t`Current location`,
        render: (record) => locationLabel(record.current_location_detail)
      },
      {
        accessor: 'destination',
        title: t`Destination`,
        render: (record) => locationLabel(record.destination_detail)
      },
      { accessor: 'updated', title: t`Last updated`, sortable: true }
    ],
    []
  );

  return (
    <Stack>
      <PageDetail
        title={t`VHC Boxes`}
        subtitle={t`Pack, locate, move, and audit mission inventory boxes`}
        icon={<IconPackage />}
        actions={[
          <Button key='scan' variant='default' leftSection={<IconBarcode />} onClick={() => navigate('/boxes/scan')}>
            {t`Scan`}
          </Button>,
          <TeamManager key='teams' />,
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
          defaultSortColumn: '-updated',
          onRowClick: (record) => navigate(`/boxes/${record.pk}`)
        }}
      />
    </Stack>
  );
}
