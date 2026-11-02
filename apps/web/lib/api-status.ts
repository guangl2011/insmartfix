import { createApiClient } from '@insmartfix/contracts';
import type { ServerConfig } from './config';

export type ApiStatus = 'mock' | 'reachable' | 'unreachable';

/** Server-side probe of GET /v1/healthz. Never called from the browser (spec §4.2). */
export async function probeApi(
  config: ServerConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<ApiStatus> {
  if (config.dataSource === 'mock') return 'mock';
  try {
    const client = createApiClient(config.apiBaseUrl, { fetch: fetchImpl });
    const { data } = await client.GET('/v1/healthz', {
      cache: 'no-store',
      signal: AbortSignal.timeout(2000),
    });
    return data?.status === 'ok' ? 'reachable' : 'unreachable';
  } catch {
    return 'unreachable';
  }
}
