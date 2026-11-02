import { describe, expect, it, vi } from 'vitest';
import {
  createInboxSync,
  createServerClock,
  INBOX_REFRESH_MS,
  OFFER_UNAVAILABLE_TOAST,
  type AcceptOutcome,
  type InboxEvent,
  type ScheduleResponse,
} from '../src/index';
import {
  createFakeClock,
  createFakeConnectivity,
  createFakeVisibility,
  flushMicrotasks,
} from '../src/testing';

interface Offer {
  wo_id: string;
  sla_deadline?: string | null;
  last_advanced_at?: string | null;
}

const T0 = Date.parse('2026-11-02T15:00:00Z');
const iso = (ms: number) => new Date(ms).toISOString();
const offer = (id: string, minutes: number): Offer => ({
  wo_id: id,
  sla_deadline: iso(T0 + minutes * 60_000),
});
const schedule = (
  offers: Offer[],
  active: Offer[] = [],
  serverMs = T0,
): ScheduleResponse<Offer> => ({
  offers,
  active,
  voice_bookings: [],
  server_time: iso(serverMs),
});

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function setup(opts: { visible?: boolean; online?: boolean } = {}) {
  const clock = createFakeClock(T0);
  const visibility = createFakeVisibility(opts.visible ?? true);
  const connectivity = createFakeConnectivity(opts.online ?? true);
  const responses: (ScheduleResponse<Offer> | Error)[] = [];
  let last: ScheduleResponse<Offer> = schedule([]);
  const fetchSchedule = vi.fn(async () => {
    const next = responses.shift();
    if (next instanceof Error) throw next;
    if (next) last = next;
    return last;
  });
  const accept = vi.fn(async (_wo: string): Promise<AcceptOutcome<{ wo_id: string }>> => ({
    ok: true,
    detail: { wo_id: _wo },
  }));
  const serverClock = createServerClock(clock);
  const sync = createInboxSync<Offer, { wo_id: string }>({
    fetchSchedule,
    accept,
    clock,
    serverClock,
    visibility: visibility.port,
    connectivity: connectivity.port,
  });
  const events: InboxEvent<{ wo_id: string }>[] = [];
  sync.onEvent((e) => events.push(e));
  return {
    clock,
    visibility,
    connectivity,
    responses,
    fetchSchedule,
    accept,
    sync,
    events,
    serverClock,
  };
}

const ids = (list: readonly Offer[]) => list.map((o) => o.wo_id);

describe('createInboxSync — loading and ordering', () => {
  it('starts in loading, then ready with sorted offers and active (T-INBOX-1 wiring)', async () => {
    const t = setup();
    t.responses.push(
      schedule(
        [offer('wo-12m', 12), offer('wo-45s', 0.75), offer('wo-4m', 4)],
        [
          { wo_id: 'old', last_advanced_at: iso(T0 - 60_000) },
          { wo_id: 'new', last_advanced_at: iso(T0) },
        ],
      ),
    );
    expect(t.sync.getState().status).toBe('loading');
    const states: string[] = [];
    t.sync.subscribe((s) => states.push(s.status));
    t.sync.start();
    await flushMicrotasks();
    const s = t.sync.getState();
    expect(s.status).toBe('ready');
    expect(ids(s.offers)).toEqual(['wo-45s', 'wo-4m', 'wo-12m']);
    expect(ids(s.active)).toEqual(['new', 'old']);
    expect(s.voiceBookings).toEqual([]);
    expect(s.lastUpdatedAt).toBe(T0);
    expect(s.error).toBeNull();
    expect(states).toContain('ready');
  });

  it('feeds server_time into the server clock (FR-2.4)', async () => {
    const t = setup();
    t.responses.push(schedule([], [], T0 + 5 * 60_000));
    t.sync.start();
    await flushMicrotasks();
    expect(t.serverClock.offsetMs()).toBe(5 * 60_000);
  });

  it('start is idempotent and stop unsubscribes everything', async () => {
    const t = setup();
    t.sync.start();
    t.sync.start();
    await flushMicrotasks();
    expect(t.fetchSchedule).toHaveBeenCalledTimes(1);
    t.sync.stop();
    expect(t.clock.pending()).toBe(0);
    t.visibility.set(false);
    t.visibility.set(true);
    t.connectivity.set(false);
    t.connectivity.set(true);
    await t.clock.advance(60_000);
    expect(t.fetchSchedule).toHaveBeenCalledTimes(1);
  });
});

describe('T-INBOX-3 auto-refresh at 20 s and on focus (core slice)', () => {
  it('refetches every 20 s while visible and picks up a new offer', async () => {
    const t = setup();
    t.responses.push(schedule([offer('a', 10)]));
    t.sync.start();
    await flushMicrotasks();
    expect(INBOX_REFRESH_MS).toBe(20_000);
    t.responses.push(schedule([offer('a', 10), offer('b', 3)]));
    await t.clock.advance(19_999);
    expect(t.fetchSchedule).toHaveBeenCalledTimes(1);
    await t.clock.advance(1);
    expect(t.fetchSchedule).toHaveBeenCalledTimes(2);
    expect(ids(t.sync.getState().offers)).toEqual(['b', 'a']);
    await t.clock.advance(20_000);
    expect(t.fetchSchedule).toHaveBeenCalledTimes(3);
  });

  it('pauses while hidden and refetches immediately when visible again', async () => {
    const t = setup();
    t.sync.start();
    await flushMicrotasks();
    t.visibility.set(false);
    await t.clock.advance(120_000);
    expect(t.fetchSchedule).toHaveBeenCalledTimes(1);
    expect(t.clock.pending()).toBe(0);
    t.responses.push(schedule([offer('new', 5)]));
    t.visibility.set(true);
    await flushMicrotasks();
    expect(t.fetchSchedule).toHaveBeenCalledTimes(2);
    expect(ids(t.sync.getState().offers)).toEqual(['new']);
    // The 20 s cadence restarts from the focus refresh.
    await t.clock.advance(20_000);
    expect(t.fetchSchedule).toHaveBeenCalledTimes(3);
  });

  it('does not fetch on start while hidden; fetches on first visibility', async () => {
    const t = setup({ visible: false });
    t.sync.start();
    await flushMicrotasks();
    expect(t.fetchSchedule).not.toHaveBeenCalled();
    expect(t.sync.getState().status).toBe('loading');
    t.visibility.set(true);
    await flushMicrotasks();
    expect(t.fetchSchedule).toHaveBeenCalledTimes(1);
  });

  it('is single-flight: overlapping refreshes share one request', async () => {
    const t = setup();
    const d = deferred<ScheduleResponse<Offer>>();
    t.fetchSchedule.mockImplementationOnce(() => d.promise);
    t.sync.start();
    const p1 = t.sync.refresh();
    const p2 = t.sync.refresh();
    expect(t.fetchSchedule).toHaveBeenCalledTimes(1);
    d.resolve(schedule([offer('x', 1)]));
    await Promise.all([p1, p2]);
    expect(ids(t.sync.getState().offers)).toEqual(['x']);
    expect(t.sync.getState().refreshing).toBe(false);
  });
});

describe('T-INBOX-4 refresh failure keeps the last list + error + Retry (core slice)', () => {
  it('keeps the last good list and exposes an error; Retry recovers', async () => {
    const t = setup();
    t.responses.push(schedule([offer('a', 10)]));
    t.sync.start();
    await flushMicrotasks();
    t.responses.push(new Error('503'));
    await t.clock.advance(20_000);
    let s = t.sync.getState();
    expect(s.status).toBe('error');
    expect(ids(s.offers)).toEqual(['a']);
    expect(s.error).toBeInstanceOf(Error);
    expect(s.lastUpdatedAt).toBe(T0);
    t.responses.push(schedule([offer('a', 10), offer('b', 2)]));
    await t.sync.retry();
    s = t.sync.getState();
    expect(s.status).toBe('ready');
    expect(s.error).toBeNull();
    expect(ids(s.offers)).toEqual(['b', 'a']);
  });

  it('first-load failure is an error with no list, and polling keeps trying (self-heal)', async () => {
    const t = setup();
    t.responses.push(new Error('boom'));
    t.sync.start();
    await flushMicrotasks();
    expect(t.sync.getState()).toMatchObject({ status: 'error', offers: [], lastUpdatedAt: null });
    t.responses.push(schedule([offer('a', 3)]));
    await t.clock.advance(20_000);
    expect(t.sync.getState().status).toBe('ready');
  });
});

describe('offline state (FR-2.7, T-INBOX-8 core slice)', () => {
  it('goes offline keeping the last list, stops polling, and refetches on reconnect', async () => {
    const t = setup();
    t.responses.push(schedule([offer('a', 10)]));
    t.sync.start();
    await flushMicrotasks();
    t.connectivity.set(false);
    expect(t.sync.getState()).toMatchObject({ status: 'offline' });
    expect(ids(t.sync.getState().offers)).toEqual(['a']);
    await t.clock.advance(60_000);
    expect(t.fetchSchedule).toHaveBeenCalledTimes(1);
    await t.sync.refresh(); // a manual refresh while offline does nothing
    expect(t.fetchSchedule).toHaveBeenCalledTimes(1);
    t.responses.push(schedule([offer('b', 1)]));
    t.connectivity.set(true);
    await flushMicrotasks();
    expect(t.fetchSchedule).toHaveBeenCalledTimes(2);
    expect(t.sync.getState().status).toBe('ready');
  });

  it('starts offline without fetching', async () => {
    const t = setup({ online: false });
    t.sync.start();
    await flushMicrotasks();
    expect(t.sync.getState().status).toBe('offline');
    expect(t.fetchSchedule).not.toHaveBeenCalled();
  });

  it('a refresh that fails after going offline reports offline, not error', async () => {
    const t = setup();
    t.sync.start();
    await flushMicrotasks();
    const d = deferred<ScheduleResponse<Offer>>();
    t.fetchSchedule.mockImplementationOnce(() => d.promise);
    const p = t.sync.refresh();
    t.connectivity.set(false);
    d.reject(new TypeError('Failed to fetch'));
    await p;
    expect(t.sync.getState().status).toBe('offline');
  });

  it('accept while offline is refused locally (cards are read-only)', async () => {
    const t = setup({ online: false });
    t.sync.start();
    expect(await t.sync.accept('a')).toEqual({ kind: 'offline' });
    expect(t.accept).not.toHaveBeenCalled();
  });
});

describe('T-INBOX-5 stale-offer race: 409 → toast → card leaves on refresh (core slice)', () => {
  it('turns 409 OFFER_UNAVAILABLE into a toast event and schedules a refresh', async () => {
    const t = setup();
    t.responses.push(schedule([offer('ana-reassigned', 4), offer('b', 8)]));
    t.sync.start();
    await flushMicrotasks();
    t.accept.mockResolvedValueOnce({
      ok: false,
      status: 409,
      code: 'OFFER_UNAVAILABLE',
      reason: 'reassigned',
    });
    t.responses.push(schedule([offer('b', 8)]));
    const result = await t.sync.accept('ana-reassigned');
    expect(result).toEqual({ kind: 'unavailable', reason: 'reassigned' });
    expect(t.events).toContainEqual({
      type: 'toast',
      message: OFFER_UNAVAILABLE_TOAST,
      woId: 'ana-reassigned',
      reason: 'reassigned',
    });
    expect(OFFER_UNAVAILABLE_TOAST).toBe("This offer just expired — it's been reassigned");
    // The card leaves with the immediate refresh (server is authoritative, no local guess).
    await flushMicrotasks();
    expect(t.fetchSchedule).toHaveBeenCalledTimes(2);
    expect(ids(t.sync.getState().offers)).toEqual(['b']);
  });

  it('a poll in flight during the 409 cannot keep the stale card', async () => {
    const t = setup();
    t.responses.push(schedule([offer('gone', 4)]));
    t.sync.start();
    await flushMicrotasks();
    const stale = deferred<ScheduleResponse<Offer>>();
    t.fetchSchedule.mockImplementationOnce(() => stale.promise);
    const poll = t.sync.refresh();
    t.accept.mockResolvedValueOnce({ ok: false, status: 409, code: 'OFFER_UNAVAILABLE' });
    expect(await t.sync.accept('gone')).toEqual({ kind: 'unavailable', reason: undefined });
    t.responses.push(schedule([]));
    stale.resolve(schedule([offer('gone', 4)]));
    await poll;
    expect(t.fetchSchedule).toHaveBeenCalledTimes(3);
    expect(t.sync.getState().offers).toEqual([]);
  });

  it('success removes the offer at once, emits accepted with the detail, then refreshes', async () => {
    const t = setup();
    t.responses.push(schedule([offer('a', 4), offer('b', 8)]));
    t.sync.start();
    await flushMicrotasks();
    // A poll that started before the accept must not bring the accepted card back.
    const stale = deferred<ScheduleResponse<Offer>>();
    t.fetchSchedule.mockImplementationOnce(() => stale.promise);
    const poll = t.sync.refresh();
    const result = await t.sync.accept('a');
    expect(result).toEqual({ kind: 'accepted', detail: { wo_id: 'a' } });
    expect(ids(t.sync.getState().offers)).toEqual(['b']);
    expect(t.events).toContainEqual({ type: 'accepted', woId: 'a', detail: { wo_id: 'a' } });
    t.responses.push(schedule([offer('b', 8)], [{ wo_id: 'a', last_advanced_at: iso(T0) }]));
    stale.resolve(schedule([offer('a', 4), offer('b', 8)]));
    await poll;
    await flushMicrotasks();
    expect(ids(t.sync.getState().offers)).toEqual(['b']);
    expect(ids(t.sync.getState().active)).toEqual(['a']);
  });

  it('other failures are reported without a toast about expiry', async () => {
    const t = setup();
    t.sync.start();
    await flushMicrotasks();
    t.accept.mockResolvedValueOnce({ ok: false, status: 500 });
    expect(await t.sync.accept('a')).toEqual({ kind: 'failed', status: 500 });
    t.accept.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    expect(await t.sync.accept('a')).toEqual({ kind: 'failed', status: null });
    t.accept.mockResolvedValueOnce({ ok: false, status: 409, code: 'INVALID_TRANSITION' });
    expect(await t.sync.accept('a')).toEqual({ kind: 'failed', status: 409 });
    expect(t.events.filter((e) => e.type === 'toast')).toEqual([]);
  });
});

describe('listeners', () => {
  it('unsubscribe stops state and event delivery', async () => {
    const t = setup();
    const states = vi.fn();
    const events = vi.fn();
    const offS = t.sync.subscribe(states);
    const offE = t.sync.onEvent(events);
    offS();
    offE();
    t.sync.start();
    await flushMicrotasks();
    await t.sync.accept('a');
    expect(states).not.toHaveBeenCalled();
    expect(events).not.toHaveBeenCalled();
  });
});
