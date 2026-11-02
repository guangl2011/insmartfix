import { describe, expect, it, vi } from 'vitest';
import { createDraftStore, draftKey, emptyCompletionDraft } from '../src';
import type { StoragePort } from '../src';
import { createFakeClock, createFakeVisibility, createMemoryStorage } from '../src/testing';

const MARCO = 'u-marco';
const ANA = 'u-ana';
const WO = 'wo-rtu-04';

function setup() {
  const storage = createMemoryStorage();
  const clock = createFakeClock(1_000);
  const store = createDraftStore(storage, { clock });
  return { storage, clock, store };
}

const draft = (labor: number) => ({ ...emptyCompletionDraft('Marco'), labor_hours: labor });

describe('draft store (FR-7.2, FR-8.1)', () => {
  it('debounces writes by 300 ms and keeps only the latest change', async () => {
    const { storage, clock, store } = setup();
    const set = vi.spyOn(storage, 'set');
    store.save(MARCO, WO, draft(1));
    await clock.advance(200);
    store.save(MARCO, WO, draft(1.5));
    await clock.advance(299);
    expect(set).not.toHaveBeenCalled();
    await clock.advance(1);
    expect(set).toHaveBeenCalledTimes(1);
    expect(storage.data.has(draftKey(MARCO, WO))).toBe(true);
    expect((await store.load(MARCO, WO))?.data.labor_hours).toBe(1.5);
  });

  it('load returns an unwritten change before the debounce fires', async () => {
    const { store } = setup();
    store.save(MARCO, WO, draft(2));
    expect((await store.load(MARCO, WO))?.data.labor_hours).toBe(2);
    expect(await store.load(MARCO, 'other')).toBeNull();
  });

  it('T-COMP-3 draft survives navigate away: a new screen instance reads it back', async () => {
    const { storage, clock, store } = setup();
    store.save(MARCO, WO, { ...draft(3), failure_code: 'COMP-FAIL', notes: 'contactor pitted' });
    await clock.advance(300);
    const nextScreen = createDraftStore(storage, { clock });
    const loaded = await nextScreen.load(MARCO, WO);
    expect(loaded).toMatchObject({
      userId: MARCO,
      woId: WO,
      updatedAt: 1_000,
      data: { failure_code: 'COMP-FAIL', notes: 'contactor pitted', labor_hours: 3 },
    });
  });

  it('T-COMP-3 draft survives background + kill: hiding flushes inside the debounce window', async () => {
    const { storage, clock, store } = setup();
    const visibility = createFakeVisibility(true);
    const unbind = store.bindVisibility(visibility.port);
    store.save(MARCO, WO, draft(4));
    visibility.set(false); // AppState background / visibilitychange hidden, then the process dies
    await clock.advance(0);
    // Reload / relaunch: fresh store over the same persisted storage, no timers ran.
    const relaunched = createDraftStore(createMemoryStorage(storage.data), {
      clock: createFakeClock(),
    });
    expect((await relaunched.load(MARCO, WO))?.data.labor_hours).toBe(4);
    unbind();
    visibility.set(true);
    store.save(MARCO, WO, draft(5));
    visibility.set(false);
    await clock.advance(0);
    expect(JSON.parse(storage.data.get(draftKey(MARCO, WO))!).data.labor_hours).toBe(4);
  });

  it('T-COMP-3 visible again does not write', async () => {
    const { storage, store } = setup();
    const visibility = createFakeVisibility(false);
    store.bindVisibility(visibility.port);
    store.save(MARCO, WO, draft(1));
    visibility.set(true);
    await Promise.resolve();
    expect(storage.data.size).toBe(0);
  });

  it('clear removes the draft and cancels a pending write', async () => {
    const { storage, clock, store } = setup();
    store.save(MARCO, WO, draft(1));
    await clock.advance(300);
    store.save(MARCO, WO, draft(2));
    await store.clear(MARCO, WO);
    await clock.advance(1000);
    expect(storage.data.size).toBe(0);
    expect(clock.pending()).toBe(0);
    expect(await store.load(MARCO, WO)).toBeNull();
  });

  it('a write in flight cannot resurrect a draft cleared after it', async () => {
    const { storage, store } = setup();
    store.save(MARCO, WO, draft(1));
    const flushing = store.flush();
    const clearing = store.clear(MARCO, WO);
    await Promise.all([flushing, clearing]);
    expect(storage.data.size).toBe(0);
    expect(await store.load(MARCO, WO)).toBeNull();
  });

  it('listUnsent returns only this user, oldest first, including unwritten changes', async () => {
    const { clock, store } = setup();
    store.save(MARCO, 'wo-1', draft(1));
    await clock.advance(300);
    store.save(ANA, 'wo-2', draft(2));
    await clock.advance(300);
    store.save(MARCO, 'wo-3', draft(3));
    const unsent = await store.listUnsent(MARCO);
    expect(unsent.map((d) => d.woId)).toEqual(['wo-1', 'wo-3']);
  });

  it('clearAllForUser removes written and pending drafts of that user only (sign-out)', async () => {
    const { storage, clock, store } = setup();
    store.save(MARCO, 'wo-1', draft(1));
    store.save(ANA, 'wo-2', draft(2));
    await clock.advance(300);
    store.save(MARCO, 'wo-3', draft(3));
    await store.clearAllForUser(MARCO);
    await clock.advance(1000);
    expect(await store.listUnsent(MARCO)).toEqual([]);
    expect([...storage.data.keys()]).toEqual([draftKey(ANA, 'wo-2')]);
  });

  it('keys escape separators so one user cannot see another user prefix', async () => {
    const { clock, store } = setup();
    store.save('u:1', 'wo', draft(1));
    store.save('u', '1:wo', draft(2));
    await clock.advance(300);
    expect((await store.listUnsent('u')).map((d) => d.woId)).toEqual(['1:wo']);
  });

  it('ignores corrupt or foreign entries', async () => {
    const { storage, store } = setup();
    await storage.set(draftKey(MARCO, 'bad-json'), '{not json');
    await storage.set(draftKey(MARCO, 'old'), JSON.stringify({ v: 0, userId: MARCO, woId: 'old' }));
    await storage.set(draftKey(MARCO, 'shape'), JSON.stringify({ v: 1, userId: 7 }));
    expect(await store.load(MARCO, 'bad-json')).toBeNull();
    expect(await store.listUnsent(MARCO)).toEqual([]);
  });

  it('a failed write keeps the change pending, reports it, and retries', async () => {
    const backing = createMemoryStorage();
    let failures = 1;
    const flaky: StoragePort = {
      ...backing,
      set: async (k, v) => {
        if (failures > 0) {
          failures -= 1;
          throw new Error('quota');
        }
        await backing.set(k, v);
      },
    };
    const clock = createFakeClock();
    const onError = vi.fn();
    const store = createDraftStore(flaky, { clock, onError });
    store.save(MARCO, WO, draft(6));
    await clock.advance(300);
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'quota' }));
    expect((await store.load(MARCO, WO))?.data.labor_hours).toBe(6);
    await clock.advance(300);
    expect(backing.data.has(draftKey(MARCO, WO))).toBe(true);
  });

  it('flush rejects on storage failure; a newer save wins over the failed one', async () => {
    const backing = createMemoryStorage();
    const flaky: StoragePort = {
      ...backing,
      set: async () => {
        throw new Error('disk');
      },
    };
    const clock = createFakeClock();
    const store = createDraftStore(flaky, { clock });
    store.save(MARCO, WO, draft(1));
    const flushing = store.flush();
    store.save(MARCO, WO, draft(2));
    await expect(flushing).rejects.toThrow('disk');
    expect((await store.load(MARCO, WO))?.data.labor_hours).toBe(2);
    await expect(store.dispose()).rejects.toThrow('disk');
  });

  it('flush on hide routes failures to onError; dispose flushes', async () => {
    const backing = createMemoryStorage();
    const onError = vi.fn();
    const failing: StoragePort = { ...backing, set: () => Promise.reject(new Error('x')) };
    const clock = createFakeClock();
    const vis = createFakeVisibility();
    const bad = createDraftStore(failing, { clock, onError });
    bad.bindVisibility(vis.port);
    bad.save(MARCO, WO, draft(1));
    vis.set(false);
    await clock.advance(0);
    expect(onError).toHaveBeenCalled();

    const good = createDraftStore(backing, { clock });
    good.save(MARCO, WO, draft(1));
    await good.dispose();
    expect(backing.data.size).toBe(1);
    await good.flush();
  });

  it('uses the system clock and default debounce when none is injected', async () => {
    vi.useFakeTimers();
    try {
      const storage = createMemoryStorage();
      const store = createDraftStore(storage);
      store.save(MARCO, WO, draft(1));
      await vi.advanceTimersByTimeAsync(299);
      expect(storage.data.size).toBe(0);
      await vi.advanceTimersByTimeAsync(1);
      expect(storage.data.size).toBe(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
