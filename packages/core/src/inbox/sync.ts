/**
 * Inbox sync controller (FR-2.5, FR-2.6, FR-2.7; design §6.2 "Refresh & the stale-offer race").
 *
 * - Refetches every 20 s while visible, and immediately when the app becomes visible again or
 *   the connection returns. Hidden or offline → no polling.
 * - A failed refresh keeps the last good list and sets `status: 'error'` (the screen shows the
 *   list plus an error with Retry). Polling continues, so the inbox self-heals (NFR-5).
 * - Offline keeps the last list with `status: 'offline'`; accept is refused locally.
 * - Accept is server-authoritative: `409 OFFER_UNAVAILABLE` becomes a `toast` event and an
 *   immediate refresh, so the card leaves with the server's list (never removed on a guess).
 *   A success removes the card at once and refreshes. Either way, a poll that started before
 *   the accept answered is discarded and refetched, so stale data can't keep or resurrect a card.
 *
 * Platform-free: web and mobile inject the fetchers and ports.
 */
import type { ClockPort, ConnectivityPort, TimerHandle, VisibilityPort } from '../ports';
import { sortActive, sortOffers } from '../ordering';
import type { ServerClock } from '../sla/clock';

export const INBOX_REFRESH_MS = 20_000;
export const OFFER_UNAVAILABLE_TOAST = "This offer just expired — it's been reassigned";

export interface InboxItem {
  wo_id: string;
  sla_deadline?: string | null;
  last_advanced_at?: string | null;
}

/** `GET /me/schedule` (or `/contractor/{cid}/schedule`) body, spec §5. */
export interface ScheduleResponse<O extends InboxItem> {
  offers: O[];
  active: O[];
  voice_bookings?: unknown[];
  server_time?: string;
}

/** What the accept adapter reports. Thrown errors are treated as network failures. */
export type AcceptOutcome<D> =
  { ok: true; detail: D } | { ok: false; status: number; code?: string; reason?: string };

export type AcceptResult<D> =
  | { kind: 'accepted'; detail: D }
  | { kind: 'unavailable'; reason: string | undefined }
  | { kind: 'offline' }
  | { kind: 'failed'; status: number | null };

export type InboxStatus = 'loading' | 'ready' | 'error' | 'offline';

export interface InboxState<O extends InboxItem> {
  status: InboxStatus;
  offers: readonly O[];
  active: readonly O[];
  voiceBookings: readonly unknown[];
  /** Device time of the last successful refresh, or null before the first. */
  lastUpdatedAt: number | null;
  error: unknown;
  refreshing: boolean;
}

export type InboxEvent<D> =
  | { type: 'toast'; message: string; woId: string; reason: string | undefined }
  | { type: 'accepted'; woId: string; detail: D };

export interface InboxSyncOptions<O extends InboxItem, D> {
  fetchSchedule: () => Promise<ScheduleResponse<O>>;
  accept: (woId: string) => Promise<AcceptOutcome<D>>;
  clock: ClockPort;
  visibility: VisibilityPort;
  connectivity: ConnectivityPort;
  /** Receives each response's `server_time` (FR-2.4). */
  serverClock?: Pick<ServerClock, 'observe'>;
  intervalMs?: number;
}

export interface InboxSync<O extends InboxItem, D> {
  start(): void;
  stop(): void;
  refresh(): Promise<void>;
  /** Same as refresh; the Retry button. */
  retry(): Promise<void>;
  accept(woId: string): Promise<AcceptResult<D>>;
  getState(): InboxState<O>;
  subscribe(listener: (state: InboxState<O>) => void): () => void;
  onEvent(listener: (event: InboxEvent<D>) => void): () => void;
}

export function createInboxSync<O extends InboxItem, D = unknown>(
  options: InboxSyncOptions<O, D>,
): InboxSync<O, D> {
  const { clock, visibility, connectivity } = options;
  const intervalMs = options.intervalMs ?? INBOX_REFRESH_MS;

  let state: InboxState<O> = {
    status: 'loading',
    offers: [],
    active: [],
    voiceBookings: [],
    lastUpdatedAt: null,
    error: null,
    refreshing: false,
  };
  const stateListeners = new Set<(s: InboxState<O>) => void>();
  const eventListeners = new Set<(e: InboxEvent<D>) => void>();
  let running = false;
  let timer: TimerHandle | null = null;
  let inflight: Promise<void> | null = null;
  /** Bumped when local state gets ahead of the server (accept success); older polls are stale. */
  let epoch = 0;
  let unsubscribers: (() => void)[] = [];

  const set = (patch: Partial<InboxState<O>>) => {
    state = { ...state, ...patch };
    for (const l of [...stateListeners]) l(state);
  };
  const emit = (e: InboxEvent<D>) => {
    for (const l of [...eventListeners]) l(e);
  };

  const clearTimer = () => {
    if (timer !== null) clock.clearTimeout(timer);
    timer = null;
  };
  const schedule = () => {
    clearTimer();
    if (running && visibility.isVisible() && connectivity.isOnline())
      timer = clock.setTimeout(() => {
        timer = null;
        void refresh();
      }, intervalMs);
  };

  async function run(): Promise<void> {
    for (;;) {
      const startedAt = epoch;
      try {
        const res = await options.fetchSchedule();
        if (startedAt !== epoch) continue;
        options.serverClock?.observe(res.server_time);
        set({
          status: connectivity.isOnline() ? 'ready' : 'offline',
          offers: sortOffers(res.offers),
          active: sortActive(res.active),
          voiceBookings: res.voice_bookings ?? [],
          lastUpdatedAt: clock.now(),
          error: null,
        });
      } catch (error) {
        if (startedAt !== epoch) continue;
        set(connectivity.isOnline() ? { status: 'error', error } : { status: 'offline' });
      }
      return;
    }
  }

  function refresh(): Promise<void> {
    if (inflight) return inflight;
    if (!connectivity.isOnline()) {
      set({ status: 'offline' });
      return Promise.resolve();
    }
    set({ refreshing: true });
    inflight = run().finally(() => {
      inflight = null;
      set({ refreshing: false });
      schedule();
    });
    return inflight;
  }

  async function accept(woId: string): Promise<AcceptResult<D>> {
    if (!connectivity.isOnline()) return { kind: 'offline' };
    let outcome: AcceptOutcome<D>;
    try {
      outcome = await options.accept(woId);
    } catch {
      return { kind: 'failed', status: null };
    }
    if (outcome.ok) {
      epoch += 1;
      set({ offers: state.offers.filter((o) => o.wo_id !== woId) });
      emit({ type: 'accepted', woId, detail: outcome.detail });
      void refresh();
      return { kind: 'accepted', detail: outcome.detail };
    }
    if (outcome.status === 409 && outcome.code === 'OFFER_UNAVAILABLE') {
      // The server has moved on; a poll already in flight may predate that, so discard it.
      epoch += 1;
      emit({ type: 'toast', message: OFFER_UNAVAILABLE_TOAST, woId, reason: outcome.reason });
      void refresh();
      return { kind: 'unavailable', reason: outcome.reason };
    }
    return { kind: 'failed', status: outcome.status };
  }

  return {
    start() {
      if (running) return;
      running = true;
      unsubscribers = [
        visibility.subscribe((visible) => {
          if (visible) void refresh();
          else clearTimer();
        }),
        connectivity.subscribe((online) => {
          if (online) void refresh();
          else {
            clearTimer();
            set({ status: 'offline' });
          }
        }),
      ];
      if (!connectivity.isOnline()) set({ status: 'offline' });
      else if (visibility.isVisible()) void refresh();
    },
    stop() {
      running = false;
      clearTimer();
      for (const u of unsubscribers) u();
      unsubscribers = [];
    },
    refresh,
    retry: refresh,
    accept,
    getState: () => state,
    subscribe(listener) {
      stateListeners.add(listener);
      return () => {
        stateListeners.delete(listener);
      };
    },
    onEvent(listener) {
      eventListeners.add(listener);
      return () => {
        eventListeners.delete(listener);
      };
    },
  };
}
