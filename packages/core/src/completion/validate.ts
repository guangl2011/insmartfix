import type { CompletionDraft } from '../drafts/types';
import type { CompletionReport, FailureCode } from './types';

/** FR-7.1 bounds, matching the API's CompletionReport model (D10 M-8). */
export const COMPLETION_LIMITS = {
  failureCodeMax: 64,
  laborMin: 0, // exclusive
  laborMax: 24,
  laborStep: 0.25,
  notesMax: 4000,
  photosMax: 4,
  technicianMax: 120,
  partsMax: 50,
  partCodeMax: 64,
  partDescriptionMax: 200,
  qtyMin: 1,
  qtyMax: 999,
} as const;

export type CompletionErrorCode =
  'required' | 'unknown_code' | 'out_of_range' | 'step' | 'too_long' | 'too_many';

export interface FieldError {
  code: CompletionErrorCode;
  /** Copy shown under the field; identical on web and mobile. */
  message: string;
}

/**
 * Keys are form field names; part rows use `parts_used.{i}.description` / `.qty` / `.part_code`.
 */
export type CompletionErrors = Record<string, FieldError>;

export interface ValidationResult {
  valid: boolean;
  errors: CompletionErrors;
}

const L = COMPLETION_LIMITS;

const isQuarterStep = (h: number) => Math.abs(h / L.laborStep - Math.round(h / L.laborStep)) < 1e-9;

/**
 * Field-level validation of a draft (FR-7.1). `catalog` is the WO's failure-code list; when it is
 * empty (not loaded yet, e.g. offline) the code is only checked for presence and length.
 */
export function validateCompletion(
  draft: CompletionDraft,
  catalog: readonly FailureCode[] = [],
): ValidationResult {
  const errors: CompletionErrors = {};
  const put = (field: string, code: CompletionErrorCode, message: string) => {
    errors[field] ??= { code, message };
  };

  const code = draft.failure_code?.trim() ?? '';
  if (!code) put('failure_code', 'required', 'Choose the failure code you found.');
  else if (code.length > L.failureCodeMax)
    put('failure_code', 'too_long', 'That code is too long.');
  else if (catalog.length && !catalog.some((c) => c.code === code)) {
    put('failure_code', 'unknown_code', 'Choose a code from the list.');
  }

  if (typeof draft.actual_fault_matched !== 'boolean') {
    put('actual_fault_matched', 'required', 'Say whether the fault matched the brief.');
  }

  const h = draft.labor_hours;
  if (h === null || h === undefined || Number.isNaN(h)) {
    put('labor_hours', 'required', 'Enter labor hours.');
  } else if (!(h > L.laborMin && h <= L.laborMax)) {
    put('labor_hours', 'out_of_range', 'Labor must be more than 0 and at most 24 hours.');
  } else if (!isQuarterStep(h)) {
    put('labor_hours', 'step', 'Use quarter hours (0.25, 0.5, 0.75 …).');
  }

  if (draft.notes.length > L.notesMax) {
    put('notes', 'too_long', `Notes can be up to ${L.notesMax} characters.`);
  }

  if (!draft.technician_id.trim()) put('technician_id', 'required', 'Enter who did the work.');
  else if (draft.technician_id.trim().length > L.technicianMax) {
    put('technician_id', 'too_long', `Up to ${L.technicianMax} characters.`);
  }

  if (draft.photos.length > L.photosMax) {
    put('photos', 'too_many', `Attach up to ${L.photosMax} photos.`);
  }

  if (draft.parts_used.length > L.partsMax) {
    put('parts_used', 'too_many', `Up to ${L.partsMax} parts.`);
  }
  draft.parts_used.forEach((p, i) => {
    const at = `parts_used.${i}`;
    const desc = p.description.trim();
    if (!desc) put(`${at}.description`, 'required', 'Describe the part.');
    else if (desc.length > L.partDescriptionMax) {
      put(`${at}.description`, 'too_long', `Up to ${L.partDescriptionMax} characters.`);
    }
    if (!Number.isInteger(p.qty) || p.qty < L.qtyMin || p.qty > L.qtyMax) {
      put(`${at}.qty`, 'out_of_range', `Quantity must be a whole number from 1 to ${L.qtyMax}.`);
    }
    if ((p.part_code?.trim().length ?? 0) > L.partCodeMax) {
      put(`${at}.part_code`, 'too_long', `Up to ${L.partCodeMax} characters.`);
    }
  });

  return { valid: Object.keys(errors).length === 0, errors };
}

/**
 * The request body for a valid draft. `photoIds` are the server ids of the draft's photos, in
 * order (the offline queue supplies them once the uploads have finished).
 */
export function toCompletionReport(
  draft: CompletionDraft,
  photoIds: readonly string[],
): CompletionReport {
  const result = validateCompletion(draft);
  if (!result.valid) {
    throw new Error(`Invalid completion draft: ${Object.keys(result.errors).join(', ')}`);
  }
  const notes = draft.notes.trim();
  return {
    failure_code: draft.failure_code!.trim(),
    actual_fault_matched: draft.actual_fault_matched!,
    parts_used: draft.parts_used.map((p) => {
      const partCode = p.part_code?.trim();
      return {
        ...(partCode ? { part_code: partCode } : {}),
        description: p.description.trim(),
        qty: p.qty,
      };
    }),
    labor_hours: draft.labor_hours!,
    ...(notes ? { notes } : {}),
    technician_id: draft.technician_id.trim(),
    photo_ids: [...photoIds],
  };
}
