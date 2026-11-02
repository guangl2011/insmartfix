/**
 * Typed error-envelope parsing (spec §5): `{"error": {"code", "message", "reason?"}, "server_time"}`.
 * Clients branch on `code`, never on `message` (which is user-facing text).
 */
import type { components } from './schema';

export type ErrorCode = components['schemas']['ErrorCode'];
export type OfferUnavailableReason = components['schemas']['OfferUnavailableReason'];
export type ApiErrorEnvelope = components['schemas']['ErrorEnvelope'];
/** @deprecated M0 name; use ApiErrorEnvelope. */
export type ApiError = ApiErrorEnvelope;

/** A non-2xx response, thrown by {@link unwrap}. `code` is null when the body was not an envelope. */
export class ApiRequestError<C extends ErrorCode = ErrorCode> extends Error {
  override readonly name = 'ApiRequestError';
  readonly status: number;
  readonly code: C | null;
  readonly reason: OfferUnavailableReason | null;
  readonly serverTime: string | null;
  /** The parsed body (envelope, text or undefined). */
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    const env = isEnvelope(body) ? body : null;
    super(env?.error.message ?? `HTTP ${status}`);
    this.status = status;
    this.code = (env?.error.code as C | undefined) ?? null;
    this.reason = env?.error.reason ?? null;
    this.serverTime = env?.server_time ?? null;
    this.body = body;
  }
}

function isEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false;
  const err = (value as { error: unknown }).error;
  return (
    typeof err === 'object' &&
    err !== null &&
    typeof (err as { code?: unknown }).code === 'string' &&
    typeof (err as { message?: unknown }).message === 'string'
  );
}

export type ApiErrorOf<C extends ErrorCode> =
  (ApiErrorEnvelope & { error: { code: C } }) | ApiRequestError<C>;

/**
 * True when `value` is an API error (the `error` from an openapi-fetch result, or a thrown
 * {@link ApiRequestError}), optionally with a specific code: `isApiError(e, 'OFFER_UNAVAILABLE')`.
 */
export function isApiError<C extends ErrorCode = ErrorCode>(
  value: unknown,
  code?: C,
): value is ApiErrorOf<C> {
  if (value instanceof ApiRequestError)
    return code === undefined ? value.code !== null : value.code === code;
  return isEnvelope(value) && (code === undefined || value.error.code === code);
}

export interface ApiErrorInfo {
  code: ErrorCode | null;
  message: string | null;
  reason: OfferUnavailableReason | null;
}

/** Normalizes either error form (or anything else) to `{code, message, reason}`. */
export function apiErrorInfo(value: unknown): ApiErrorInfo {
  if (value instanceof ApiRequestError)
    return { code: value.code, message: value.code ? value.message : null, reason: value.reason };
  if (isEnvelope(value))
    return {
      code: value.error.code,
      message: value.error.message,
      reason: value.error.reason ?? null,
    };
  return { code: null, message: null, reason: null };
}

/** The shape every openapi-fetch call resolves to. */
export interface FetchResult<D, E> {
  data?: D;
  error?: E;
  response: Response;
}

/** Returns `data` for a 2xx result, otherwise throws {@link ApiRequestError}. */
export function unwrap<D, E>(result: FetchResult<D, E>): D {
  if (result.error !== undefined || !result.response.ok)
    throw new ApiRequestError(result.response.status, result.error);
  return result.data as D;
}
