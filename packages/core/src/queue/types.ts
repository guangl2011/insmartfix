import type { CompletionReport } from '../completion/types';

/** `POST /workorders/{wo}/complete` success body (fields core reads). */
export interface CompletionResult {
  calibration_label: string;
  record_updated: true;
}

/**
 * The app's HTTP layer for queued work. Implementations throw on failure; an error with a numeric
 * `status` is an HTTP response, anything else (no `status`) is a network error or timeout.
 */
export interface QueueTransport {
  uploadPhoto(req: {
    woId: string;
    localId: string;
    idempotencyKey: string;
  }): Promise<{ photo_id: string }>;
  complete(req: {
    woId: string;
    body: CompletionReport;
    idempotencyKey: string;
  }): Promise<CompletionResult>;
}

export interface QueueError {
  /** HTTP status, absent for network errors. */
  status?: number;
  /** Error envelope code, e.g. `ALREADY_COMPLETED`. */
  code?: string;
  message: string;
}

interface ItemBase {
  id: string;
  woId: string;
  /** Generated once at enqueue and reused for every retry (FR-7.4, D12). */
  idempotencyKey: string;
  /** `dead`: rejected with a non-retryable 4xx; kept for the UI until retried or discarded. */
  status: 'pending' | 'dead';
  attempts: number;
  /** Epoch ms before which the item is not retried (backoff). */
  nextAttemptAt: number;
  createdAt: number;
  lastError?: QueueError;
}

export interface PhotoUploadItem extends ItemBase {
  kind: 'photo_upload';
  /** The platform's handle to the resized file / blob. */
  localId: string;
}

export interface CompleteItem extends ItemBase {
  kind: 'complete';
  report: Omit<CompletionReport, 'photo_ids'>;
  /** Draft photos in order; each resolves to a server photo id before the body is built. */
  photoLocalIds: string[];
  /** Server ids already known at enqueue (photos uploaded earlier). */
  knownPhotoIds: Record<string, string>;
  /**
   * The exact body sent on the first attempt. Every retry resends it unchanged with the same key,
   * so the queue can never trigger `422 IDEMPOTENCY_KEY_REUSED`.
   */
  body?: CompletionReport;
}

export type QueueItem = PhotoUploadItem | CompleteItem;

export type QueueEvent =
  | { type: 'changed'; items: QueueItem[] }
  | { type: 'photo_uploaded'; woId: string; localId: string; photoId: string }
  | { type: 'completed'; woId: string; result: CompletionResult }
  | { type: 'dead'; item: QueueItem }
  | { type: 'auth_required' }
  | { type: 'error'; error: unknown };
