/** The real route modules, rendered by expo-router's testing library with injected services. */
import RootLayout from '../../app/_layout';
import TabsLayout from '../../app/(tabs)/_layout';
import Index from '../../app/index';
import Inbox from '../../app/(tabs)/inbox';
import Account from '../../app/(tabs)/account';
import JobsLayout from '../../app/jobs/_layout';
import Job from '../../app/jobs/[id]/index';
import Login from '../../app/login';
import type { AppServices } from '../../src/data';

export function appRoutes(services: AppServices) {
  return {
    _layout: () => <RootLayout services={services} />,
    index: Index,
    login: Login,
    '(tabs)/_layout': TabsLayout,
    '(tabs)/inbox': Inbox,
    '(tabs)/account': Account,
    'jobs/_layout': JobsLayout,
    'jobs/[id]/index': Job,
  };
}
