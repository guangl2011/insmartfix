import { fireEvent, renderRouter, screen } from 'expo-router/testing-library';
import { appRoutes } from '../helpers/router';
import { seedSession } from '../helpers/session';
import { createTestServices } from '../helpers/services';
import { ergonomicsViolations } from '../helpers/ergo';

function routes() {
  const { services, mock } = createTestServices();
  seedSession(mock);
  return appRoutes(services);
}

describe('shell and navigation (M5-T2)', () => {
  it('T-NAV-1 shows two nav items and a disabled Voice intake stub', async () => {
    await renderRouter(routes(), { initialUrl: '/' });
    await screen.findByTestId('inbox-screen');
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
    await screen.findByTestId('inbox-screen');
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

  it('T-NAV-1 /jobs/[id] resolves', async () => {
    await renderRouter(routes(), { initialUrl: '/jobs/wo-123' });
    await screen.findByTestId('job-screen');
    expect(screen).toHavePathname('/jobs/wo-123');
    expect(screen.getByLabelText('Work order wo-123')).toBeOnTheScreen();
  });

  it('T-NAV-1 /login resolves', async () => {
    const { services } = createTestServices();
    await renderRouter(appRoutes(services), { initialUrl: '/login' });
    expect(await screen.findByTestId('login-screen')).toBeOnTheScreen();
  });

  it('T-ERGO-1 nav targets are ≥ 44 pt and labels ≥ 16 pt', async () => {
    await renderRouter(routes(), { initialUrl: '/inbox' });
    await screen.findByTestId('inbox-screen');
    expect(ergonomicsViolations(screen.container)).toEqual([]);
  });
});
