// M3-T1: generated client factory, error-envelope parsing and Idempotency-Key helpers.
import { describe, expect, expectTypeOf, it, vi } from 'vitest';
import {
  ApiRequestError,
  apiErrorInfo,
  createApiClient,
  idempotencyHeader,
  IDEMPOTENCY_KEY_PATTERN,
  isApiError,
  isValidIdempotencyKey,
  newIdempotencyKey,
  unwrap,
  type ErrorCode,
  type WorkOrderDetail,
} from '../src/index';

const WO = '7f0c2a52-6a83-4c1c-9a35-2f0b3c7c1d11';
const NOW = '2026-11-02T15:00:00Z';

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const envelope = (code: ErrorCode, message: string, reason?: string) => ({
  error: { code, message, ...(reason ? { reason } : {}) },
  server_time: NOW,
});

function client(respond: (req: Request) => Response, extra: Record<string, unknown> = {}) {
  const fetch = vi.fn(async (req: Request) => respond(req));
  return { fetch, api: createApiClient({ baseUrl: 'http://api.test/', fetch, ...extra }) };
}

describe('createApiClient', () => {
  it('adds the bearer token from getToken and keeps an explicit Authorization header', async () => {
    const { fetch, api } = client(() => json(200, { server_time: NOW }), {
      getToken: async () => 'tok-123',
    });
    await api.GET('/v1/me');
    expect(fetch.mock.calls[0]![0].headers.get('Authorization')).toBe('Bearer tok-123');
    await api.GET('/v1/me', { headers: { Authorization: 'Bearer explicit' } });
    expect(fetch.mock.calls[1]![0].headers.get('Authorization')).toBe('Bearer explicit');
  });

  it('sends no Authorization header without a token', async () => {
    const { fetch, api } = client(() => json(200, {}), { getToken: () => null });
    await api.GET('/v1/healthz');
    expect(fetch.mock.calls[0]![0].headers.has('Authorization')).toBe(false);
  });

  it('reports server_time with the send time, and ignores bodies without it', async () => {
    const onServerTime = vi.fn();
    let t = 1000;
    const { api } = client(
      (req) =>
        req.url.endsWith('/healthz')
          ? json(200, { status: 'ok', server_time: NOW })
          : req.url.endsWith('/readyz')
            ? new Response('not json', {
                status: 503,
                headers: { 'content-type': 'application/json' },
              })
            : new Response(null, { status: 204 }),
      { onServerTime, now: () => (t += 10) },
    );
    await api.GET('/v1/healthz');
    expect(onServerTime).toHaveBeenCalledWith(NOW, { sentAt: 1010 });
    await api.GET('/v1/readyz');
    await api.POST('/v1/auth/logout');
    expect(onServerTime).toHaveBeenCalledOnce();
  });

  it('accepts the M0 positional form and sends the Idempotency-Key header', async () => {
    const fetch = vi.fn(async (_req: Request) => json(200, { server_time: NOW }));
    const api = createApiClient('http://api.test///', { fetch, headers: { 'x-request-id': 'r1' } });
    const key = newIdempotencyKey();
    await api.POST('/v1/me/accept/{wo}', {
      params: { path: { wo: WO }, header: idempotencyHeader(key) },
    });
    const req = fetch.mock.calls[0]![0];
    expect(req.url).toBe(`http://api.test/v1/me/accept/${WO}`);
    expect(req.headers.get('Idempotency-Key')).toBe(key);
    expect(req.headers.get('x-request-id')).toBe('r1');
  });

  it('types responses from the generated schema', async () => {
    const { api } = client(() => json(200, {}));
    const res = await api.GET('/v1/workorders/{wo}', { params: { path: { wo: WO } } });
    expect(res.response.status).toBe(200);
    expectTypeOf<NonNullable<typeof res.data>>().toHaveProperty('pre_diagnostic_available');
    expectTypeOf<WorkOrderDetail>().toHaveProperty('lifecycle_history');
  });
});

describe('error envelope parsing', () => {
  it('recognizes the 409 OFFER_UNAVAILABLE envelope with its reason', async () => {
    const { api } = client(() =>
      json(409, envelope('OFFER_UNAVAILABLE', 'Offer gone', 'reassigned')),
    );
    const res = await api.POST('/v1/me/accept/{wo}', { params: { path: { wo: WO } } });
    expect(res.response.status).toBe(409);
    expect(isApiError(res.error)).toBe(true);
    expect(isApiError(res.error, 'OFFER_UNAVAILABLE')).toBe(true);
    expect(isApiError(res.error, 'ALREADY_COMPLETED')).toBe(false);
    expect(apiErrorInfo(res.error)).toEqual({
      code: 'OFFER_UNAVAILABLE',
      message: 'Offer gone',
      reason: 'reassigned',
    });
    if (isApiError(res.error, 'OFFER_UNAVAILABLE') && !(res.error instanceof ApiRequestError))
      expectTypeOf(res.error.error.code).toEqualTypeOf<'OFFER_UNAVAILABLE'>();
  });

  it('unwrap returns data on 2xx and throws ApiRequestError otherwise', async () => {
    const { api } = client((req) =>
      req.url.includes('/complete')
        ? json(409, envelope('ALREADY_COMPLETED', 'Already completed'))
        : req.url.endsWith('/logout')
          ? new Response(null, { status: 204 })
          : json(200, { status: 'ok', server_time: NOW }),
    );
    expect(unwrap(await api.GET('/v1/healthz'))).toMatchObject({ status: 'ok' });
    expect(unwrap(await api.POST('/v1/auth/logout'))).toBeUndefined();
    const res = await api.POST('/v1/workorders/{wo}/complete', {
      params: { path: { wo: WO } },
      body: {
        failure_code: 'COMP-CONTACTOR',
        actual_fault_matched: true,
        parts_used: [],
        labor_hours: 1,
        technician_id: 'Marco Rossi',
        photo_ids: [],
      },
    });
    let thrown: unknown;
    try {
      unwrap(res);
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(ApiRequestError);
    const err = thrown as ApiRequestError;
    expect(err).toMatchObject({
      name: 'ApiRequestError',
      status: 409,
      code: 'ALREADY_COMPLETED',
      reason: null,
      serverTime: NOW,
      message: 'Already completed',
    });
    expect(isApiError(err, 'ALREADY_COMPLETED')).toBe(true);
    expect(isApiError(err, 'OFFER_UNAVAILABLE')).toBe(false);
    expect(isApiError(err)).toBe(true);
    expect(apiErrorInfo(err)).toEqual({
      code: 'ALREADY_COMPLETED',
      message: 'Already completed',
      reason: null,
    });
  });

  it('handles non-envelope failures (proxy HTML 502, empty 500, odd shapes)', () => {
    const r = (status: number) => new Response(null, { status });
    const e502 = new ApiRequestError(502, '<html>Bad gateway</html>');
    expect(e502).toMatchObject({ status: 502, code: null, message: 'HTTP 502', serverTime: null });
    expect(isApiError(e502)).toBe(false);
    expect(apiErrorInfo(e502)).toEqual({ code: null, message: null, reason: null });
    expect(() => unwrap({ response: r(500) })).toThrow('HTTP 500');
    for (const odd of [
      null,
      undefined,
      'x',
      42,
      {},
      { error: null },
      { error: { code: 1, message: 'm' } },
      { error: { code: 'X' } },
    ])
      expect(isApiError(odd)).toBe(false);
    expect(apiErrorInfo({ nope: true })).toEqual({ code: null, message: null, reason: null });
  });
});

describe('Idempotency-Key helpers', () => {
  it('generates distinct UUIDv4 keys that match the contract pattern', () => {
    const keys = new Set(Array.from({ length: 50 }, () => newIdempotencyKey()));
    expect(keys.size).toBe(50);
    for (const k of keys) {
      expect(k).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
      expect(isValidIdempotencyKey(k)).toBe(true);
    }
  });

  it('falls back to getRandomValues (React Native without randomUUID) and never to Math.random', () => {
    const fixed = {
      getRandomValues: <T extends Uint8Array>(a: T) => {
        a.fill(0xff);
        return a;
      },
    };
    expect(newIdempotencyKey(fixed)).toBe('ffffffff-ffff-4fff-bfff-ffffffffffff');
    expect(() => newIdempotencyKey({})).toThrow(/secure random/);
  });

  it('validates keys against the contract pattern', () => {
    expect(IDEMPOTENCY_KEY_PATTERN.source).toBe('^[A-Za-z0-9._:-]{8,128}$');
    expect(idempotencyHeader('queue:complete:1234')).toEqual({
      'Idempotency-Key': 'queue:complete:1234',
    });
    for (const bad of ['short', 'has space here', 'x'.repeat(129), 'émoji-key-1'])
      expect(() => idempotencyHeader(bad)).toThrow(/Idempotency-Key/);
  });
});
