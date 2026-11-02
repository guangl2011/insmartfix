export type { components, operations, paths } from './schema';
export { createApiClient, type ApiClient, type ApiClientOptions } from './client';
export {
  ApiRequestError,
  apiErrorInfo,
  isApiError,
  unwrap,
  type ApiError,
  type ApiErrorEnvelope,
  type ApiErrorInfo,
  type ApiErrorOf,
  type ErrorCode,
  type FetchResult,
  type OfferUnavailableReason,
} from './errors';
export {
  IDEMPOTENCY_HEADER,
  IDEMPOTENCY_KEY_PATTERN,
  idempotencyHeader,
  isValidIdempotencyKey,
  newIdempotencyKey,
} from './idempotency';

import type { components } from './schema';
type S = components['schemas'];
/** Convenience aliases for the §5 models. */
export type OfferSummary = S['OfferSummary'];
export type WorkOrderDetail = S['WorkOrderDetail'];
export type OwnerWorkOrderDetail = S['OwnerWorkOrderDetail'];
export type ScheduleResponse = S['ScheduleResponse'];
export type CompletionReport = S['CompletionReport'];
export type CompletionResponse = S['CompletionResponse'];
export type FailureCode = S['FailureCode'];
export type TransitionRequest = S['TransitionRequest'];
export type TransitionResponse = S['TransitionResponse'];
export type DeclineRequest = S['DeclineRequest'];
export type MeResponse = S['MeResponse'];
export type LoginResponse = S['LoginResponse'];
export type LifecycleStage = S['LifecycleStage'];
export type DispatchState = S['DispatchState'];
