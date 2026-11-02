/** Test services: in-process contract mock, in-memory storage and controllable ports. */
import { createMockApi, type MockApi } from '@insmartfix/contracts/mocks';
import {
  createMemoryStorage,
  createFakeConnectivity,
  createFakeVisibility,
} from '@insmartfix/core/testing';
import {
  createAppServices,
  createMockFetch,
  type AppFetch,
  type AppServices,
} from '../../src/data';
import { getMobileConfig } from '../../src/config';

export const TEST_BASE_URL = 'http://api.test';

export interface TestServices {
  services: AppServices;
  mock: MockApi;
  connectivity: ReturnType<typeof createFakeConnectivity>;
  visibility: ReturnType<typeof createFakeVisibility>;
  storage: ReturnType<typeof createMemoryStorage>;
}

export interface TestServiceOptions {
  mock?: MockApi;
  storage?: ReturnType<typeof createMemoryStorage>;
  /** Wraps the transport (e.g. to hold a request open and observe an in-flight state). */
  wrapFetch?: (inner: AppFetch) => AppFetch;
}

/** A transport wrapper that holds matching requests until `release()` (in-flight UI states). */
export function gate(match: string) {
  let open!: () => void;
  const opened = new Promise<void>((r) => {
    open = r;
  });
  return {
    wrap:
      (inner: AppFetch): AppFetch =>
      async (req) => {
        if (new URL(req.url).pathname.includes(match)) await opened;
        return inner(req);
      },
    release: () => open(),
  };
}

export function createTestServices(opts: TestServiceOptions = {}): TestServices {
  const mock = opts.mock ?? createMockApi({ baseUrl: TEST_BASE_URL });
  const connectivity = createFakeConnectivity(true);
  const visibility = createFakeVisibility(true);
  const storage = opts.storage ?? createMemoryStorage();
  const services = createAppServices(
    getMobileConfig({ EXPO_PUBLIC_DATA_SOURCE: 'mock', EXPO_PUBLIC_API_BASE_URL: TEST_BASE_URL }),
    {
      mock,
      fetch: (opts.wrapFetch ?? ((f) => f))(createMockFetch(mock)),
      connectivity: connectivity.port,
      visibility: visibility.port,
      storage,
    },
  );
  return { services, mock, connectivity, visibility, storage };
}
