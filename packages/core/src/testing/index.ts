/**
 * In-memory port adapters for tests (core, web and mobile). Not for production use.
 */
import type {
  ClockPort,
  ConnectivityPort,
  StoragePort,
  TimerHandle,
  VisibilityPort,
} from '../ports';

export interface MemoryStorage extends StoragePort {
  /** The raw backing map; share it between store instances to simulate a reload or app kill. */
  readonly data: Map<string, string>;
}

export function createMemoryStorage(data: Map<string, string> = new Map()): MemoryStorage {
  return {
    data,
    get: async (key) => data.get(key) ?? null,
    set: async (key, value) => {
      data.set(key, value);
    },
    delete: async (key) => {
      data.delete(key);
    },
    keys: async (prefix = '') => [...data.keys()].filter((k) => k.startsWith(prefix)),
  };
}

/** Lets pending promise callbacks run (enough turns for chained async adapter calls). */
export async function flushMicrotasks(turns = 20): Promise<void> {
  for (let i = 0; i < turns; i += 1) await Promise.resolve();
}

export interface FakeClock extends ClockPort {
  /** Moves time forward, firing due timers in order and letting their async work settle. */
  advance(ms: number): Promise<void>;
  /** Number of timers still scheduled. */
  pending(): number;
}

export function createFakeClock(startMs = 0): FakeClock {
  let now = startMs;
  let seq = 0;
  const timers = new Map<number, { at: number; callback: () => void }>();
  const nextDue = (limit: number) => {
    let best: [number, { at: number; callback: () => void }] | undefined;
    for (const entry of timers) {
      if (entry[1].at <= limit && (!best || entry[1].at < best[1].at)) best = entry;
    }
    return best;
  };
  return {
    now: () => now,
    setTimeout: (callback, ms) => {
      seq += 1;
      timers.set(seq, { at: now + Math.max(0, ms), callback });
      return seq;
    },
    clearTimeout: (handle: TimerHandle) => {
      timers.delete(handle as number);
    },
    pending: () => timers.size,
    advance: async (ms) => {
      const target = now + ms;
      await flushMicrotasks();
      for (let due = nextDue(target); due; due = nextDue(target)) {
        timers.delete(due[0]);
        now = due[1].at;
        due[1].callback();
        await flushMicrotasks();
      }
      now = target;
    },
  };
}

interface Toggle<P> {
  port: P;
  set(value: boolean): void;
}

function createToggle(initial: boolean): {
  get: () => boolean;
  set: (v: boolean) => void;
  subscribe: (l: (v: boolean) => void) => () => void;
} {
  let value = initial;
  const listeners = new Set<(v: boolean) => void>();
  return {
    get: () => value,
    set: (v) => {
      if (v === value) return;
      value = v;
      for (const l of [...listeners]) l(v);
    },
    subscribe: (l) => {
      listeners.add(l);
      return () => {
        listeners.delete(l);
      };
    },
  };
}

export type FakeConnectivity = Toggle<ConnectivityPort>;

export function createFakeConnectivity(online = true): FakeConnectivity {
  const t = createToggle(online);
  return { port: { isOnline: t.get, subscribe: t.subscribe }, set: t.set };
}

export type FakeVisibility = Toggle<VisibilityPort>;

export function createFakeVisibility(visible = true): FakeVisibility {
  const t = createToggle(visible);
  return { port: { isVisible: t.get, subscribe: t.subscribe }, set: t.set };
}
