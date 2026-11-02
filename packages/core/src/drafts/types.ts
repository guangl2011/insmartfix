/** A part line in the completion form (FR-7.1). */
export interface DraftPart {
  part_code?: string;
  description: string;
  qty: number;
}

/**
 * A photo attached in the form. `local_id` names the platform's stored file or blob; `photo_id`
 * is set once the upload has been confirmed by the server.
 */
export interface DraftPhoto {
  local_id: string;
  photo_id?: string;
}

/**
 * The completion form as the contractor is filling it in (FR-7.1). Fields are nullable because a
 * draft is saved on every change, long before it is valid; `validateCompletion` decides that.
 */
export interface CompletionDraft {
  failure_code: string | null;
  actual_fault_matched: boolean | null;
  parts_used: DraftPart[];
  labor_hours: number | null;
  notes: string;
  technician_id: string;
  photos: DraftPhoto[];
}

export function emptyCompletionDraft(technicianId = ''): CompletionDraft {
  return {
    failure_code: null,
    actual_fault_matched: null,
    parts_used: [],
    labor_hours: null,
    notes: '',
    technician_id: technicianId,
    photos: [],
  };
}
