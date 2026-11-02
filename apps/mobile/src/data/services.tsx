/**
 * App-wide services (dependency injection): config, the server clock, core ports and the HTTP
 * transport. Screens read them with `useServices()`; tests pass fakes to `ServicesProvider`.
 */
import {
  createServerClock,
  systemClock,
  type ConnectivityPort,
  type ServerClock,
  type StoragePort,
  type VisibilityPort,
} from '@insmartfix/core';
import { createApiClient, type ApiClient } from '@insmartfix/contracts';
import type { MockApi } from '@insmartfix/contracts/mocks';
import { createContext, useContext, type ReactNode } from 'react';
import {
  createAppStateVisibility,
  createAsyncStorage,
  createNetInfoConnectivity,
} from '../adapters';
import { getMobileConfig, type MobileConfig } from '../config';
import { createLiveFetch, createMockBackend, createMockFetch, type AppFetch } from './fetch';

export type TokenSource = () => string | null | undefined | Promise<string | null | undefined>;

export interface AppServices {
  config: MobileConfig;
  /** Server time (FR-2.4): every response's `server_time` updates its offset. */
  clock: ServerClock;
  connectivity: ConnectivityPort;
  visibility: VisibilityPort;
  /** Durable app storage (AsyncStorage). Never holds the token. */
  storage: StoragePort;
  fetch: AppFetch;
  /** The in-process contract mock, when `DATA_SOURCE=mock`. */
  mock: MockApi | null;
  /** Typed `/v1` client over `fetch`, observing `server_time` on every response. */
  createClient(getToken?: TokenSource): ApiClient;
}

export type ServiceOverrides = Partial<Omit<AppServices, 'createClient'>>;

export function createAppServices(
  config: MobileConfig = getMobileConfig(),
  overrides: ServiceOverrides = {},
): AppServices {
  const mock =
    overrides.mock !== undefined
      ? overrides.mock
      : config.dataSource === 'mock'
        ? createMockBackend(config.apiBaseUrl, config.mockScenarios)
        : null;
  const fetchImpl = overrides.fetch ?? (mock ? createMockFetch(mock) : createLiveFetch());
  const clock = overrides.clock ?? createServerClock(systemClock());
  return {
    config,
    clock,
    connectivity: overrides.connectivity ?? createNetInfoConnectivity(),
    visibility: overrides.visibility ?? createAppStateVisibility(),
    storage: overrides.storage ?? createAsyncStorage(),
    fetch: fetchImpl,
    mock,
    createClient: (getToken) =>
      createApiClient({
        baseUrl: config.apiBaseUrl,
        fetch: fetchImpl,
        getToken,
        onServerTime: (t, { sentAt }) => {
          clock.observe(t, { sentAt });
        },
      }),
  };
}

const ServicesContext = createContext<AppServices | null>(null);

export function ServicesProvider({
  services,
  children,
}: {
  services: AppServices;
  children: ReactNode;
}) {
  return <ServicesContext.Provider value={services}>{children}</ServicesContext.Provider>;
}

export function useServices(): AppServices {
  const s = useContext(ServicesContext);
  if (!s) throw new Error('useServices() outside <ServicesProvider>');
  return s;
}

let appServices: AppServices | null = null;

/** The process-wide services for the running app (created on first use). */
export function getAppServices(): AppServices {
  appServices ??= createAppServices();
  return appServices;
}
