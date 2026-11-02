import { GET } from './route';

describe('GET /api/healthz', () => {
  it('returns ok with a server time', async () => {
    const res = GET();
    expect(res.status).toBe(200);
    const body = (await res.json()) as { status: string; server_time: string };
    expect(body.status).toBe('ok');
    expect(Number.isNaN(Date.parse(body.server_time))).toBe(false);
  });
});
