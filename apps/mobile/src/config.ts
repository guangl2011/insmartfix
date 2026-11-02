/**
 * Mobile runtime config. Expo inlines EXPO_PUBLIC_* at bundle time; EAS profiles set them per ring.
 * DATA_SOURCE=mock → the MSW contract mock in-process; live → FastAPI at API_BASE_URL via /me/* routes.
 */
export type DataSource = 'mock' | 'live';

export interface MobileConfig {
  dataSource: DataSource;
  apiBaseUrl: string;
  /** Crash reporting is on only when a DSN is configured (NFR-7, DSN optional). */
  sentryDsn: string | null;
  /** `MOCK_SCENARIOS` string for the contract mocks (mock data source only). */
  mockScenarios: string;
}

// Expo only inlines `process.env.EXPO_PUBLIC_*` when accessed by full name, so read them explicitly.
const bundledEnv = {
  EXPO_PUBLIC_DATA_SOURCE: process.env.EXPO_PUBLIC_DATA_SOURCE,
  EXPO_PUBLIC_API_BASE_URL: process.env.EXPO_PUBLIC_API_BASE_URL,
  EXPO_PUBLIC_SENTRY_DSN: process.env.EXPO_PUBLIC_SENTRY_DSN,
  EXPO_PUBLIC_MOCK_SCENARIOS: process.env.EXPO_PUBLIC_MOCK_SCENARIOS,
};

export function getMobileConfig(
  env: Record<string, string | undefined> = bundledEnv,
): MobileConfig {
  const raw = (env.EXPO_PUBLIC_DATA_SOURCE ?? 'mock').trim().toLowerCase();
  const dataSource: DataSource = raw === 'live' ? 'live' : 'mock';
  const apiBaseUrl = (env.EXPO_PUBLIC_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '');
  const sentryDsn = env.EXPO_PUBLIC_SENTRY_DSN?.trim() || null;
  const mockScenarios = env.EXPO_PUBLIC_MOCK_SCENARIOS?.trim() ?? '';
  return { dataSource, apiBaseUrl, sentryDsn, mockScenarios };
}
