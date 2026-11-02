import type { ClockPort, StoragePort, TimerHandle, Unsubscribe, VisibilityPort } from '../ports';
import { systemClock } from '../ports';
import type { CompletionDraft } from './types';

/** FR-7.2: autosave is debounced 300 ms. */
export const DRAFT_DEBOUNCE_MS = 300;
const PREFIX = 'draft:';
const VERSION = 1;

export interface StoredDraft<T> {
  userId: string;
  woId: string;
  /** Epoch ms of the last `save`. */
  updatedAt: number;
  data: T;
}

export interface DraftStoreOptions {
  debounceMs?: number;
  clock?: ClockPort;
  /** Called when a debounced background write fails; the draft stays pending and is retried. */
  onError?: (error: unknown) => void;
}

export interface DraftStore<T> {
  /** Records a change; it is written after `debounceMs` of quiet, or on `flush`. */
  save(userId: string, woId: string, data: T): void;
  /** Latest draft for the WO, including a change not yet written. */
  load(userId: string, woId: string): Promise<StoredDraft<T> | null>;
  /** Writes every pending change now. Rejects if storage fails (the change stays pending). */
  flush(): Promise<void>;
  /** Deletes the draft. Call only after the server confirmed the submit (FR-7.2). */
  clear(userId: string, woId: string): Promise<void>;
  /** Drafts the user still has on this device (sign-out warning, FR-8.1), oldest first. */
  listUnsent(userId: string): Promise<StoredDraft<T>[]>;
  /** Removes every draft of the user (sign-out, FR-8.1). */
  clearAllForUser(userId: string): Promise<void>;
  /** Flushes whenever the app is hidden or backgrounded, so a draft survives a kill. */
  bindVisibility(visibility: VisibilityPort): Unsubscribe;
  /** Cancels timers (pending changes are flushed first). */
  dispose(): Promise<void>;
}

const enc = encodeURIComponent;
const userPrefix = (userId: string) => `${PREFIX}${enc(userId)}:`;
export const draftKey = (userId: string, woId: string) => `${userPrefix(userId)}${enc(woId)}`;

function parse<T>(raw: string | null): StoredDraft<T> | null {
  if (raw === null) return null;
  try {
    const v = JSON.parse(raw) as { v?: unknown } & StoredDraft<T>;
    if (v.v !== VERSION || typeof v.userId !== 'string' || typeof v.woId !== 'string') return null;
    return { userId: v.userId, woId: v.woId, updatedAt: v.updatedAt, data: v.data };
  } catch {
    return null;
  }
}

export function createDraftStore<T = CompletionDraft>(
  storage: StoragePort,
  options: DraftStoreOptions = {},
): DraftStore<T> {
  const debounceMs = options.debounceMs ?? DRAFT_DEBOUNCE_MS;
  const clock = options.clock ?? systemClock();
  const onError = options.onError ?? (() => {});
  const pending = new Map<string, { draft: StoredDraft<T>; timer: TimerHandle }>();
  // Storage calls for one key run strictly in order, so a late write can't resurrect a cleared draft.
  const chains = new Map<string, Promise<void>>();

  const run = (key: string, op: () => Promise<void>): Promise<void> => {
    const next = (chains.get(key) ?? Promise.resolve()).catch(() => {}).then(op);
    chains.set(key, next);
    const cleanup = () => {
      if (chains.get(key) === next) chains.delete(key);
    };
    next.then(cleanup, cleanup);
    return next;
  };

  // Keys cleared while a write was in flight; a failed write must not re-queue them.
  const cleared = new Set<string>();

  const write = (key: string): Promise<void> => {
    const entry = pending.get(key);
    if (!entry) return chains.get(key)?.catch(() => {}) ?? Promise.resolve();
    clock.clearTimeout(entry.timer);
    pending.delete(key);
    const body = JSON.stringify({ v: VERSION, ...entry.draft });
    return run(key, () => storage.set(key, body)).catch((error: unknown) => {
      // Keep the change unless a newer save or a clear superseded it.
      if (!pending.has(key) && !cleared.has(key)) {
        pending.set(key, { draft: entry.draft, timer: schedule(key) });
      }
      throw error;
    });
  };

  const schedule = (key: string) =>
    clock.setTimeout(() => {
      write(key).catch(onError);
    }, debounceMs);

  const flush = async () => {
    const results = await Promise.allSettled([...pending.keys()].map(write));
    const failed = results.find((r): r is PromiseRejectedResult => r.status === 'rejected');
    if (failed) throw failed.reason;
  };

  const drop = (key: string) => {
    const entry = pending.get(key);
    if (entry) clock.clearTimeout(entry.timer);
    pending.delete(key);
    cleared.add(key);
    return run(key, () => storage.delete(key)).finally(() => cleared.delete(key));
  };

  return {
    save(userId, woId, data) {
      const key = draftKey(userId, woId);
      const existing = pending.get(key);
      if (existing) clock.clearTimeout(existing.timer);
      cleared.delete(key);
      pending.set(key, {
        draft: { userId, woId, updatedAt: clock.now(), data },
        timer: schedule(key),
      });
    },
    async load(userId, woId) {
      const key = draftKey(userId, woId);
      const entry = pending.get(key);
      if (entry) return entry.draft;
      await chains.get(key)?.catch(() => {});
      return parse<T>(await storage.get(key));
    },
    flush,
    clear: (userId, woId) => drop(draftKey(userId, woId)),
    async listUnsent(userId) {
      const prefix = userPrefix(userId);
      const byKey = new Map<string, StoredDraft<T>>();
      for (const key of await storage.keys(prefix)) {
        const draft = parse<T>(await storage.get(key));
        if (draft) byKey.set(key, draft);
      }
      for (const [key, entry] of pending) if (key.startsWith(prefix)) byKey.set(key, entry.draft);
      return [...byKey.values()].sort((a, b) => a.updatedAt - b.updatedAt);
    },
    async clearAllForUser(userId) {
      const prefix = userPrefix(userId);
      const keys = new Set([...pending.keys()].filter((k) => k.startsWith(prefix)));
      for (const key of await storage.keys(prefix)) keys.add(key);
      await Promise.all([...keys].map(drop));
    },
    bindVisibility(visibility) {
      return visibility.subscribe((visible) => {
        if (!visible) flush().catch(onError);
      });
    },
    async dispose() {
      await flush();
    },
  };
}
