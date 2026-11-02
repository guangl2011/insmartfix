import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi } from 'vitest';
import { createApiClient, type components } from '../src/index';

const spec = JSON.parse(
  readFileSync(fileURLToPath(new URL('../openapi.json', import.meta.url)), 'utf8'),
) as { openapi: string; paths: Record<string, unknown> };

describe('openapi.json', () => {
  it('is an OpenAPI 3.1 document exposing the health endpoints (spec §5)', () => {
    expect(spec.openapi).toMatch(/^3\.1\./);
    expect(Object.keys(spec.paths)).toEqual(expect.arrayContaining(['/v1/healthz', '/v1/readyz']));
  });
});

describe('v1 contract (spec §5, D11, D12)', () => {
  it('declares every v1 route', () => {
    expect(Object.keys(spec.paths).sort()).toEqual(
      [
        '/v1/auth/login',
        '/v1/auth/logout',
        '/v1/contractor/{cid}/accept/{wo}',
        '/v1/contractor/{cid}/decline/{wo}',
        '/v1/contractor/{cid}/schedule',
        '/v1/dispatch/workorders',
        '/v1/failure-codes',
        '/v1/healthz',
        '/v1/me',
        '/v1/me/accept/{wo}',
        '/v1/me/decline/{wo}',
        '/v1/me/schedule',
        '/v1/readyz',
        '/v1/workorders/{wo}',
        '/v1/workorders/{wo}/complete',
        '/v1/workorders/{wo}/photos',
        '/v1/workorders/{wo}/transition',
      ].sort(),
    );
  });

  it('exposes the error codes clients branch on', () => {
    const codes: components['schemas']['ErrorCode'][] = [
      'OFFER_UNAVAILABLE',
      'INVALID_TRANSITION',
      'ALREADY_COMPLETED',
      'IDEMPOTENCY_KEY_REUSED',
      'INVALID_CREDENTIALS',
    ];
    const declared = (
      spec as unknown as { components: { schemas: Record<string, { enum?: string[] }> } }
    ).components.schemas.ErrorCode?.enum;
    expect(declared).toEqual(expect.arrayContaining(codes));
  });
});

describe('createApiClient', () => {
  it('calls the typed endpoint on the configured base URL', async () => {
    const fetchMock = vi.fn(
      async (_req: Request) =>
        new Response(JSON.stringify({ status: 'ok', server_time: '2026-11-02T00:00:00Z' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    );
    const client = createApiClient('http://api.test/', { fetch: fetchMock });
    const { data, error } = await client.GET('/v1/healthz');
    expect(error).toBeUndefined();
    expect(data?.status).toBe('ok');
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]![0].url).toBe('http://api.test/v1/healthz');
  });
});
