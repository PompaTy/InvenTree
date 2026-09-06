import { t } from '@lingui/core/macro';
import {
  ActionIcon,
  Button,
  Card,
  Combobox,
  Group,
  InputBase,
  Loader,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Textarea,
  useCombobox
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useDebouncedValue } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import {
  IconDeviceFloppy,
  IconPackage,
  IconPlus,
  IconTrash
} from '@tabler/icons-react';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { ApiEndpoints } from '@lib/enums/ApiEndpoints';
import { apiUrl } from '@lib/functions/Api';
import { PageDetail } from '../../components/nav/PageDetail';
import { useApi } from '../../contexts/ApiContext';
import { showApiErrorMessage } from '../../functions/notifications';
import {
  type VhcBox,
  type VhcLocation,
  type VhcPartSummary,
  type VhcTeam,
  apiResults,
  locationLabel
} from './types';

const STERILITY_OPTIONS = [
  { value: 'S', label: 'S' },
  { value: 'NS', label: 'NS' }
];

interface BoxItemFormValue {
  part: string | null;
  part_name: string;
  quantity: number | string;
  size: string;
  sterile: string | null;
  expiry_date: string | null;
  expiry_label?: string;
  part_detail?: VhcPartSummary;
}

interface BoxFormValues {
  box_number: string;
  items: BoxItemFormValue[];
  team: string;
  other_team_description: string;
  current_location: string | null;
  destination: string | null;
  note: string;
}

function nullablePk(value: string | null) {
  return value ? Number(value) : null;
}

function PartAutocomplete({
  value,
  onChange
}: Readonly<{
  value: BoxItemFormValue;
  onChange: (value: BoxItemFormValue) => void;
}>) {
  const api = useApi();
  const combobox = useCombobox({
    onDropdownClose: () => combobox.resetSelectedOption()
  });
  const [search] = useDebouncedValue(value.part_name, 250);
  const [parts, setParts] = useState<VhcPartSummary[]>(
    value.part_detail ? [value.part_detail] : []
  );
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const term = search.trim();
    if (term.length < 2) {
      setParts(value.part_detail ? [value.part_detail] : []);
      return;
    }

    let active = true;
    setLoading(true);
    api
      .get(apiUrl(ApiEndpoints.part_list), {
        params: { search: term, active: true, limit: 20 }
      })
      .then(({ data }) => {
        if (active) setParts(apiResults<VhcPartSummary>(data));
      })
      .catch(() => {
        if (active) setParts([]);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [api, search]);

  return (
    <Stack gap={4} style={{ flex: 1 }}>
      <Combobox
        store={combobox}
        onOptionSubmit={(partPk) => {
          const part = parts.find((candidate) => String(candidate.pk) === partPk);
          if (part) {
            onChange({ ...value, part: String(part.pk), part_name: part.name, part_detail: part });
          }
          combobox.closeDropdown();
        }}
      >
        <Combobox.Target>
          <InputBase
            label={t`Item`}
            required
            value={value.part_name}
            placeholder={t`Search parts or enter a new item name`}
            onChange={(event) => {
              onChange({
                ...value,
                part: null,
                part_name: event.currentTarget.value,
                part_detail: undefined
              });
              combobox.openDropdown();
            }}
            onFocus={() => combobox.openDropdown()}
            onClick={() => combobox.openDropdown()}
            onBlur={() => combobox.closeDropdown()}
            rightSection={loading ? <Loader size={16} /> : <Combobox.Chevron />}
          />
        </Combobox.Target>
        <Combobox.Dropdown>
          <Combobox.Options>
            {parts.length === 0 ? (
              <Combobox.Empty>
                {search.trim().length < 2
                  ? t`Type at least two characters to search`
                  : t`No existing part found. This item will be created.`}
              </Combobox.Empty>
            ) : (
              parts.map((part) => (
                <Combobox.Option key={part.pk} value={String(part.pk)}>
                  <Text size='sm' fw={500}>{part.name}</Text>
                  <Text size='xs' c='dimmed'>
                    {[part.IPN, part.description].filter(Boolean).join(' - ')}
                  </Text>
                </Combobox.Option>
              ))
            )}
          </Combobox.Options>
        </Combobox.Dropdown>
      </Combobox>
      <Text size='xs' c={value.part ? 'green' : 'dimmed'}>
        {value.part
          ? t`Existing part selected; stock will be linked automatically.`
          : t`If no exact part exists, a new part and stock record will be created.`}
      </Text>
    </Stack>
  );
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
  const [locations, setLocations] = useState<VhcLocation[]>([]);

  const form = useForm<BoxFormValues>({
    initialValues: {
      box_number: '',
      items: [
        {
          part: null,
          part_name: '',
          quantity: 1,
          size: '',
          sterile: null,
          expiry_date: null
        }
      ],
      team: '',
      other_team_description: '',
      current_location: null,
      destination: null,
      note: ''
    },
    validate: {
      box_number: (value) =>
        value && !/^\d{6}$/.test(value) ? t`Use exactly six digits` : null,
      items: (items) => {
        if (!items.length) return t`Add at least one item`;
        if (items.some((item) => !item.part_name.trim())) return t`Every item needs a name`;
        if (items.some((item) => Number(item.quantity) <= 0)) return t`Every quantity must be greater than zero`;
        const names = items.map((item) => item.part_name.trim().toLowerCase());
        if (new Set(names).size !== names.length) return t`The same item cannot be listed twice`;
        return null;
      },
      team: (value) => (value ? null : t`Team is required`)
    }
  });

  useEffect(() => {
    Promise.all([
      api.get(apiUrl(ApiEndpoints.vhc_team_list), { params: { active: true, limit: 1000 } }),
      api.get(apiUrl(ApiEndpoints.stock_location_list), { params: { limit: 1000 } })
    ])
      .then(([teamResponse, locationResponse]) => {
        const loadedTeams = apiResults<VhcTeam>(teamResponse.data);
        const loadedLocations = apiResults<VhcLocation>(locationResponse.data);
        setTeams(loadedTeams);
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
          items: data.items.map((item) => ({
            part: String(item.part),
            part_name: item.part_detail.name,
            quantity: Number(item.quantity),
            size: item.size || '',
            sterile: item.sterile || null,
            expiry_date: item.expiry_date || null,
            expiry_label: item.expiry_label || '',
            part_detail: item.part_detail
          })),
          team: String(data.team),
          other_team_description: data.other_team_description,
          current_location: data.current_location ? String(data.current_location) : null,
          destination: data.destination ? String(data.destination) : null,
          note: data.note
        });
      })
      .catch((error) => showApiErrorMessage({ error, title: t`Could not load box` }));
  }, [boxId]);


  const selectedTeam = teams.find((team) => String(team.pk) === form.values.team);

  const updateItem = (index: number, item: BoxItemFormValue) => {
    form.setFieldValue(
      'items',
      form.values.items.map((current, itemIndex) => (itemIndex === index ? item : current))
    );
  };

  const save = form.onSubmit((values) => {
    setSaving(true);
    const payload = {
      box_number: values.box_number.trim(),
      items: values.items.map((item) => ({
        ...(item.part ? { part: Number(item.part) } : { part_name: item.part_name.trim() }),
        quantity: Number(item.quantity),
        size: item.size.trim(),
        sterile: item.sterile || '',
        expiry_date: item.expiry_date || null,
        expiry_label: item.expiry_label || ''
      })),
      team: Number(values.team),
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

            <Card withBorder p='md'>
              <Stack>
                <Group justify='space-between'>
                  <div>
                    <Text fw={600}>{t`Box items`}</Text>
                    <Text size='sm' c='dimmed'>{t`Select an existing part or type a new item name.`}</Text>
                  </div>
                  <Button
                    type='button'
                    variant='light'
                    leftSection={<IconPlus size={16} />}
                    onClick={() =>
                      form.insertListItem('items', {
                        part: null,
                        part_name: '',
                        quantity: 1,
                        size: '',
                        sterile: null,
                        expiry_date: null
                      })
                    }
                  >
                    {t`Add item`}
                  </Button>
                </Group>
                {form.values.items.map((item, index) => (
                  <Card key={`${index}-${item.part ?? 'new'}`} withBorder p='sm'>
                    <Stack gap='sm'>
                      <Group align='flex-start' wrap='nowrap'>
                        <PartAutocomplete value={item} onChange={(next) => updateItem(index, next)} />
                        <NumberInput
                          label={t`Quantity`}
                          required
                          min={0.00001}
                          decimalScale={5}
                          allowNegative={false}
                          style={{ width: 150 }}
                          value={item.quantity}
                          onChange={(quantity) => updateItem(index, { ...item, quantity })}
                        />
                        <ActionIcon
                          mt={25}
                          size='lg'
                          variant='subtle'
                          color='red'
                          aria-label={t`Remove item`}
                          disabled={form.values.items.length === 1}
                          onClick={() => form.removeListItem('items', index)}
                        >
                          <IconTrash size={18} />
                        </ActionIcon>
                      </Group>
                      <SimpleGrid cols={{ base: 1, sm: 3 }}>
                        <TextInput
                          label={t`Size`}
                          value={item.size}
                          onChange={(event) =>
                            updateItem(index, {
                              ...item,
                              size: event.currentTarget.value
                            })
                          }
                        />
                        <Select
                          label={t`Sterile (S/NS)`}
                          clearable
                          data={STERILITY_OPTIONS}
                          value={item.sterile}
                          onChange={(sterile) =>
                            updateItem(index, { ...item, sterile, expiry_label: item.expiry_label ? (sterile === 'S' ? 'ER' : sterile === 'NS' ? 'N/A' : '') : '' })
                          }
                        />
                        <Stack gap='xs'>
                        <Select
                          label={t`Expiration date`}
                          value={item.expiry_label || 'date'}
                          data={[
                            { value: 'date', label: t`Date` },
                            ...(item.sterile === 'S' ? [{ value: 'ER', label: 'ER' }] : item.sterile === 'NS' ? [{ value: 'N/A', label: 'N/A' }] : [])
                          ]}
                          onChange={(value) => updateItem(index, { ...item, expiry_label: value === 'date' ? '' : value || '', expiry_date: value === 'date' ? item.expiry_date : null })}
                        />
                        {!item.expiry_label && <TextInput
                          aria-label={t`Expiration date`}
                          type='date'
                          value={item.expiry_date ?? ''}
                          onChange={(event) =>
                            updateItem(index, {
                              ...item,
                              expiry_date: event.currentTarget.value || null
                            })
                          }
                        />}
                        </Stack>
                      </SimpleGrid>
                    </Stack>
                  </Card>
                ))}
                {form.errors.items && <Text size='sm' c='red'>{String(form.errors.items)}</Text>}
              </Stack>
            </Card>

            <SimpleGrid cols={{ base: 1, sm: 2 }}>
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
