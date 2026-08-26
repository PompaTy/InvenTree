import { t } from '@lingui/core/macro';
import {
  ActionIcon,
  Button,
  ColorInput,
  Divider,
  Group,
  Modal,
  Stack,
  Text,
  TextInput
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import {
  IconDeviceFloppy,
  IconPlus,
  IconTrash,
  IconUsersGroup
} from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';

import { ApiEndpoints } from '@lib/enums/ApiEndpoints';
import { apiUrl } from '@lib/functions/Api';
import { useApi } from '../../contexts/ApiContext';
import { showApiErrorMessage } from '../../functions/notifications';
import { useUserState } from '../../states/UserState';
import { type VhcTeam, apiResults } from './types';

function makeTeamCode(name: string) {
  return (
    name
      .trim()
      .toUpperCase()
      .replace(/[^A-Z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, 30) || 'TEAM'
  );
}

export default function TeamManager() {
  const api = useApi();
  const user = useUserState();
  const [opened, setOpened] = useState(false);
  const [teams, setTeams] = useState<VhcTeam[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [newName, setNewName] = useState('');
  const [newColor, setNewColor] = useState('#228BE6');
  const [creating, setCreating] = useState(false);

  const loadTeams = useCallback(() => {
    setLoading(true);
    api
      .get(apiUrl(ApiEndpoints.vhc_team_list), { params: { limit: 1000 } })
      .then(({ data }) => setTeams(apiResults<VhcTeam>(data)))
      .catch((error) =>
        showApiErrorMessage({
          error,
          title: t({ message: 'Could not load teams' })
        })
      )
      .finally(() => setLoading(false));
  }, [api]);

  useEffect(() => {
    if (opened) {
      loadTeams();
    }
  }, [loadTeams, opened]);

  if (!user.isStaff()) {
    return null;
  }

  const updateTeam = (teamId: number, changes: Partial<VhcTeam>) => {
    setTeams((current) =>
      current.map((team) =>
        team.pk === teamId ? { ...team, ...changes } : team
      )
    );
  };

  const saveTeam = (team: VhcTeam) => {
    const name = team.name.trim();

    if (!name) {
      notifications.show({
        title: t({ message: 'Team name is required' }),
        message: t({ message: 'Enter a name before saving the team.' }),
        color: 'red'
      });
      return;
    }

    setSavingId(team.pk);
    api
      .patch(apiUrl(ApiEndpoints.vhc_team_list) + team.pk + '/', {
        name,
        color: team.color
      })
      .then(({ data }) => {
        updateTeam(team.pk, data);
        notifications.show({
          title: t({ message: 'Team saved' }),
          message: t({ message: 'The team has been updated.' }),
          color: 'green'
        });
      })
      .catch((error) =>
        showApiErrorMessage({
          error,
          title: t({ message: 'Could not save team' })
        })
      )
      .finally(() => setSavingId(null));
  };

  const createTeam = () => {
    const name = newName.trim();

    if (!name) {
      notifications.show({
        title: t({ message: 'Team name is required' }),
        message: t({ message: 'Enter a name before adding a team.' }),
        color: 'red'
      });
      return;
    }

    setCreating(true);
    api
      .post(apiUrl(ApiEndpoints.vhc_team_list), {
        name,
        code: makeTeamCode(name),
        color: newColor,
        active: true
      })
      .then(({ data }) => {
        setTeams((current) => [...current, data]);
        setNewName('');
        setNewColor('#228BE6');
        notifications.show({
          title: t({ message: 'Team added' }),
          message: t({
            message: 'The team is now available when packing a box.'
          }),
          color: 'green'
        });
      })
      .catch((error) =>
        showApiErrorMessage({
          error,
          title: t({ message: 'Could not add team' }),
          message: t({ message: 'A unique team name is required.' })
        })
      )
      .finally(() => setCreating(false));
  };

  const deleteTeam = (team: VhcTeam) => {
    modals.openConfirmModal({
      title: t({ message: 'Remove team' }),
      children: (
        <Text>
          {t({
            message:
              'Remove this team? This cannot be undone. Teams assigned to boxes cannot be removed.'
          })}
        </Text>
      ),
      labels: {
        confirm: t({ message: 'Remove' }),
        cancel: t({ message: 'Cancel' })
      },
      confirmProps: { color: 'red' },
      onConfirm: () => {
        setSavingId(team.pk);
        api
          .delete(apiUrl(ApiEndpoints.vhc_team_list) + team.pk + '/')
          .then(() => {
            setTeams((current) =>
              current.filter((currentTeam) => currentTeam.pk !== team.pk)
            );
            notifications.show({
              title: t({ message: 'Team removed' }),
              message: t({ message: 'The team has been removed.' }),
              color: 'green'
            });
          })
          .catch((error) =>
            showApiErrorMessage({
              error,
              title: t({ message: 'Could not remove team' }),
              message: t({
                message: 'Teams assigned to boxes cannot be removed.'
              })
            })
          )
          .finally(() => setSavingId(null));
      }
    });
  };

  return (
    <>
      <Button
        variant='default'
        leftSection={<IconUsersGroup />}
        onClick={() => setOpened(true)}
      >
        {t({ message: 'Edit teams' })}
      </Button>
      <Modal
        opened={opened}
        onClose={() => setOpened(false)}
        title={t({ message: 'Edit teams' })}
        size='lg'
      >
        <Stack>
          <Text size='sm' c='dimmed'>
            {t({
              message:
                'Add teams and update their names or label colors. Removing a team is only possible when it is not assigned to a box.'
            })}
          </Text>
          <Group align='flex-end' wrap='nowrap'>
            <TextInput
              label={t({ message: 'New team name' })}
              placeholder={t({ message: 'e.g. General Medicine' })}
              value={newName}
              onChange={(event) => setNewName(event.currentTarget.value)}
              style={{ flex: 1 }}
            />
            <ColorInput
              label={t({ message: 'Color' })}
              value={newColor}
              onChange={setNewColor}
              format='hex'
              w={150}
            />
            <Button
              leftSection={<IconPlus size={16} />}
              onClick={createTeam}
              loading={creating}
            >
              {t({ message: 'Add team' })}
            </Button>
          </Group>
          <Divider />
          {loading ? (
            <Text c='dimmed'>{t({ message: 'Loading teams...' })}</Text>
          ) : teams.length === 0 ? (
            <Text c='dimmed'>
              {t({ message: 'No teams have been added yet.' })}
            </Text>
          ) : (
            teams.map((team) => (
              <Group key={team.pk} align='flex-end' wrap='nowrap'>
                <TextInput
                  label={t({ message: 'Team name' })}
                  value={team.name}
                  onChange={(event) =>
                    updateTeam(team.pk, { name: event.currentTarget.value })
                  }
                  style={{ flex: 1 }}
                />
                <ColorInput
                  label={t({ message: 'Color' })}
                  value={team.color}
                  onChange={(color) => updateTeam(team.pk, { color })}
                  format='hex'
                  w={150}
                />
                <ActionIcon
                  size='lg'
                  variant='light'
                  aria-label={t({ message: 'Save team' })}
                  onClick={() => saveTeam(team)}
                  loading={savingId === team.pk}
                >
                  <IconDeviceFloppy size={18} />
                </ActionIcon>
                <ActionIcon
                  size='lg'
                  variant='light'
                  color='red'
                  aria-label={t({ message: 'Remove team' })}
                  disabled={savingId === team.pk}
                  onClick={() => deleteTeam(team)}
                >
                  <IconTrash size={18} />
                </ActionIcon>
              </Group>
            ))
          )}
        </Stack>
      </Modal>
    </>
  );
}
