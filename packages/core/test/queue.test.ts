import { describe, expect, it, vi } from 'vitest';
import { isValidIdempotencyKey } from '@insmartfix/contracts';
import { createDraftStore, createOfflineQueue, emptyCompletionDraft, queueKey } from '../src';
import type { CompletionReport, QueueEvent, QueueTransport, StoragePort } from '../src';
import {
  createFakeClock,
  createFakeConnectivity,
  createFakeVisibility,
  createMemoryStorage,
  flushMicrotasks,
} from '../src/testing';

const USER = 'u-marco';
const WO = 'wo-rtu-04';
const REPORT: Omit<CompletionReport, 'photo_ids'> = {
  failure_code: 'RTU-CONT',
  actual_fault_matched: true,
  parts_used: [{ description: 'Contactor 40A', qty: 1 }],
  labor_hours: 1.5,
  technician_id: 'Marco Rossi',
};

type Fault = null | 'network' | 'lost-response' | { status: number; code?: string };

/**
 * In-memory API with the server's idempotency rules (D10 H-3, D12): a record per
 * (scope, key) with the body hash; same key + same body → original result; same key + different
 * body → 422 IDEMPOTENCY_KEY_REUSED; a new key on a completed WO → 409 ALREADY_COMPLETED.
 */
function fakeServer() {
  const records = new Map<string, { body: string; result: unknown }>();
  const completed = new Map<string, CompletionReport>();
  const calls: { kind: string; key: string; body?: string }[] = [];
  const faults: Fault[] = [];
  let photoSeq = 0;
  let calibrations = 0;
  let gate: Promise<void> | null = null;

  const idempotent = <T>(scope: string, key: string, body: string, exec: () => T): T => {
    const hit = records.get(`${scope}|${key}`);
    if (hit) {
      if (hit.body !== body)
        throw { status: 422, code: 'IDEMPOTENCY_KEY_REUSED', message: 'reused' };
      return hit.result as T;
    }
    const result = exec();
    records.set(`${scope}|${key}`, { body, result });
    return result;
  };

  const handle = async <T>(kind: string, key: string, body: string, exec: () => T): Promise<T> => {
    calls.push({ kind, key, body });
    if (gate) await gate;
    const fault = faults.shift() ?? null;
    if (fault === 'network') throw new TypeError('Network request failed');
    if (fault && fault !== 'lost-response') throw { ...fault, message: `HTTP ${fault.status}` };
    const result = exec();
    if (fault === 'lost-response') throw new TypeError('connection reset after commit');
    return result;
  };

  const transport: QueueTransport = {
    uploadPhoto: ({ woId, localId, idempotencyKey }) =>
      handle('photo', idempotencyKey, localId, () =>
        idempotent(`photos|${woId}`, idempotencyKey, localId, () => ({
          photo_id: `ph-${++photoSeq}`,
        })),
      ),
    complete: ({ woId, body, idempotencyKey }) => {
      const json = JSON.stringify(body);
      return handle('complete', idempotencyKey, json, () =>
        idempotent(`complete|${woId}`, idempotencyKey, json, () => {
          if (completed.has(woId)) {
            throw { status: 409, code: 'ALREADY_COMPLETED', message: 'already completed' };
          }
          completed.set(woId, body);
          calibrations += 1;
          return { calibration_label: 'MATCH', record_updated: true as const };
        }),
      );
    },
  };
  return {
    transport,
    calls,
    faults,
    completed,
    calibrations: () => calibrations,
    hold() {
      let release!: () => void;
      gate = new Promise((r) => (release = r));
      return () => {
        gate = null;
        release();
      };
    },
  };
}

function setup(opts: { online?: boolean; storage?: ReturnType<typeof createMemoryStorage> } = {}) {
  const storage = opts.storage ?? createMemoryStorage();
  const clock = createFakeClock(10_000);
  const net = createFakeConnectivity(opts.online ?? true);
  const vis = createFakeVisibility(true);
  const server = fakeServer();
  const drafts = createDraftStore(storage, { clock });
  let n = 0;
  const make = (transport: QueueTransport = server.transport) =>
    createOfflineQueue({
      userId: USER,
      storage,
      transport,
      clock,
      connectivity: net.port,
      visibility: vis.port,
      drafts,
      generateKey: () => `key-${String(++n).padStart(4, '0')}`,
      random: () => 0.5,
      backoff: { baseMs: 1000, maxMs: 8000 },
    });
  const queue = make();
  const events: QueueEvent[] = [];
  queue.subscribe((e) => events.push(e));
  const stop = queue.start();
  const ofType = <T extends QueueEvent['type']>(t: T) =>
    events.filter((e): e is Extract<QueueEvent, { type: T }> => e.type === t);
  return { storage, clock, net, vis, server, drafts, queue, events, ofType, stop, make };
}

describe('offline queue (FR-7.3, FR-7.7, NFR-5)', () => {
  it('T-COMP-5 submit offline → queued → reconnect → auto-flush once → calibration once', async () => {
    const t = setup({ online: false });
    t.drafts.save(USER, WO, emptyCompletionDraft('Marco Rossi'));
    await t.drafts.flush();
    await t.queue.enqueueCompletion(WO, REPORT, []);
    await t.clock.advance(60_000);
    expect(t.server.calls).toHaveLength(0);
    expect((await t.queue.list()).map((i) => i.kind)).toEqual(['complete']); // drives the banner
    expect(await t.drafts.load(USER, WO)).not.toBeNull();

    // Flaky reconnect: several online/foreground signals in a burst.
    t.net.set(true);
    t.net.set(false);
    t.net.set(true);
    t.vis.set(false);
    t.vis.set(true);
    await t.queue.flush();
    await t.clock.advance(60_000);

    expect(t.server.calls.filter((c) => c.kind === 'complete')).toHaveLength(1);
    expect(t.server.calibrations()).toBe(1);
    expect(t.ofType('completed')).toEqual([
      { type: 'completed', woId: WO, result: { calibration_label: 'MATCH', record_updated: true } },
    ]);
    expect(await t.queue.list()).toEqual([]);
    expect(await t.drafts.load(USER, WO)).toBeNull(); // cleared only after confirmed success
  });

  it('T-COMP-5 a flush never runs twice concurrently (single-flight)', async () => {
    const t = setup({ online: false });
    await t.queue.enqueueCompletion(WO, REPORT, []);
    const release = t.server.hold();
    t.net.set(true);
    const a = t.queue.flush();
    const b = t.queue.flush();
    await flushMicrotasks();
    expect(t.server.calls).toHaveLength(1);
    release();
    await Promise.all([a, b]);
    expect(t.server.calls).toHaveLength(1);
    expect(t.server.calibrations()).toBe(1);
  });

  it('T-COMP-5 work enqueued during a flush is picked up by the same flush', async () => {
    const t = setup();
    const release = t.server.hold();
    const first = t.queue.enqueueCompletion('wo-1', REPORT, []);
    await flushMicrotasks();
    await first;
    await t.queue.enqueueCompletion('wo-2', REPORT, []);
    release();
    await t.queue.flush();
    expect([...t.server.completed.keys()]).toEqual(['wo-1', 'wo-2']);
  });

  it('T-PHOTO-2 photo queued offline is uploaded before the completion, which carries its id', async () => {
    const t = setup({ online: false });
    await t.queue.enqueuePhoto(WO, 'file-a');
    await t.queue.enqueueCompletion(WO, REPORT, [
      { local_id: 'file-a' },
      { local_id: 'file-b' },
      { local_id: 'file-c', photo_id: 'ph-earlier' },
    ]);
    expect((await t.queue.list()).map((i) => i.kind)).toEqual([
      'photo_upload',
      'photo_upload',
      'complete',
    ]);
    t.net.set(true);
    await t.queue.flush();
    expect(t.server.calls.map((c) => c.kind)).toEqual(['photo', 'photo', 'complete']);
    expect(t.server.completed.get(WO)?.photo_ids).toEqual(['ph-1', 'ph-2', 'ph-earlier']);
    expect(t.ofType('photo_uploaded').map((e) => [e.localId, e.photoId])).toEqual([
      ['file-a', 'ph-1'],
      ['file-b', 'ph-2'],
    ]);
  });

  it('T-PHOTO-2 the completion waits while a photo upload is failing', async () => {
    const t = setup();
    t.server.faults.push({ status: 503 });
    await t.queue.enqueueCompletion(WO, REPORT, [{ local_id: 'file-a' }]);
    await t.queue.flush();
    expect(t.server.calls.map((c) => c.kind)).toEqual(['photo']);
    await t.clock.advance(1000); // backoff 1000 × (0.5 + 0.25)
    expect(t.server.calls.map((c) => c.kind)).toEqual(['photo', 'photo', 'complete']);
    expect(t.server.completed.get(WO)?.photo_ids).toEqual(['ph-1']);
  });

  it('D12 retries after a lost response reuse the key and the exact body; never 422', async () => {
    const t = setup();
    // photo: lost, ok · complete: lost, 502, network, ok
    t.server.faults.push('lost-response', null, 'lost-response', { status: 502 }, 'network');
    await t.queue.enqueueCompletion(WO, REPORT, [{ local_id: 'file-a' }]);
    await t.queue.flush();
    for (let i = 0; i < 5; i += 1) await t.clock.advance(8000);
    const photos = t.server.calls.filter((c) => c.kind === 'photo');
    expect(photos).toHaveLength(2);
    expect(photos[1]).toEqual(photos[0]);
    const sends = t.server.calls.filter((c) => c.kind === 'complete');
    expect(sends).toHaveLength(4);
    expect(t.server.completed.get(WO)?.photo_ids).toEqual(['ph-1']); // one photo, not two
    expect(new Set(sends.map((c) => c.key)).size).toBe(1);
    expect(new Set(sends.map((c) => c.body)).size).toBe(1);
    expect(t.ofType('dead')).toEqual([]);
    expect(t.server.calibrations()).toBe(1);
    expect(t.ofType('completed')).toHaveLength(1);
  });

  it('D12 a relaunch after a kill mid-send resends the same key and body', async () => {
    const storage = createMemoryStorage();
    const t = setup({ storage });
    t.server.faults.push('lost-response');
    await t.queue.enqueueCompletion(WO, REPORT, []);
    await t.queue.flush();
    t.stop(); // the app is killed; only storage survives
    const before = JSON.parse(storage.data.get(queueKey(USER))!).items[0];
    expect(before.body).toBeDefined();

    const relaunched = t.make();
    relaunched.start();
    await relaunched.flush();
    await t.clock.advance(1000); // the persisted backoff still applies
    const sends = t.server.calls.filter((c) => c.kind === 'complete');
    expect(sends).toHaveLength(2);
    expect(sends[1]).toEqual(sends[0]);
    expect(t.server.calibrations()).toBe(1);
    expect(await relaunched.list()).toEqual([]);
  });

  it('backs off exponentially with jitter up to the cap, and retries 408 / 429 / 5xx', async () => {
    const t = setup();
    t.server.faults.push({ status: 500 }, { status: 408 }, { status: 429 }, 'network', 'network');
    await t.queue.enqueueCompletion(WO, REPORT, []);
    await t.queue.flush();
    const at = async () => (await t.queue.list())[0]!.nextAttemptAt - t.clock.now();
    expect(await at()).toBe(750); // 1000 × 0.75
    await t.clock.advance(750);
    expect(await at()).toBe(1500);
    await t.clock.advance(1500);
    expect(await at()).toBe(3000);
    await t.clock.advance(3000);
    expect(await at()).toBe(6000);
    await t.clock.advance(6000);
    expect(await at()).toBe(6000); // capped at 8000 × 0.75
    expect((await t.queue.list())[0]?.attempts).toBe(5);
    await t.clock.advance(6000);
    expect(t.server.calibrations()).toBe(1);
  });

  it('a 4xx dead-letters the item, keeps the draft, and retry resends the same key and body', async () => {
    const t = setup();
    t.drafts.save(USER, WO, emptyCompletionDraft());
    t.server.faults.push({ status: 422, code: 'VALIDATION_ERROR' });
    const item = await t.queue.enqueueCompletion(WO, REPORT, []);
    await t.queue.flush();
    const dead = t.ofType('dead');
    expect(dead).toHaveLength(1);
    expect(dead[0]?.item).toMatchObject({
      status: 'dead',
      lastError: { status: 422, code: 'VALIDATION_ERROR' },
    });
    await t.clock.advance(600_000);
    expect(t.server.calls).toHaveLength(1);
    expect(await t.drafts.load(USER, WO)).not.toBeNull();

    await t.queue.retry(item.id);
    const sends = t.server.calls;
    expect(sends).toHaveLength(2);
    expect(sends[1]).toEqual(sends[0]);
    expect(await t.drafts.load(USER, WO)).toBeNull();
    await t.queue.retry('missing');
  });

  it('a dead photo blocks its completion until discarded; the completion then omits it', async () => {
    const t = setup();
    t.server.faults.push({ status: 415, code: 'UNSUPPORTED_MEDIA_TYPE' });
    await t.queue.enqueueCompletion(WO, REPORT, [{ local_id: 'bad' }, { local_id: 'good' }]);
    await t.queue.flush();
    const items = await t.queue.list();
    expect(items.map((i) => [i.kind, i.status])).toEqual([
      ['photo_upload', 'dead'],
      ['complete', 'pending'],
    ]);
    expect(t.server.calls.map((c) => c.kind)).toEqual(['photo', 'photo']);
    await t.queue.discard(items[0]!.id);
    await t.queue.flush();
    expect(t.server.completed.get(WO)?.photo_ids).toEqual(['ph-1']);
    await t.queue.discard('missing');
  });

  it('409 ALREADY_COMPLETED from a different key is dead-lettered, not retried', async () => {
    const t = setup();
    t.server.completed.set(WO, { ...REPORT, photo_ids: [] });
    await t.queue.enqueueCompletion(WO, REPORT, []);
    await t.queue.flush();
    expect(t.ofType('dead')[0]?.item.lastError?.code).toBe('ALREADY_COMPLETED');
  });

  it('401 pauses the queue without spending attempts until the next external trigger', async () => {
    const t = setup();
    t.server.faults.push({ status: 401 });
    await t.queue.enqueueCompletion(WO, REPORT, []);
    await t.queue.flush();
    expect(t.ofType('auth_required')).toHaveLength(1);
    await t.clock.advance(600_000);
    expect(t.server.calls).toHaveLength(1);
    expect((await t.queue.list())[0]).toMatchObject({ attempts: 0, status: 'pending' });
    t.vis.set(false);
    t.vis.set(true); // e.g. back from the login screen
    await t.queue.flush();
    expect(t.server.calibrations()).toBe(1);
  });

  it('re-queuing an unsent completion updates it in place; a sent one gets a new key', async () => {
    const t = setup({ online: false });
    const a = await t.queue.enqueueCompletion(WO, REPORT, []);
    const b = await t.queue.enqueueCompletion(WO, { ...REPORT, labor_hours: 2 }, []);
    expect(b.id).toBe(a.id);
    expect(b.idempotencyKey).toBe(a.idempotencyKey);
    expect(await t.queue.list()).toHaveLength(1);

    t.net.set(true);
    t.server.faults.push({ status: 503 });
    await t.queue.flush();
    const c = await t.queue.enqueueCompletion(WO, { ...REPORT, labor_hours: 3 }, []);
    expect(c.idempotencyKey).not.toBe(a.idempotencyKey);
    await t.clock.advance(10_000);
    expect(t.server.completed.get(WO)?.labor_hours).toBe(3);
    expect(t.ofType('dead')).toEqual([]);
  });

  it('enqueuePhoto is deduplicated and skips photos already uploaded', async () => {
    const t = setup({ online: false });
    const p1 = await t.queue.enqueuePhoto(WO, 'file-a');
    const p2 = await t.queue.enqueuePhoto(WO, 'file-a');
    expect(p2?.id).toBe(p1?.id);
    t.net.set(true);
    await t.queue.flush();
    expect(await t.queue.enqueuePhoto(WO, 'file-a')).toBeNull();
    await t.queue.enqueueCompletion(WO, REPORT, [{ local_id: 'file-a' }]);
    await t.queue.flush();
    expect(t.server.calls.map((c) => c.kind)).toEqual(['photo', 'complete']);
    expect(t.server.completed.get(WO)?.photo_ids).toEqual(['ph-1']);
  });

  it('survives a relaunch with queued photos and completion (app kill while offline)', async () => {
    const storage = createMemoryStorage();
    const t = setup({ storage, online: false });
    await t.queue.enqueueCompletion(WO, REPORT, [{ local_id: 'file-a' }]);
    t.stop();
    const relaunched = t.make();
    relaunched.start();
    t.net.set(true);
    await relaunched.flush();
    expect(t.server.completed.get(WO)?.photo_ids).toEqual(['ph-1']);
  });

  it('discarding or signing out while a send is in flight leaves nothing behind', async () => {
    const t = setup();
    const release = t.server.hold();
    const photo = await t.queue.enqueuePhoto(WO, 'file-a');
    await flushMicrotasks();
    await t.queue.discard(photo!.id);
    release();
    await t.queue.flush();
    expect(await t.queue.list()).toEqual([]);

    t.server.faults.push({ status: 500 });
    const hold2 = t.server.hold();
    await t.queue.enqueueCompletion('wo-2', REPORT, []);
    await flushMicrotasks();
    await t.queue.clearAll();
    hold2();
    await t.queue.flush();
    expect(await t.queue.list()).toEqual([]);
    expect(t.storage.data.has(queueKey(USER))).toBe(false);
  });

  it('clearAll forgets everything for the user (sign-out)', async () => {
    const t = setup({ online: false });
    await t.queue.enqueueCompletion(WO, REPORT, [{ local_id: 'file-a' }]);
    await t.queue.clearAll();
    expect(await t.queue.list()).toEqual([]);
    expect(t.ofType('changed').at(-1)).toEqual({ type: 'changed', items: [] });
    t.net.set(true);
    await t.queue.flush();
    expect(t.server.calls).toEqual([]);
  });

  it('stop() unsubscribes from connectivity and cancels the retry timer', async () => {
    const t = setup();
    t.server.faults.push('network');
    await t.queue.enqueueCompletion(WO, REPORT, []);
    await t.queue.flush();
    expect(t.clock.pending()).toBe(1);
    t.stop();
    expect(t.clock.pending()).toBe(0);
    t.net.set(false);
    t.net.set(true);
    await t.clock.advance(60_000);
    expect(t.server.calls).toHaveLength(1);
  });
});

describe('offline queue storage', () => {
  const opts = (storage: StoragePort, transport: QueueTransport = fakeServer().transport) => ({
    userId: USER,
    storage,
    transport,
    connectivity: createFakeConnectivity(true).port,
    clock: createFakeClock(),
  });

  it('keeps an unreadable queue aside and starts empty', async () => {
    const storage = createMemoryStorage();
    await storage.set(queueKey(USER), '{broken');
    const q = createOfflineQueue(opts(storage));
    expect(await q.list()).toEqual([]);
    expect(storage.data.get(`${queueKey(USER)}:corrupt:0`)).toBe('{broken');
    await storage.set(queueKey('other'), JSON.stringify({ v: 9 }));
    const q2 = createOfflineQueue({ ...opts(storage), userId: 'other' });
    expect(await q2.list()).toEqual([]);
    await q.clearAll();
    expect([...storage.data.keys()].sort()).toEqual([
      queueKey('other'),
      `${queueKey('other')}:corrupt:0`,
    ]);
  });

  it('loads a saved queue without an uploaded map', async () => {
    const storage = createMemoryStorage();
    await storage.set(queueKey(USER), JSON.stringify({ v: 1, items: [] }));
    expect(await createOfflineQueue(opts(storage)).list()).toEqual([]);
  });

  it('a storage read failure rejects calls instead of overwriting the saved queue', async () => {
    const storage = createMemoryStorage();
    const broken: StoragePort = { ...storage, get: () => Promise.reject(new Error('io')) };
    const q = createOfflineQueue(opts(broken));
    await expect(q.list()).rejects.toThrow('io');
    await expect(q.enqueuePhoto(WO, 'a')).rejects.toThrow('io');
    expect(storage.data.size).toBe(0);
  });

  it('storage write failures surface as error events from background flushes', async () => {
    const storage = createMemoryStorage();
    let fail = false;
    const flaky: StoragePort = {
      ...storage,
      set: (k, v) => (fail ? Promise.reject(new Error('quota')) : storage.set(k, v)),
    };
    const q = createOfflineQueue(opts(flaky));
    const errors: unknown[] = [];
    q.subscribe((e) => e.type === 'error' && errors.push(e.error));
    await q.enqueueCompletion(WO, REPORT, []);
    fail = true;
    q.start();
    await flushMicrotasks(50);
    expect(errors.map((e) => (e as Error).message)).toContain('quota');
  });

  it('a failing draft clear is reported but does not undo the completion', async () => {
    const storage = createMemoryStorage();
    const q = createOfflineQueue({
      ...opts(storage),
      drafts: { clear: () => Promise.reject(new Error('locked')) },
    });
    const events: QueueEvent[] = [];
    q.subscribe((e) => events.push(e));
    await q.enqueueCompletion(WO, REPORT, []);
    await q.flush();
    expect(events.map((e) => e.type)).toContain('completed');
    expect(events.some((e) => e.type === 'error')).toBe(true);
  });

  it('a throwing listener does not interrupt the flush', async () => {
    const storage = createMemoryStorage();
    const q = createOfflineQueue(opts(storage));
    q.subscribe(() => {
      throw new Error('ui bug');
    });
    await q.enqueueCompletion(WO, REPORT, []);
    await q.flush();
    expect(await q.list()).toEqual([]);
  });

  it('uses crypto.randomUUID and the system clock by default', async () => {
    const q = createOfflineQueue({
      userId: USER,
      storage: createMemoryStorage(),
      transport: fakeServer().transport,
      connectivity: createFakeConnectivity(false).port,
    });
    const item = await q.enqueueCompletion(WO, REPORT, []);
    expect(item.idempotencyKey).toMatch(/^[0-9a-f-]{36}$/);
    expect(isValidIdempotencyKey(item.idempotencyKey)).toBe(true);
    expect(Math.abs(item.createdAt - Date.now())).toBeLessThan(5000);
  });

  it('refuses to start without a secure key source', () => {
    vi.stubGlobal('crypto', undefined);
    try {
      expect(() => createOfflineQueue(opts(createMemoryStorage()))).toThrow(/generateKey/);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('maps non-object transport errors to network errors', async () => {
    const transport: QueueTransport = {
      uploadPhoto: () => Promise.reject('boom'),
      complete: () => Promise.reject('boom'),
    };
    const q = createOfflineQueue(opts(createMemoryStorage(), transport));
    await q.enqueueCompletion(WO, REPORT, []);
    await q.flush();
    expect((await q.list())[0]?.lastError).toEqual({ message: 'boom' });
  });
});
