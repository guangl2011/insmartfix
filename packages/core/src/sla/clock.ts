/**
 * Server clock (FR-2.4, T-SLA-2). Every API body carries `server_time`; the offset between it and
 * the device clock cancels device skew, so countdowns match the server's `sla_deadline`.
 */
import type { ClockPort } from '../ports';

export interface ObserveOptions {
  /** Device time (ms) when the request was sent. With it, the offset uses the request midpoint. */
  sentAt?: number;
}

export interface ServerClock extends ClockPort {
  /** Records a response's `server_time`. Returns false (and keeps the old offset) if unusable. */
  observe(serverTime: string | null | undefined, options?: ObserveOptions): boolean;
  /** Convenience: observe `body.server_time` from any parsed response body. */
  observeBody(body: unknown, options?: ObserveOptions): boolean;
  /** server − device, in ms (0 until the first observation). */
  offsetMs(): number;
  hasObservation(): boolean;
}

/** A ClockPort whose `now()` is server time; timers delegate to the device clock. */
export function createServerClock(device: ClockPort): ServerClock {
  let offset = 0;
  let observed = false;

  const observe: ServerClock['observe'] = (serverTime, options = {}) => {
    const server = typeof serverTime === 'string' ? Date.parse(serverTime) : Number.NaN;
    if (Number.isNaN(server)) return false;
    const receivedAt = device.now();
    const local = options.sentAt === undefined ? receivedAt : (options.sentAt + receivedAt) / 2;
    offset = server - local;
    observed = true;
    return true;
  };

  return {
    now: () => device.now() + offset,
    setTimeout: (callback, ms) => device.setTimeout(callback, ms),
    clearTimeout: (handle) => device.clearTimeout(handle),
    observe,
    observeBody: (body, options) =>
      typeof body === 'object' && body !== null && 'server_time' in body
        ? observe((body as { server_time?: string }).server_time, options)
        : false,
    offsetMs: () => offset,
    hasObservation: () => observed,
  };
}

/** Milliseconds until `deadline` on the given (server) clock, or null without a valid deadline. */
export function slaRemainingMs(
  deadline: string | null | undefined,
  clock: Pick<ClockPort, 'now'>,
): number | null {
  if (!deadline) return null;
  const t = Date.parse(deadline);
  return Number.isNaN(t) ? null : t - clock.now();
}
