import { t } from '@lingui/core/macro';
import { Container, Drawer, Flex, Group, Space } from '@mantine/core';
import { useViewportSize } from '@mantine/hooks';
import { useEffect, useMemo, useRef, useState } from 'react';

import { AboutLinks, DocumentationLinks } from '../../defaults/links';
import { getNavigationMenuItems } from '../../defaults/navigation';
import useInstanceName from '../../hooks/UseInstanceName';
import * as classes from '../../main.css';
import { useGlobalSettingsState } from '../../states/SettingsStates';
import { useUserState } from '../../states/UserState';
import { InvenTreeLogo } from '../items/InvenTreeLogo';
import { type MenuLinkItem, MenuLinks } from '../items/MenuLinks';
import { StylishText } from '../items/StylishText';

// TODO @matmair #1: implement plugin loading and menu item generation see #5269
const plugins: MenuLinkItem[] = [];

export function NavigationDrawer({
  opened,
  close
}: Readonly<{
  opened: boolean;
  close: () => void;
}>) {
  return (
    <Drawer
      opened={opened}
      onClose={close}
      size='lg'
      withCloseButton={false}
      classNames={{
        body: classes.navigationDrawer
      }}
    >
      <DrawerContent closeFunc={close} />
    </Drawer>
  );
}

function DrawerContent({ closeFunc }: Readonly<{ closeFunc?: () => void }>) {
  const user = useUserState();

  const globalSettings = useGlobalSettingsState();
  const menuItems = useMemo(
    () => getNavigationMenuItems(user, globalSettings),
    [user, globalSettings]
  );

  const [scrollHeight, setScrollHeight] = useState(0);
  const ref = useRef(null);
  const { height } = useViewportSize();

  const title = useInstanceName();

  // update scroll height when viewport size changes
  useEffect(() => {
    if (ref.current == null) return;
    setScrollHeight(height - ref.current['clientHeight'] - 65);
  });

  const menuItemsDocumentation: MenuLinkItem[] = useMemo(
    () => DocumentationLinks(),
    []
  );

  const menuItemsAbout: MenuLinkItem[] = useMemo(
    () => AboutLinks(globalSettings, user),
    []
  );

  return (
    <Flex direction='column' mih='100vh' p={16}>
      <Group wrap='nowrap'>
        <InvenTreeLogo />
        <StylishText size='xl'>{title}</StylishText>
      </Group>
      <Space h='xs' />
      <Container className={classes.layoutContent} p={0}>
        <MenuLinks
          title={t`Navigation`}
          links={menuItems.navigate}
          beforeClick={closeFunc}
        />
        <MenuLinks
          title={t`Settings`}
          links={menuItems.settings}
          beforeClick={closeFunc}
        />
        <MenuLinks
          title={t`Actions`}
          links={menuItems.actions}
          beforeClick={closeFunc}
        />
        <Space h='md' />
        {plugins.length > 0 ? (
          <MenuLinks
            title={t`Plugins`}
            links={plugins}
            beforeClick={closeFunc}
          />
        ) : (
          <></>
        )}
      </Container>
      <div ref={ref}>
        <Space h='md' />
        <MenuLinks
          title={t`Documentation`}
          links={menuItemsDocumentation}
          beforeClick={closeFunc}
        />
        <Space h='md' />
        <MenuLinks
          title={t`About`}
          links={menuItemsAbout}
          beforeClick={closeFunc}
        />
      </div>
    </Flex>
  );
}
