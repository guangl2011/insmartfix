import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { render } from '@testing-library/react-native';
import { act, fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';
import { LOGIN_COPY } from '../../app/login';
import { SESSION_KEY, SessionProvider, useSession, type Session } from '../../src/auth';
import { ServicesProvider } from '../../src/data';
import { PRIMARY_ACTION_TESTID } from '../../src/ui';
import { ergonomicsViolations } from '../helpers/ergo';
import { appRoutes } from '../helpers/router';
import { createTestServices, gate, type TestServiceOptions } from '../helpers/services';
import { keychain, seedSession } from '../helpers/session';

async function openLogin(opts: TestServiceOptions = {}) {
  const t = createTestServices(opts);
  await renderRouter(appRoutes(t.services), { initialUrl: '/' });
  await screen.findByTestId('login-screen');
  return t;
}

const signInButton = () => screen.getByTestId(PRIMARY_ACTION_TESTID);

async function fill(email: string, password: string) {
  await fireEvent.changeText(screen.getByLabelText('Email'), email);
  await fireEvent.changeText(screen.getByLabelText('Password'), password);
}

describe('login (M5-T3)', () => {
  it('T-AUTH-1 valid login lands on the inbox', async () => {
    await openLogin();
    expect(screen).toHavePathname('/login');
    expect(screen.getByText(LOGIN_COPY.tagline)).toBeOnTheScreen();
    await fill('marco@test.insmart.ai', 'correct horse');
    await fireEvent.press(signInButton());
    expect(await screen.findByTestId('inbox-screen')).toBeOnTheScreen();
    expect(screen).toHavePathname('/inbox');
  });

  it('T-AUTH-1 FR-1.5 Sign in is enabled only when both fields are non-empty', async () => {
    await openLogin();
    expect(signInButton()).toBeDisabled();
    await fireEvent.changeText(screen.getByLabelText('Email'), 'marco@test.insmart.ai');
    expect(signInButton()).toBeDisabled();
    await fireEvent.changeText(screen.getByLabelText('Password'), 'pw');
    expect(signInButton()).toBeEnabled();
    await fireEvent.changeText(screen.getByLabelText('Email'), '   ');
    expect(signInButton()).toBeDisabled();
  });

  it('T-AUTH-1 FR-1.5 while submitting the button spins and the form is disabled', async () => {
    const hold = gate('/auth/login');
    await openLogin({ wrapFetch: hold.wrap });
    await fill('marco@test.insmart.ai', 'pw');
    await fireEvent.press(signInButton());
    expect(signInButton()).toBeBusy();
    expect(signInButton()).toBeDisabled();
    expect(screen.getByLabelText('Email').props.editable).toBe(false);
    expect(screen.getByLabelText('Password').props.editable).toBe(false);
    hold.release();
    expect(await screen.findByTestId('inbox-screen')).toBeOnTheScreen();
  });

  it('T-AUTH-2 bad credentials show the inline error and keep the fields', async () => {
    await openLogin();
    await fill('marco@test.insmart.ai', 'wrong-password');
    await fireEvent.press(signInButton());
    expect(await screen.findByText(LOGIN_COPY.invalid)).toBeOnTheScreen();
    expect(screen.getByLabelText('Email').props.value).toBe('marco@test.insmart.ai');
    expect(screen.getByLabelText('Password').props.value).toBe('wrong-password');
    expect(screen).toHavePathname('/login');
    expect(screen.queryByTestId('login-retry')).toBeNull();
    expect(keychain.has(SESSION_KEY)).toBe(false);
  });

  it('T-AUTH-3 network down shows the connection message, and Retry signs in', async () => {
    const t = await openLogin();
    t.mock.scenarios.networkErrorNext(1, { path: '/auth/login' });
    await fill('marco@test.insmart.ai', 'pw');
    await fireEvent.press(signInButton());
    expect(await screen.findByText(LOGIN_COPY.network)).toBeOnTheScreen();
    expect(screen.getByLabelText('Email').props.value).toBe('marco@test.insmart.ai');
    await fireEvent.press(screen.getByTestId('login-retry'));
    expect(await screen.findByTestId('inbox-screen')).toBeOnTheScreen();
  });

  it('T-AUTH-3 a 5xx at login is reported without losing the fields', async () => {
    const t = await openLogin();
    t.mock.scenarios.failNext(503, 1, { path: '/auth/login' });
    await fill('marco@test.insmart.ai', 'pw');
    await fireEvent.press(signInButton());
    expect(await screen.findByText(LOGIN_COPY.server)).toBeOnTheScreen();
    expect(screen.getByLabelText('Password').props.value).toBe('pw');
  });

  it('T-AUTH-5 the token is stored only in the secure store (device-only), never AsyncStorage or logs', async () => {
    const logs = (['log', 'info', 'warn', 'error', 'debug'] as const).map((k) =>
      jest.spyOn(console, k),
    );
    await openLogin();
    await fill('marco@test.insmart.ai', 'pw');
    await fireEvent.press(signInButton());
    await screen.findByTestId('inbox-screen');

    const stored = JSON.parse(keychain.get(SESSION_KEY)!) as { access_token: string };
    expect(stored.access_token).toMatch(/^mock\./);
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith(SESSION_KEY, expect.any(String), {
      keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
    });
    const keys = await AsyncStorage.getAllKeys();
    const values = (await AsyncStorage.multiGet(keys)).map(([, v]) => v ?? '');
    expect(values.some((v) => v.includes(stored.access_token))).toBe(false);
    for (const spy of logs) {
      expect(JSON.stringify(spy.mock.calls)).not.toContain(stored.access_token);
      spy.mockRestore();
    }
  });

  it('T-AUTH-5 restores a stored session at launch', async () => {
    const t = createTestServices();
    seedSession(t.mock);
    await renderRouter(appRoutes(t.services), { initialUrl: '/' });
    expect(await screen.findByTestId('inbox-screen')).toBeOnTheScreen();
  });

  it('T-AUTH-5 drops an expired stored session at launch', async () => {
    const t2 = createTestServices();
    seedSession(t2.mock, 'marco@test.insmart.ai', -1000);
    await renderRouter(appRoutes(t2.services), { initialUrl: '/inbox' });
    expect(await screen.findByTestId('login-screen')).toBeOnTheScreen();
    await waitFor(() => expect(keychain.has(SESSION_KEY)).toBe(false));
  });

  it('a 401 on an authenticated call ends the session (server-side revocation, D11)', async () => {
    const t = createTestServices();
    const u = seedSession(t.mock);
    let session: Session | null = null;
    function Probe() {
      session = useSession();
      return null;
    }
    await render(
      <ServicesProvider services={t.services}>
        <SessionProvider>
          <Probe />
        </SessionProvider>
      </ServicesProvider>,
    );
    await waitFor(() => expect(session!.status).toBe('signedIn'));
    const me = await session!.api.GET('/v1/me');
    expect(me.response.status).toBe(200); // the mock only answers a valid bearer token
    u.token_version += 1;
    await act(async () => {
      await session!.api.GET('/v1/me');
    });
    await waitFor(() => expect(session!.status).toBe('signedOut'));
    expect(keychain.has(SESSION_KEY)).toBe(false);
  });

  it('T-ERGO-1 login fields and buttons meet 44 pt / 16 pt', async () => {
    const t = await openLogin();
    t.mock.scenarios.networkErrorNext(1);
    await fill('a@b.c', 'pw');
    await fireEvent.press(signInButton());
    await screen.findByTestId('login-retry');
    expect(ergonomicsViolations(screen.container)).toEqual([]);
    expect(screen.getAllByTestId(PRIMARY_ACTION_TESTID)).toHaveLength(1);
  });
});
