/**
 * The app's HTTP transport (spec §4.2). `live` is the platform fetch with a timeout, so a dead
 * mechanical-room connection fails fast instead of hanging. `mock` answers in-process from the
 * MSW contract mocks (`DATA_SOURCE=mock`, same screens and code paths, D§13).
 */
import { applyScenarioString, createMockApi, WO, type MockApi } from '@insmartfix/contracts/mocks';
import { getResponse } from 'msw';

export type AppFetch = (request: Request) => Promise<Response>;

export const REQUEST_TIMEOUT_MS = 15_000;

/** Rejects (like a network error) when the server hasn't answered within `ms`. */
export function withTimeout(
  fetchImpl: (input: Request) => Promise<Response>,
  ms = REQUEST_TIMEOUT_MS,
): AppFetch {
  return (request) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ms);
    const upstream = request.signal;
    if (upstream?.aborted) controller.abort();
    else upstream?.addEventListener?.('abort', () => controller.abort());
    return fetchImpl(new Request(request, { signal: controller.signal })).finally(() =>
      clearTimeout(timer),
    );
  };
}

export function createLiveFetch(fetchImpl: typeof fetch = fetch): AppFetch {
  return withTimeout((r) => fetchImpl(r));
}

/** In-process contract mock: requests never leave the device. */
export function createMockFetch(api: MockApi): AppFetch {
  return async (request) => {
    const response = await getResponse(api.handlers, request);
    if (!response) {
      return new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'Not found' } }), {
        status: 404,
        headers: { 'content-type': 'application/json' },
      });
    }
    // HttpResponse.error() is a network failure, as fetch would report it.
    if (response.type === 'error') throw new TypeError('Network request failed');
    return response;
  };
}

export function createMockBackend(baseUrl: string, scenarios = ''): MockApi {
  const api = createMockApi({ baseUrl });
  if (scenarios) applyScenarioString(api.scenarios, scenarios, WO.rtu12m);
  return api;
}
