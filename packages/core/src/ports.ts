/**
 * Injected ports (IMPLEMENTATION_PLAN §4). packages/core never touches a platform API directly:
 * web supplies localStorage / IndexedDB / navigator.onLine / visibilitychange, mobile supplies
 * AsyncStorage / NetInfo / AppState. In-memory adapters for tests live in `./testing`.
 */

/** Async string key-value storage. */
export interface StoragePort {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  delete(key: string): Promise<void>;
  /** Every stored key, or only those starting with `prefix`. */
  keys(prefix?: string): Promise<string[]>;
}

/** Opaque timer handle returned by {@link ClockPort.setTimeout}. */
export type TimerHandle = unknown;

/** Wall clock and timers, so tests can drive time deterministically. */
export interface ClockPort {
  /** Epoch milliseconds. */
  now(): number;
  setTimeout(callback: () => void, ms: number): TimerHandle;
  clearTimeout(handle: TimerHandle): void;
}

export type Unsubscribe = () => void;

/** Network reachability (`navigator.onLine` + online/offline events, NetInfo). */
export interface ConnectivityPort {
  isOnline(): boolean;
  subscribe(listener: (online: boolean) => void): Unsubscribe;
}

/** Foreground state (`visibilitychange`, AppState `active` vs `background`). */
export interface VisibilityPort {
  isVisible(): boolean;
  subscribe(listener: (visible: boolean) => void): Unsubscribe;
}

interface TimerGlobals {
  setTimeout(callback: () => void, ms: number): TimerHandle;
  clearTimeout(handle: TimerHandle): void;
}

/** ClockPort over the host's `Date.now` and timers (same on browsers, Node and React Native). */
export function systemClock(): ClockPort {
  const g = globalThis as unknown as TimerGlobals;
  return {
    now: () => Date.now(),
    setTimeout: (callback, ms) => g.setTimeout(callback, ms),
    clearTimeout: (handle) => g.clearTimeout(handle),
  };
}
