import { t } from '@lingui/core/macro';
import { Alert, Card, Stack } from '@mantine/core';
import { IconBarcode } from '@tabler/icons-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ApiEndpoints } from '@lib/enums/ApiEndpoints';
import { apiUrl } from '@lib/functions/Api';
import { BarcodeInput } from '../../components/barcodes/BarcodeInput';
import { PageDetail } from '../../components/nav/PageDetail';
import { useApi } from '../../contexts/ApiContext';
import { type VhcBox, apiResults } from './types';

export default function BoxScan() {
  const api = useApi();
  const navigate = useNavigate();
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string>();

  const scan = (rawBarcode: string) => {
    const boxNumber = rawBarcode.match(/\d{6}/)?.[0];
    if (!boxNumber) {
      setError(t`This is not a six-digit VHC box number`);
      return;
    }

    setProcessing(true);
    setError(undefined);
    api
      .get(apiUrl(ApiEndpoints.vhc_box_scan), { params: { barcode: boxNumber } })
      .then(({ data }) => {
        const boxes = apiResults<VhcBox>(data);
        if (boxes.length === 1) {
          navigate(`/boxes/${boxes[0].pk}`);
        } else {
          setError(t`No box was found for ${boxNumber}`);
        }
      })
      .catch(() => setError(t`The box lookup failed`))
      .finally(() => setProcessing(false));
  };

  return (
    <Stack>
      <PageDetail
        title={t`Scan VHC box`}
        subtitle={t`Open a box record by scanning or entering its six-digit label`}
        icon={<IconBarcode />}
      />
      <Card withBorder p='md'>
        <Stack>
          <Alert color='blue'>{t`Scan the QR code on a VHC box label, or enter the number manually.`}</Alert>
          <BarcodeInput onScan={scan} processing={processing} error={error} actionText={t`Find box`} />
        </Stack>
      </Card>
    </Stack>
  );
}
