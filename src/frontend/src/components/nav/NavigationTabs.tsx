import { t } from '@lingui/core/macro';
import {
  ActionIcon,
  Button,
  Checkbox,
  Divider,
  Group,
  Modal,
  Paper,
  ScrollArea,
  Stack,
  Tabs,
  Text,
  Tooltip,
  UnstyledButton
} from '@mantine/core';
import {
  IconAdjustmentsHorizontal,
  IconArrowDown,
  IconArrowUp,
  IconGripVertical
} from '@tabler/icons-react';
import { type DragEvent, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useShallow } from 'zustand/react/shallow';

import { getBaseUrl, navigateToLink } from '@lib/functions/Navigation';
import type { NavigationUIFeature } from '../plugins/PluginUIFeatureTypes';
import {
  DEFAULT_NAVIGATION_TABS,
  getNavigationMenuItems
} from '../../defaults/navigation';
import { generateUrl } from '../../functions/urls';
import { InvenTreeIcon } from '../../functions/icons';
import { usePluginUIFeature } from '../../hooks/UsePluginUIFeature';
import * as classes from '../../main.css';
import { useLocalState } from '../../states/LocalState';
import {
  useGlobalSettingsState,
  useUserSettingsState
} from '../../states/SettingsStates';
import { useUserState } from '../../states/UserState';
import type { MenuLinkItem } from '../items/MenuLinks';

function itemMatchesPath(item: MenuLinkItem, pathname: string) {
  const link = item.link?.replace(/\/$/, '') || '/';

  if (item.id === 'home') {
    return pathname === '/' || pathname === '/home' || pathname === '/home/';
  }

  return pathname === link || pathname.startsWith(`${link}/`);
}

export function NavigationTabs() {
  const user = useUserState();
  const globalSettings = useGlobalSettingsState();
  const userSettings = useUserSettingsState();
  const navigate = useNavigate();
  const location = useLocation();
  const [editorOpened, setEditorOpened] = useState(false);
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [navigationTabs, setNavigationTabs] = useLocalState(
    useShallow((state) => [
      state.navigationTabs,
      state.setNavigationTabs
    ])
  );

  const availableItems = useMemo(() => {
    const items = getNavigationMenuItems(user, globalSettings);
    return [...items.navigate, ...items.settings, ...items.actions].filter(
      (item) => !item.hidden && !!item.link && !item.external
    );
  }, [user, globalSettings]);

  const availableById = useMemo(
    () => new Map(availableItems.map((item) => [item.id, item])),
    [availableItems]
  );

  const selectedIds = navigationTabs ?? DEFAULT_NAVIGATION_TABS;
  const selectedItems = selectedIds
    .map((id) => availableById.get(id))
    .filter((item): item is MenuLinkItem => !!item);

  const activeItem = [...selectedItems]
    .sort((a, b) => (b.link?.length ?? 0) - (a.link?.length ?? 0))
    .find((item) => itemMatchesPath(item, location.pathname));

  const withIcons = userSettings.isSet('ICONS_IN_NAVBAR', false);

  const extraNavs = usePluginUIFeature<NavigationUIFeature>({
    featureType: 'navigation',
    context: {}
  });

  const updateSelection = (id: string, selected: boolean) => {
    const current = selectedItems.map((item) => item.id);
    setNavigationTabs(
      selected ? [...current, id] : current.filter((itemId) => itemId !== id)
    );
  };

  const moveTab = (id: string, offset: number) => {
    const current = selectedItems.map((item) => item.id);
    const from = current.indexOf(id);
    const to = from + offset;

    if (from < 0 || to < 0 || to >= current.length) return;

    const next = [...current];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    setNavigationTabs(next);
  };

  const dropTab = (targetId: string, event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (!draggedId || draggedId === targetId) return;

    const current = selectedItems.map((item) => item.id);
    const from = current.indexOf(draggedId);
    const to = current.indexOf(targetId);
    if (from < 0 || to < 0) return;

    const next = [...current];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    setNavigationTabs(next);
    setDraggedId(null);
  };

  const editorItems = [
    ...selectedItems,
    ...availableItems.filter((item) => !selectedIds.includes(item.id))
  ];

  return (
    <>
      <Group gap={2} wrap='nowrap' className={classes.navigationTabs}>
        <Tabs
          defaultValue='home'
          classNames={{
            root: classes.tabs,
            list: classes.tabsList,
            tab: classes.tab
          }}
          value={activeItem?.id ?? null}
        >
          <Tabs.List>
            {selectedItems.map((item) => (
              <Tabs.Tab
                value={item.id}
                key={item.id}
                leftSection={
                  withIcons &&
                  item.icon && (
                    <InvenTreeIcon
                      icon={item.icon}
                      iconProps={{ size: 18 }}
                    />
                  )
                }
                onClick={(event) =>
                  navigateToLink(item.link!, navigate, event)
                }
              >
                <UnstyledButton
                  component='a'
                  href={generateUrl(`/${getBaseUrl()}${item.link}`)}
                >
                  {item.title}
                </UnstyledButton>
              </Tabs.Tab>
            ))}
            {extraNavs.map((nav) => (
              <Tabs.Tab
                value={`plugin-${nav.options.key}`}
                key={`plugin-${nav.options.key}`}
                onClick={(event) =>
                  navigateToLink(nav.options.options.url, navigate, event)
                }
              >
                {nav.options.title}
              </Tabs.Tab>
            ))}
          </Tabs.List>
        </Tabs>
        <Tooltip label={t`Customize navigation tabs`} position='bottom'>
          <ActionIcon
            variant='subtle'
            aria-label={t`Customize navigation tabs`}
            onClick={() => setEditorOpened(true)}
          >
            <IconAdjustmentsHorizontal size={18} />
          </ActionIcon>
        </Tooltip>
      </Group>

      <Modal
        opened={editorOpened}
        onClose={() => setEditorOpened(false)}
        title={t`Customize navigation tabs`}
        size='md'
      >
        <Stack>
          <Text size='sm' c='dimmed'>
            {t`Choose which menu destinations appear in the header. Drag selected tabs to reorder them, or use the arrow buttons.`}
          </Text>
          <Divider />
          <ScrollArea.Autosize mah='60vh'>
            <Stack gap='xs'>
              {editorItems.map((item) => {
                const selected = selectedIds.includes(item.id);
                const selectedIndex = selectedItems.findIndex(
                  (selectedItem) => selectedItem.id === item.id
                );

                return (
                  <Paper
                    key={item.id}
                    withBorder
                    p='xs'
                    draggable={selected}
                    onDragStart={() => setDraggedId(item.id)}
                    onDragEnd={() => setDraggedId(null)}
                    onDragOver={(event) => selected && event.preventDefault()}
                    onDrop={(event) => selected && dropTab(item.id, event)}
                    style={{ cursor: selected ? 'grab' : 'default' }}
                  >
                    <Group justify='space-between' wrap='nowrap'>
                      <Group gap='xs' wrap='nowrap'>
                        <IconGripVertical
                          size={18}
                          opacity={selected ? 1 : 0.25}
                          aria-hidden
                        />
                        <Checkbox
                          checked={selected}
                          onChange={(event) =>
                            updateSelection(item.id, event.currentTarget.checked)
                          }
                          label={item.title}
                        />
                      </Group>
                      {selected && (
                        <Group gap={4} wrap='nowrap'>
                          <ActionIcon
                            variant='subtle'
                            aria-label={t`Move tab up`}
                            disabled={selectedIndex === 0}
                            onClick={() => moveTab(item.id, -1)}
                          >
                            <IconArrowUp size={17} />
                          </ActionIcon>
                          <ActionIcon
                            variant='subtle'
                            aria-label={t`Move tab down`}
                            disabled={selectedIndex === selectedItems.length - 1}
                            onClick={() => moveTab(item.id, 1)}
                          >
                            <IconArrowDown size={17} />
                          </ActionIcon>
                        </Group>
                      )}
                    </Group>
                  </Paper>
                );
              })}
            </Stack>
          </ScrollArea.Autosize>
          <Divider />
          <Group justify='space-between'>
            <Button variant='default' onClick={() => setNavigationTabs(null)}>
              {t`Reset to defaults`}
            </Button>
            <Button onClick={() => setEditorOpened(false)}>{t`Done`}</Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
