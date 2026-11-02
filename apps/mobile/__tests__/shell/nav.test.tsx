import { fireEvent, renderRouter, screen } from 'expo-router/testing-library';
import RootLayout from '../../app/_layout';
import TabsLayout from '../../app/(tabs)/_layout';
import Index from '../../app/index';
import Inbox from '../../app/(tabs)/inbox';
import Account from '../../app/(tabs)/account';
import Job from '../../app/jobs/[id]/index';
import Login from '../../app/login';
import { createTestServices } from '../helpers/services';
import { ergonomicsViolations } from '../helpers/ergo';

function routes() {
  const { services } = createTestServices();
  return {
    _layout: () => <RootLayout services={services} />,
    index: Index,
    login: Login,
    '(tabs)/_layout': TabsLayout,
    '(tabs)/inbox': Inbox,
    '(tabs)/account': Account,
    'jobs/[id]/index': Job,
  };
}

describe('shell and navigation (M5-T2)', () => {
  it('T-NAV-1 shows two nav items and a disabled Voice intake stub', async () => {
    await renderRouter(routes(), { initialUrl: '/' });
    expect(screen).toHavePathname('/inbox');
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((t) => t.props.accessibilityLabel)).toEqual([
      'Inbox',
      'Account',
      'Voice intake',
    ]);
    expect(screen.getByRole('tab', { name: 'Inbox' })).toBeSelected();
    expect(screen.getByRole('tab', { name: 'Voice intake' })).toBeDisabled();
  });

  it('T-NAV-1 Inbox and Account routes resolve from the nav; Voice intake goes nowhere', async () => {
    await renderRouter(routes(), { initialUrl: '/inbox' });
    await fireEvent.press(screen.getByRole('tab', { name: 'Account' }));
    expect(screen).toHavePathname('/account');
    expect(screen.getByTestId('account-screen')).toBeOnTheScreen();
    expect(screen.getByRole('tab', { name: 'Account' })).toBeSelected();

    await fireEvent.press(screen.getByRole('tab', { name: 'Voice intake' }));
    expect(screen).toHavePathname('/account');

    await fireEvent.press(screen.getByRole('tab', { name: 'Inbox' }));
    expect(screen).toHavePathname('/inbox');
    expect(screen.getByTestId('inbox-screen')).toBeOnTheScreen();
  });

  it('T-NAV-1 /jobs/[id] and /login resolve', async () => {
    await renderRouter(routes(), { initialUrl: '/jobs/wo-123' });
    expect(screen).toHavePathname('/jobs/wo-123');
    expect(screen.getByLabelText('Work order wo-123')).toBeOnTheScreen();

    await renderRouter(routes(), { initialUrl: '/login' });
    expect(screen.getByTestId('login-screen')).toBeOnTheScreen();
  });

  it('T-ERGO-1 nav targets are ≥ 44 pt and labels ≥ 16 pt', async () => {
    await renderRouter(routes(), { initialUrl: '/inbox' });
    expect(ergonomicsViolations(screen.container)).toEqual([]);
  });
});
