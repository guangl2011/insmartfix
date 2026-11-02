/**
 * Typed fetch client for the InsmartFix API (`/v1`), generated types from openapi.json
 * (openapi-typescript) + openapi-fetch.
 *
 * - `getToken` adds `Authorization: Bearer …` (server-side web proxy and mobile). Browser code
 *   never calls the API directly and never has a token (spec §4.2, FR-1.2).
 * - `onServerTime` receives every JSON body's `server_time` with the request's send time, for
 *   `@insmartfix/core`'s server clock (FR-2.4).
 */
import createClient, { type Middleware } from 'openapi-fetch';
import type { paths } from './schema';

export interface ApiClientOptions {
  /** API origin, e.g. `http://api:8000`. Paths already include `/v1`. */
  baseUrl: string;
  /** Bearer token source. Return null/undefined for unauthenticated calls. */
  getToken?: () => string | null | undefined | Promise<string | null | undefined>;
  fetch?: (request: Request) => Promise<Response>;
  headers?: Record<string, string>;
  onServerTime?: (serverTime: string, timing: { sentAt: number }) => void;
  /** Device clock for `timing.sentAt` (default Date.now). */
  now?: () => number;
}

/** `createApiClient({ baseUrl, getToken, fetch })`; the M0 form `(baseUrl, options)` still works. */
export function createApiClient(
  optionsOrBaseUrl: ApiClientOptions | string,
  rest: Omit<ApiClientOptions, 'baseUrl'> = {},
) {
  const options =
    typeof optionsOrBaseUrl === 'string'
      ? { ...rest, baseUrl: optionsOrBaseUrl }
      : optionsOrBaseUrl;
  const { getToken, onServerTime, now = Date.now } = options;
  const client = createClient<paths>({
    baseUrl: options.baseUrl.replace(/\/+$/, ''),
    ...(options.fetch ? { fetch: options.fetch } : {}),
    ...(options.headers ? { headers: options.headers } : {}),
  });
  const sentAt = new WeakMap<Request, number>();

  const middleware: Middleware = {
    async onRequest({ request }) {
      if (getToken && !request.headers.has('Authorization')) {
        const token = await getToken();
        if (token) request.headers.set('Authorization', `Bearer ${token}`);
      }
      sentAt.set(request, now());
      return request;
    },
    async onResponse({ request, response }) {
      if (!onServerTime || !response.headers.get('content-type')?.includes('json')) return;
      try {
        const body: unknown = await response.clone().json();
        const t = (body as { server_time?: unknown } | null)?.server_time;
        if (typeof t === 'string') onServerTime(t, { sentAt: sentAt.get(request) ?? now() });
      } catch {
        // Unparseable body: openapi-fetch reports it; nothing to observe.
      }
    },
  };
  client.use(middleware);
  return client;
}

export type ApiClient = ReturnType<typeof createApiClient>;
