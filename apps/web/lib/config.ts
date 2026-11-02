/**
 * Server-side runtime config — env vars only (TEST_PLAN §3).
 * DATA_SOURCE=mock → the UI talks to the MSW contract mock (M4); live → FastAPI at API_BASE_URL.
 */
export type DataSource = 'mock' | 'live';

export interface ServerConfig {
  dataSource: DataSource;
  apiBaseUrl: string;
}

export function getServerConfig(env: NodeJS.ProcessEnv = process.env): ServerConfig {
  const raw = (env.DATA_SOURCE ?? 'live').trim().toLowerCase();
  if (raw !== 'mock' && raw !== 'live') {
    throw new Error(`DATA_SOURCE must be "mock" or "live", got "${raw}"`);
  }
  const apiBaseUrl = (env.API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '');
  return { dataSource: raw, apiBaseUrl };
}
