import { describe, expect, it } from 'vitest';
import { createServerClock, formatSla, SLA_GLYPH, slaRemainingMs } from '../src/index';
import { createFakeClock } from '../src/testing';

const S = 1000;
const M = 60 * S;

describe('T-SLA-1 formatSla follows the design §7.5 table', () => {
  it.each([
    // > 5 min: regular
    [12 * M, '12m left', 'regular', false],
    [5 * M + 1, '6m left', 'regular', false],
    // 1–5 min: medium
    [5 * M, '5m left', 'medium', false],
    [4 * M, '4m left', 'medium', false],
    [3 * M + 58 * S, '4m left', 'medium', false],
    [60 * S, '1m left', 'medium', false],
    // < 60 s: bold with a subtle pulse
    [59_999, '60s left', 'bold', true],
    [45 * S, '45s left', 'bold', true],
    [44_200, '45s left', 'bold', true],
    [1, '1s left', 'bold', true],
  ] as const)('%d ms → %s (%s)', (ms, label, weight, pulse) => {
    expect(formatSla(ms)).toMatchObject({ label, weight, glyph: SLA_GLYPH, pulse, muted: false });
  });

  it('past the deadline is the advisory "Expiring" (bold, glyph)', () => {
    for (const ms of [0, -1, -10 * M])
      expect(formatSla(ms)).toMatchObject({
        label: 'Expiring',
        weight: 'bold',
        glyph: SLA_GLYPH,
        pulse: false,
        muted: false,
        state: 'expiring',
      });
  });

  it('server-expired is "Expired" (bold, muted, no glyph), whatever the local countdown says', () => {
    for (const ms of [12 * M, 0, -M])
      expect(formatSla(ms, { serverExpired: true })).toEqual({
        label: 'Expired',
        weight: 'bold',
        glyph: null,
        pulse: false,
        muted: true,
        state: 'expired',
        accessibleLabel: 'Offer expired',
      });
  });

  it('shows hours past an hour, and reads well to a screen reader (T-A11Y-2 support)', () => {
    expect(formatSla(90 * M).label).toBe('1h 30m left');
    expect(formatSla(120 * M).label).toBe('2h left');
    expect(formatSla(60 * M).label).toBe('60m left');
    expect(formatSla(12 * M).accessibleLabel).toBe('Time to accept: 12 minutes left');
    expect(formatSla(60 * S).accessibleLabel).toBe('Time to accept: 1 minute left');
    expect(formatSla(45 * S).accessibleLabel).toBe('Time to accept: 45 seconds left');
    expect(formatSla(1 * S).accessibleLabel).toBe('Time to accept: 1 second left');
    expect(formatSla(90 * M).accessibleLabel).toBe('Time to accept: 1 hour 30 minutes left');
    expect(formatSla(120 * M).accessibleLabel).toBe('Time to accept: 2 hours left');
    expect(formatSla(0).accessibleLabel).toBe('Offer expiring');
  });

  it('never returns a color (urgency is weight + label only)', () => {
    const samples = [12 * M, 4 * M, 45 * S, 0, -1].map((ms) => formatSla(ms));
    samples.push(formatSla(0, { serverExpired: true }));
    for (const r of samples) {
      for (const [k, v] of Object.entries(r)) {
        expect(k).not.toMatch(/colou?r|tone|status|variant|hex/i);
        expect(String(v)).not.toMatch(
          /#[0-9a-f]{3,8}\b|rgb|hsl|var\(|\b(red|amber|green|orange)\b/i,
        );
      }
    }
  });

  it('treats NaN as expiring rather than inventing time', () => {
    expect(formatSla(Number.NaN).label).toBe('Expiring');
  });
});

describe('T-SLA-2 server clock offset (unit)', () => {
  const SERVER = Date.parse('2026-11-02T15:00:00Z');

  it.each([
    ['device 5 min fast', +5 * M],
    ['device 5 min slow', -5 * M],
    ['device in sync', 0],
  ])('%s: the countdown still matches server time', (_name, skew) => {
    const device = createFakeClock(SERVER + skew);
    const server = createServerClock(device);
    server.observe('2026-11-02T15:00:00Z');
    expect(server.offsetMs()).toBe(-skew || 0);
    expect(server.now()).toBe(SERVER);
    // An offer with 4 minutes left on the server shows 4 minutes, not 4 ± 5.
    const deadline = new Date(SERVER + 4 * M).toISOString();
    expect(slaRemainingMs(deadline, server)).toBe(4 * M);
    expect(formatSla(slaRemainingMs(deadline, server)!).label).toBe('4m left');
  });

  it('ticks with the device clock after an observation', async () => {
    const device = createFakeClock(SERVER + 5 * M);
    const server = createServerClock(device);
    server.observe(new Date(SERVER).toISOString());
    await device.advance(30 * S);
    expect(server.now()).toBe(SERVER + 30 * S);
    // Timers delegate to the device clock, so the server clock is a drop-in ClockPort.
    let fired = false;
    const h = server.setTimeout(() => (fired = true), 10);
    server.clearTimeout(h);
    server.setTimeout(() => (fired = true), 10);
    await device.advance(10);
    expect(fired).toBe(true);
  });

  it('uses the request midpoint when the send time is known (cancels latency)', () => {
    const device = createFakeClock(SERVER + 5 * M + 400); // response received 400 ms after send
    const server = createServerClock(device);
    server.observe(new Date(SERVER + 200).toISOString(), { sentAt: SERVER + 5 * M });
    expect(server.offsetMs()).toBe(-5 * M);
  });

  it('keeps the latest valid observation and ignores garbage', () => {
    const device = createFakeClock(SERVER);
    const server = createServerClock(device);
    expect(server.offsetMs()).toBe(0);
    expect(server.hasObservation()).toBe(false);
    expect(server.observe('not a date')).toBe(false);
    expect(server.observe(undefined)).toBe(false);
    expect(server.observe(null)).toBe(false);
    expect(server.observe(new Date(SERVER + M).toISOString())).toBe(true);
    expect(server.observe('')).toBe(false);
    expect(server.offsetMs()).toBe(M);
    expect(server.hasObservation()).toBe(true);
  });

  it('observes any response body carrying server_time', () => {
    const device = createFakeClock(SERVER);
    const server = createServerClock(device);
    expect(
      server.observeBody({ server_time: new Date(SERVER - M).toISOString(), offers: [] }),
    ).toBe(true);
    expect(server.offsetMs()).toBe(-M);
    expect(server.observeBody({ offers: [] })).toBe(false);
    expect(server.observeBody(null)).toBe(false);
    expect(server.observeBody('x')).toBe(false);
  });

  it('a missing or invalid deadline has no countdown', () => {
    const server = createServerClock(createFakeClock(SERVER));
    expect(slaRemainingMs(undefined, server)).toBeNull();
    expect(slaRemainingMs(null, server)).toBeNull();
    expect(slaRemainingMs('soon', server)).toBeNull();
  });
});
