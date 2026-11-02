/**
 * Scenario switches for the contract mocks: latency, 5xx injection, network errors and the
 * stale-offer race (TEST_PLAN T-INBOX-4, T-INBOX-5, T-COMP-4, resilience). Flip them from a test,
 * or set them for `pnpm dev:mock` with `MOCK_SCENARIOS`, e.g.
 * `MOCK_SCENARIOS="latency=800,race,fail=503:2:/complete"`.
 */
import type { components } from '../src/schema';

export type OfferUnavailableReason = components['schemas']['OfferUnavailableReason'];

export interface RequestMatcher {
  /** Substring or pattern tested against the URL pathname. Omit to match every request. */
  path?: string | RegExp;
  method?: string;
}

interface Rule extends RequestMatcher {
  times: number;
}

export interface Scenarios {
  /** Fixed delay before every response (default 0). */
  setLatency(ms: number): void;
  latency(): number;
  /** The next `times` matching requests return `status` with an INTERNAL envelope. */
  failNext(status: 500 | 502 | 503 | 504, times?: number, match?: RequestMatcher): void;
  /** The next `times` matching requests fail at the network level (fetch rejects). */
  networkErrorNext(times?: number, match?: RequestMatcher): void;
  /**
   * The stale-offer race: the server has already moved this offer on (expired, reassigned to Ana,
   * or withdrawn), but the client still shows it. The next accept of `woId` gets
   * `409 OFFER_UNAVAILABLE {reason}` and the offer leaves the caller's schedule.
   */
  raceOffer(woId: string, reason?: OfferUnavailableReason): void;
  /** Consumed by the handlers: the pending race for `woId`, if any. */
  takeRace(woId: string): OfferUnavailableReason | null;
  /** Consumed by the handlers before each request. */
  next(request: Request): { kind: 'ok' } | { kind: 'fail'; status: number } | { kind: 'network' };
  reset(): void;
}

const matches = (rule: RequestMatcher, request: Request) => {
  if (rule.method && rule.method.toUpperCase() !== request.method) return false;
  if (rule.path === undefined) return true;
  const path = new URL(request.url).pathname;
  return typeof rule.path === 'string' ? path.includes(rule.path) : rule.path.test(path);
};

export function createScenarios(): Scenarios {
  let latency = 0;
  let fails: (Rule & { status: number })[] = [];
  let networks: Rule[] = [];
  const races = new Map<string, OfferUnavailableReason>();

  const take = <R extends Rule>(rules: R[], request: Request): R | undefined => {
    const rule = rules.find((r) => r.times > 0 && matches(r, request));
    if (rule) rule.times -= 1;
    return rule;
  };

  return {
    setLatency: (ms) => {
      latency = Math.max(0, ms);
    },
    latency: () => latency,
    failNext: (status, times = 1, match = {}) => {
      fails.push({ ...match, status, times });
    },
    networkErrorNext: (times = 1, match = {}) => {
      networks.push({ ...match, times });
    },
    raceOffer: (woId, reason = 'reassigned') => {
      races.set(woId, reason);
    },
    takeRace: (woId) => {
      const reason = races.get(woId) ?? null;
      races.delete(woId);
      return reason;
    },
    next: (request) => {
      if (take(networks, request)) return { kind: 'network' };
      const fail = take(fails, request);
      return fail ? { kind: 'fail', status: fail.status } : { kind: 'ok' };
    },
    reset: () => {
      latency = 0;
      fails = [];
      networks = [];
      races.clear();
    },
  };
}

/**
 * Applies a `MOCK_SCENARIOS` string: comma-separated `latency=<ms>`, `race[=<woId>[:<reason>]]`,
 * `fail=<status>[:<times>[:<path>]]`, `network[=<times>[:<path>]]`. Unknown entries throw, so a
 * typo can't silently run a demo without the scenario it was meant to show.
 */
export function applyScenarioString(
  scenarios: Scenarios,
  spec: string,
  defaultRaceWo: string,
): void {
  for (const raw of spec
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)) {
    const [name, arg = ''] = raw.split('=', 2) as [string, string?];
    const parts = arg.split(':').filter(Boolean);
    if (name === 'latency' && /^\d+$/.test(arg)) scenarios.setLatency(Number(arg));
    else if (name === 'race')
      scenarios.raceOffer(
        parts[0] ?? defaultRaceWo,
        (parts[1] as OfferUnavailableReason | undefined) ?? 'reassigned',
      );
    else if (name === 'fail' && /^(500|502|503|504)$/.test(parts[0] ?? ''))
      scenarios.failNext(
        Number(parts[0]) as 500,
        Number(parts[1] ?? 1),
        parts[2] ? { path: parts[2] } : {},
      );
    else if (name === 'network')
      scenarios.networkErrorNext(Number(parts[0] ?? 1), parts[1] ? { path: parts[1] } : {});
    else throw new Error(`Unknown MOCK_SCENARIOS entry: ${raw}`);
  }
}
