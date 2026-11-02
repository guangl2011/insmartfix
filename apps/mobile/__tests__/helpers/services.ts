/** Test services: in-process contract mock, in-memory storage and controllable ports. */
import { createMockApi, type MockApi } from '@insmartfix/contracts/mocks';
import {
  createMemoryStorage,
  createFakeConnectivity,
  createFakeVisibility,
} from '@insmartfix/core/testing';
import { createAppServices, createMockFetch, type AppServices } from '../../src/data';
import { getMobileConfig } from '../../src/config';

export const TEST_BASE_URL = 'http://api.test';

export interface TestServices {
  services: AppServices;
  mock: MockApi;
  connectivity: ReturnType<typeof createFakeConnectivity>;
  visibility: ReturnType<typeof createFakeVisibility>;
  storage: ReturnType<typeof createMemoryStorage>;
}

export function createTestServices(
  opts: { mock?: MockApi; storage?: ReturnType<typeof createMemoryStorage> } = {},
): TestServices {
  const mock = opts.mock ?? createMockApi({ baseUrl: TEST_BASE_URL });
  const connectivity = createFakeConnectivity(true);
  const visibility = createFakeVisibility(true);
  const storage = opts.storage ?? createMemoryStorage();
  const services = createAppServices(
    getMobileConfig({ EXPO_PUBLIC_DATA_SOURCE: 'mock', EXPO_PUBLIC_API_BASE_URL: TEST_BASE_URL }),
    {
      mock,
      fetch: createMockFetch(mock),
      connectivity: connectivity.port,
      visibility: visibility.port,
      storage,
    },
  );
  return { services, mock, connectivity, visibility, storage };
}
