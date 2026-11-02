import createClient, { type ClientOptions } from 'openapi-fetch';
import type { components, paths } from './schema';

export type { components, paths } from './schema';

/** Error envelope shared by every API error (spec §5). */
export type ApiError = components['schemas']['ErrorEnvelope'];

/** Typed fetch client for the InsmartFix API (`/v1`). */
export function createApiClient(baseUrl: string, options: Omit<ClientOptions, 'baseUrl'> = {}) {
  return createClient<paths>({ ...options, baseUrl: baseUrl.replace(/\/+$/, '') });
}

export type ApiClient = ReturnType<typeof createApiClient>;
