import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi } from 'vitest';
import { createApiClient } from '../src/index';

const spec = JSON.parse(
  readFileSync(fileURLToPath(new URL('../openapi.json', import.meta.url)), 'utf8'),
) as { openapi: string; paths: Record<string, unknown> };

describe('openapi.json', () => {
  it('is an OpenAPI 3.1 document exposing the health endpoints (spec §5)', () => {
    expect(spec.openapi).toMatch(/^3\.1\./);
    expect(Object.keys(spec.paths)).toEqual(expect.arrayContaining(['/v1/healthz', '/v1/readyz']));
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
