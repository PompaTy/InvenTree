import { t } from '@lingui/core/macro';

import { ModelType } from '@lib/enums/ModelType';
import { UserRoles } from '@lib/enums/Roles';
import type { SettingsStateProps } from '@lib/types/Settings';
import type { UserStateProps } from '@lib/types/User';
import type { MenuLinkItem } from '../components/items/MenuLinks';

export const DEFAULT_NAVIGATION_TABS = [
  'vhc-boxes',
  'parts',
  'stock',
  'vhc-box-scan',
];

/**
 * Construct the internal destinations displayed in the main navigation menu.
 * Header tab customization uses this same source so the two stay in sync.
 */
export function getNavigationMenuItems(
  user: UserStateProps,
  globalSettings: SettingsStateProps
) {
  const navigate: MenuLinkItem[] = [
    {
      id: 'home',
      title: t`Dashboard`,
      link: '/',
      icon: 'dashboard'
    },
    {
      id: 'parts',
      title: t`Parts`,
      hidden: !user.hasViewPermission(ModelType.part),
      link: '/part',
      icon: 'part'
    },
    {
      id: 'stock',
      title: t`Stock`,
      link: '/stock',
      hidden: !user.hasViewPermission(ModelType.stockitem),
      icon: 'stock'
    },
    {
      id: 'vhc-boxes',
      title: t`VHC Boxes`,
      link: '/boxes',
      icon: 'stock'
    },
    {
      id: 'build',
      title: t`Manufacturing`,
      link: '/manufacturing/',
      hidden: !user.hasViewRole(UserRoles.build),
      icon: 'build'
    },
    {
      id: 'purchasing',
      title: t`Purchasing`,
      link: '/purchasing/',
      hidden: !user.hasViewRole(UserRoles.purchase_order),
      icon: 'purchase_orders'
    },
    {
      id: 'sales',
      title: t`Sales`,
      link: '/sales/',
      hidden: !user.hasViewRole(UserRoles.sales_order),
      icon: 'sales_orders'
    },
    {
      id: 'users',
      title: t`Users`,
      link: '/core/index/users',
      icon: 'user'
    },
    {
      id: 'groups',
      title: t`Groups`,
      link: '/core/index/groups',
      icon: 'group'
    }
  ];

  const settings: MenuLinkItem[] = [
    {
      id: 'notifications',
      title: t`Notifications`,
      link: '/notifications',
      icon: 'notification'
    },
    {
      id: 'user-settings',
      title: t`User Settings`,
      link: '/settings/user',
      icon: 'user'
    },
    {
      id: 'system-settings',
      title: t`System Settings`,
      link: '/settings/system',
      icon: 'system',
      hidden: !user.isStaff()
    },
    {
      id: 'admin-center',
      title: t`Admin Center`,
      link: '/settings/admin',
      icon: 'admin',
      hidden: !user.isStaff()
    }
  ];

  const actions: MenuLinkItem[] = [
    {
      id: 'barcode',
      title: t`Scan Barcode`,
      link: '/scan',
      icon: 'barcode',
      hidden: !globalSettings.isSet('BARCODE_ENABLE')
    },
    {
      id: 'vhc-box-scan',
      title: t`Scan VHC Box`,
      link: '/boxes/scan',
      icon: 'barcode'
    }
  ];

  return { navigate, settings, actions };
}
