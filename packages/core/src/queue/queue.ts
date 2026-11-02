import type { CompletionReport } from '../completion/types';
import type { DraftPhoto } from '../drafts/types';
import type {
  ClockPort,
  ConnectivityPort,
  StoragePort,
  TimerHandle,
  Unsubscribe,
  VisibilityPort,
} from '../ports';
import { systemClock } from '../ports';
import type {
  CompleteItem,
  CompletionResult,
  PhotoUploadItem,
  QueueError,
  QueueEvent,
  QueueItem,
  QueueTransport,
} from './types';

export interface OfflineQueueOptions {
  userId: string;
  storage: StoragePort;
  transport: QueueTransport;
  connectivity: ConnectivityPort;
  /** Flush when the app comes back to the foreground. */
  visibility?: VisibilityPort;
  /** Cleared for a WO only after the server confirmed its completion (FR-7.2). */
  drafts?: { clear(userId: string, woId: string): Promise<void> };
  clock?: ClockPort;
  /**
   * Cryptographically random key source; defaults to `crypto.randomUUID`. On React Native pass
   * `newIdempotencyKey` from `@insmartfix/contracts` (it also uses `getRandomValues`).
   */
  generateKey?: () => string;
  backoff?: { baseMs?: number; maxMs?: number };
  /** [0, 1) jitter source; defaults to `Math.random`. */
  random?: () => number;
}

export interface OfflineQueue {
  /** Subscribes to connectivity (and visibility) and flushes now if online. */
  start(): Unsubscribe;
  /** Uploads a photo as soon as possible (ahead of its WO's completion). */
  enqueuePhoto(woId: string, localId: string): Promise<PhotoUploadItem | null>;
  /**
   * Queues a completion. Its photos without a `photo_id` are queued first; the completion waits
   * for them and is sent with their server ids. Re-queuing an unsent completion updates it in
   * place; one that was already sent is replaced by a new item with a new key.
   */
  enqueueCompletion(
    woId: string,
    report: Omit<CompletionReport, 'photo_ids'>,
    photos: readonly DraftPhoto[],
  ): Promise<CompleteItem>;
  /** Sends what is due. Single-flight: a call during a flush joins it (and re-runs once). */
  flush(): Promise<void>;
  list(): Promise<QueueItem[]>;
  /** Moves a dead item back to pending (same key and body) and flushes. */
  retry(itemId: string): Promise<void>;
  /** Drops an item; a discarded photo is also dropped from its WO's completion. */
  discard(itemId: string): Promise<void>;
  /** Sign-out (FR-8.1): forget everything queued for this user. */
  clearAll(): Promise<void>;
  subscribe(listener: (event: QueueEvent) => void): Unsubscribe;
}

interface State {
  v: 1;
  items: QueueItem[];
  /** Server photo ids by WO and local id, kept until the WO's completion succeeds. */
  uploaded: Record<string, Record<string, string>>;
}

type Outcome = 'ok' | 'retry' | 'auth' | 'dead';

/** JSON round-trip copy (portable to every JS engine the apps run on). */
const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

const empty = (): State => ({ v: 1, items: [], uploaded: {} });

export const queueKey = (userId: string) => `queue:${encodeURIComponent(userId)}`;

function defaultKey(): () => string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  if (!c?.randomUUID)
    throw new Error('createOfflineQueue: provide generateKey (no crypto.randomUUID)');
  return () => c.randomUUID!();
}

function toQueueError(e: unknown): QueueError {
  const o = (typeof e === 'object' && e !== null ? e : {}) as Partial<QueueError>;
  return {
    ...(typeof o.status === 'number' ? { status: o.status } : {}),
    ...(typeof o.code === 'string' ? { code: o.code } : {}),
    message: typeof o.message === 'string' ? o.message : String(e),
  };
}

/** Network errors, 408, 429 and 5xx are retried; 401 pauses; any other 4xx dead-letters. */
function classify(err: QueueError): Exclude<Outcome, 'ok'> {
  const s = err.status;
  if (s === undefined || s === 408 || s === 429 || s >= 500) return 'retry';
  return s === 401 ? 'auth' : 'dead';
}

export function createOfflineQueue(o: OfflineQueueOptions): OfflineQueue {
  const clock = o.clock ?? systemClock();
  const newKey = o.generateKey ?? defaultKey();
  const random = o.random ?? Math.random;
  const baseMs = o.backoff?.baseMs ?? 2_000;
  const maxMs = o.backoff?.maxMs ?? 300_000;
  const key = queueKey(o.userId);
  const listeners = new Set<(e: QueueEvent) => void>();

  let state = empty();
  let writes: Promise<void> = Promise.resolve();
  let flushing: Promise<void> | null = null;
  let again = false;
  let paused = false;
  let timer: TimerHandle | undefined;

  const emit = (e: QueueEvent) => {
    for (const l of [...listeners]) {
      try {
        l(e);
      } catch {
        // A UI listener bug must never interrupt a send or skip clearing a confirmed draft.
      }
    }
  };
  const snapshot = () => clone(state.items);

  // A storage read failure rejects every call: starting empty would overwrite the saved queue.
  const ready = (async () => {
    const raw = await o.storage.get(key);
    if (raw === null) return;
    try {
      const parsed = JSON.parse(raw) as State;
      if (parsed?.v === 1 && Array.isArray(parsed.items)) {
        state = { v: 1, items: parsed.items, uploaded: parsed.uploaded ?? {} };
        return;
      }
    } catch {
      // fall through: keep the unreadable copy for support, start empty
    }
    await o.storage.set(`${key}:corrupt:${clock.now()}`, raw);
  })();
  ready.catch(() => {});

  /** Persists the state; callers await it before any network call that depends on it. */
  const save = () => {
    const body = JSON.stringify(state);
    writes = writes.catch(() => {}).then(() => o.storage.set(key, body));
    const done = writes;
    return done.then(() => emit({ type: 'changed', items: snapshot() }));
  };

  const resolved = (item: CompleteItem, localId: string) =>
    state.uploaded[item.woId]?.[localId] ?? item.knownPhotoIds[localId];
  const photoItem = (woId: string, localId: string) =>
    state.items.find(
      (i): i is PhotoUploadItem =>
        i.kind === 'photo_upload' && i.woId === woId && i.localId === localId,
    );
  const waitingOnPhotos = (item: QueueItem) =>
    item.kind === 'complete' &&
    !item.body &&
    item.photoLocalIds.some((l) => !resolved(item, l) && photoItem(item.woId, l));
  const remove = (id: string) => {
    state.items = state.items.filter((i) => i.id !== id);
  };
  const base = (woId: string) => ({
    id: newKey(),
    woId,
    idempotencyKey: newKey(),
    status: 'pending' as const,
    attempts: 0,
    nextAttemptAt: clock.now(),
    createdAt: clock.now(),
  });

  /** Records a failed attempt; returns how the pass should continue. */
  async function failed(item: QueueItem, e: unknown): Promise<Exclude<Outcome, 'ok'>> {
    const err = toQueueError(e);
    const outcome = classify(err);
    if (outcome === 'auth') {
      emit({ type: 'auth_required' });
      return outcome;
    }
    item.lastError = err;
    if (outcome === 'retry') {
      item.attempts += 1;
      const delay = Math.min(maxMs, baseMs * 2 ** (item.attempts - 1));
      item.nextAttemptAt = clock.now() + Math.round(delay * (0.5 + random() / 2));
    } else {
      item.status = 'dead';
    }
    // The item may have been discarded or replaced while it was in flight.
    if (state.items.includes(item)) await save();
    if (outcome === 'dead') emit({ type: 'dead', item: clone(item) });
    return outcome;
  }

  async function sendPhoto(item: PhotoUploadItem): Promise<Outcome> {
    let photoId: string;
    try {
      const res = await o.transport.uploadPhoto({
        woId: item.woId,
        localId: item.localId,
        idempotencyKey: item.idempotencyKey,
      });
      photoId = res.photo_id;
    } catch (e) {
      return failed(item, e);
    }
    if (!state.items.includes(item)) return 'ok'; // discarded or signed out while uploading
    (state.uploaded[item.woId] ??= {})[item.localId] = photoId;
    remove(item.id);
    await save();
    emit({ type: 'photo_uploaded', woId: item.woId, localId: item.localId, photoId });
    return 'ok';
  }

  async function sendCompletion(item: CompleteItem): Promise<Outcome> {
    if (!item.body) {
      // Freeze the body and persist it before the first send; every retry reuses it verbatim.
      const photoIds = item.photoLocalIds.flatMap((l) => resolved(item, l) ?? []);
      item.body = { ...item.report, photo_ids: photoIds };
      await save();
    }
    let result: CompletionResult;
    try {
      result = await o.transport.complete({
        woId: item.woId,
        body: item.body,
        idempotencyKey: item.idempotencyKey,
      });
    } catch (e) {
      return failed(item, e);
    }
    remove(item.id);
    if (!state.items.some((i) => i.woId === item.woId)) delete state.uploaded[item.woId];
    await save();
    await o.drafts?.clear(o.userId, item.woId).catch((error) => emit({ type: 'error', error }));
    emit({ type: 'completed', woId: item.woId, result });
    return 'ok';
  }

  const send = (item: QueueItem) =>
    item.kind === 'photo_upload' ? sendPhoto(item) : sendCompletion(item);

  const due = (i: QueueItem) => i.status === 'pending' && !waitingOnPhotos(i);

  function scheduleNext() {
    if (timer !== undefined) clock.clearTimeout(timer);
    timer = undefined;
    if (paused || !o.connectivity.isOnline()) return;
    const next = Math.min(...state.items.filter(due).map((i) => i.nextAttemptAt));
    if (Number.isFinite(next)) {
      timer = clock.setTimeout(
        () => {
          timer = undefined;
          run(false).catch((error) => emit({ type: 'error', error }));
        },
        Math.max(0, next - clock.now()),
      );
    }
  }

  async function pass() {
    while (!paused && o.connectivity.isOnline()) {
      const now = clock.now();
      const item = state.items.find((i) => due(i) && i.nextAttemptAt <= now);
      if (!item) break;
      const outcome = await send(item);
      if (outcome === 'auth') paused = true;
      if (outcome === 'retry' || outcome === 'auth') break;
    }
  }

  function run(external: boolean): Promise<void> {
    if (external) paused = false;
    if (flushing) {
      again = true;
      return flushing;
    }
    flushing = (async () => {
      await ready;
      try {
        do {
          again = false;
          await pass();
        } while (again && !paused);
      } finally {
        flushing = null;
        scheduleNext();
      }
    })();
    return flushing;
  }

  const kick = () => {
    run(true).catch((error) => emit({ type: 'error', error }));
  };

  async function addPhoto(woId: string, localId: string): Promise<PhotoUploadItem | null> {
    if (state.uploaded[woId]?.[localId]) return null;
    const existing = photoItem(woId, localId);
    if (existing) return existing;
    const item: PhotoUploadItem = { ...base(woId), kind: 'photo_upload', localId };
    state.items.push(item);
    return item;
  }

  return {
    start() {
      const offs = [o.connectivity.subscribe((online) => online && kick())];
      if (o.visibility) offs.push(o.visibility.subscribe((visible) => visible && kick()));
      kick();
      return () => {
        for (const off of offs) off();
        if (timer !== undefined) clock.clearTimeout(timer);
        timer = undefined;
      };
    },
    async enqueuePhoto(woId, localId) {
      await ready;
      const item = await addPhoto(woId, localId);
      await save();
      kick();
      return item && clone(item);
    },
    async enqueueCompletion(woId, report, photos) {
      await ready;
      const knownPhotoIds: Record<string, string> = {};
      for (const p of photos) {
        if (p.photo_id) knownPhotoIds[p.local_id] = p.photo_id;
        else await addPhoto(woId, p.local_id);
      }
      const fields = {
        report: clone(report),
        photoLocalIds: photos.map((p) => p.local_id),
        knownPhotoIds,
      };
      const current = state.items.find(
        (i): i is CompleteItem => i.kind === 'complete' && i.woId === woId,
      );
      let item: CompleteItem;
      if (current && !current.body) {
        item = Object.assign(current, fields, { status: 'pending', nextAttemptAt: clock.now() });
      } else {
        if (current) remove(current.id);
        item = { ...base(woId), kind: 'complete', ...fields };
        state.items.push(item);
      }
      await save();
      kick();
      return clone(item);
    },
    flush: () => run(true),
    list: async () => {
      await ready;
      return snapshot();
    },
    async retry(itemId) {
      await ready;
      const item = state.items.find((i) => i.id === itemId);
      if (!item) return;
      Object.assign(item, { status: 'pending', attempts: 0, nextAttemptAt: clock.now() });
      await save();
      await run(true);
    },
    async discard(itemId) {
      await ready;
      const item = state.items.find((i) => i.id === itemId);
      if (!item) return;
      remove(itemId);
      if (item.kind === 'photo_upload') {
        for (const c of state.items) {
          if (c.kind === 'complete' && c.woId === item.woId && !c.body) {
            c.photoLocalIds = c.photoLocalIds.filter((l) => l !== item.localId);
          }
        }
      }
      await save();
      kick();
    },
    async clearAll() {
      await ready;
      state = empty();
      if (timer !== undefined) clock.clearTimeout(timer);
      timer = undefined;
      // Also drops any set-aside unreadable copy, so nothing of this user's work stays behind.
      writes = writes
        .catch(() => {})
        .then(async () => {
          const extra = await o.storage.keys(`${key}:`);
          await Promise.all([key, ...extra].map((k) => o.storage.delete(k)));
        });
      await writes;
      emit({ type: 'changed', items: [] });
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
