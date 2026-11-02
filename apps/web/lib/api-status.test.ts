import { probeApi } from './api-status';

const live = { dataSource: 'live', apiBaseUrl: 'http://api.test' } as const;
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

describe('probeApi', () => {
  it('reports mock without calling the network', async () => {
    const f = vi.fn();
    await expect(probeApi({ ...live, dataSource: 'mock' }, f)).resolves.toBe('mock');
    expect(f).not.toHaveBeenCalled();
  });

  it('is reachable when /v1/healthz says ok', async () => {
    const f = vi.fn(async (_req: Request) => json({ status: 'ok', server_time: 'x' }));
    await expect(probeApi(live, f as unknown as typeof fetch)).resolves.toBe('reachable');
    expect(f.mock.calls[0]![0].url).toBe('http://api.test/v1/healthz');
  });

  it('is unreachable on a non-2xx or a network error', async () => {
    const bad = vi.fn(async () => json({ error: { code: 'X', message: 'y' } }, 503));
    await expect(probeApi(live, bad as unknown as typeof fetch)).resolves.toBe('unreachable');
    const down = vi.fn(async () => {
      throw new TypeError('fetch failed');
    });
    await expect(probeApi(live, down as unknown as typeof fetch)).resolves.toBe('unreachable');
  });
});
