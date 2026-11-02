/**
 * Mobile crash reporting (NFR-7). Off unless a Sentry-compatible DSN is configured. No PII: no
 * default PII, and no request bodies or headers (the bearer token) are ever attached.
 */
import * as Sentry from '@sentry/react-native';

export interface CrashReportingOptions {
  dsn: string | null;
  environment?: string;
}

export function initCrashReporting({ dsn, environment }: CrashReportingOptions): boolean {
  if (!dsn) return false;
  Sentry.init({
    dsn,
    environment,
    sendDefaultPii: false,
    beforeBreadcrumb: (crumb) => {
      // URLs can carry work-order ids; keep the method and status only.
      if (crumb.category === 'fetch' || crumb.category === 'xhr') {
        const { method, status_code } = (crumb.data ?? {}) as Record<string, unknown>;
        return { ...crumb, data: { method, status_code } };
      }
      return crumb;
    },
  });
  return true;
}
