import { createMockApi } from '@insmartfix/contracts/mocks';
import { getMobileConfig } from '../../src/config';
import {
  createAppServices,
  createLiveFetch,
  createMockBackend,
  createMockFetch,
  withTimeout,
} from '../../src/data';
import { initCrashReporting } from '../../src/observability/crash';
import * as Sentry from '@sentry/react-native';

const BASE = 'http://api.test';

describe('data source switch (M5-T2)', () => {
  it('mock: answers /v1 from the contract mocks in-process and moves the server clock', async () => {
    const mock = createMockApi({ baseUrl: BASE });
    const services = createAppServices(getMobileConfig({ EXPO_PUBLIC_API_BASE_URL: BASE }), {
      mock,
      fetch: createMockFetch(mock),
      connectivity: { isOnline: () => true, subscribe: () => () => {} },
      visibility: { isVisible: () => true, subscribe: () => () => {} },
    });
    const api = services.createClient();
    const res = await api.POST('/v1/auth/login', {
      body: { email: 'marco@test.insmart.ai', password: 'pw' },
    });
    expect(res.response.status).toBe(200);
    expect(res.data?.user.name).toBe('Marco Rossi');
    expect(services.clock.hasObservation()).toBe(true);
  });

  it('mock: unknown routes are 404 and injected network failures reject like fetch', async () => {
    const mock = createMockApi({ baseUrl: BASE });
    const f = createMockFetch(mock);
    expect((await f(new Request(`${BASE}/nope`))).status).toBe(404);
    mock.scenarios.networkErrorNext(1);
    await expect(f(new Request(`${BASE}/v1/healthz`))).rejects.toThrow('Network request failed');
  });

  it('applies MOCK_SCENARIOS to the in-process backend', async () => {
    const mock = createMockBackend(BASE, 'fail=503:1:/healthz');
    const res = await createMockFetch(mock)(new Request(`${BASE}/v1/healthz`));
    expect(res.status).toBe(503);
  });

  it('defaults to the mock backend unless DATA_SOURCE=live', () => {
    const ports = {
      connectivity: { isOnline: () => true, subscribe: () => () => {} },
      visibility: { isVisible: () => true, subscribe: () => () => {} },
    };
    expect(createAppServices(getMobileConfig({}), ports).mock).not.toBeNull();
    expect(
      createAppServices(getMobileConfig({ EXPO_PUBLIC_DATA_SOURCE: 'live' }), ports).mock,
    ).toBeNull();
  });

  it('live: a request that outlives the timeout rejects (fails fast on bad signal)', async () => {
    jest.useFakeTimers();
    try {
      const hang = (req: Request) =>
        new Promise<Response>((_, reject) =>
          req.signal.addEventListener('abort', () => reject(new Error('aborted'))),
        );
      const p = withTimeout(hang, 1000)(new Request(`${BASE}/v1/me`));
      jest.advanceTimersByTime(1000);
      await expect(p).rejects.toThrow('aborted');
    } finally {
      jest.useRealTimers();
    }
  });

  it('live: passes the request through to the platform fetch', async () => {
    const platform = jest.fn(async () => new Response('{}', { status: 200 }));
    const res = await createLiveFetch(platform as unknown as typeof fetch)(
      new Request(`${BASE}/v1/healthz`),
    );
    expect(res.status).toBe(200);
    expect(platform).toHaveBeenCalledTimes(1);
  });
});

describe('crash reporting (NFR-7)', () => {
  it('is off without a DSN and on, without default PII, with one', () => {
    expect(initCrashReporting({ dsn: null })).toBe(false);
    expect(Sentry.init).not.toHaveBeenCalled();
    expect(initCrashReporting({ dsn: 'https://k@o.example/1' })).toBe(true);
    const opts = (Sentry.init as jest.Mock).mock.calls[0][0];
    expect(opts.sendDefaultPii).toBe(false);
    expect(
      opts.beforeBreadcrumb({
        category: 'fetch',
        data: { url: 'http://x/v1/workorders/1', method: 'GET', status_code: 200 },
      }),
    ).toEqual({
      category: 'fetch',
      data: { method: 'GET', status_code: 200 },
    });
    expect(opts.beforeBreadcrumb({ category: 'ui' })).toEqual({ category: 'ui' });
  });
});
