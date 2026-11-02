/**
 * Wire shapes from the §5 contract that core needs. Kept structural so core stays dependency-free;
 * `test/contract-compat.test.ts` pins them to the generated `@insmartfix/contracts` types.
 */

/** `GET /failure-codes` item. */
export interface FailureCode {
  code: string;
  subtype: string;
  component_group: string;
  label: string;
}

export interface PartUsed {
  part_code?: string | null;
  description: string;
  qty: number;
}

/** `POST /workorders/{wo}/complete` body. */
export interface CompletionReport {
  failure_code: string;
  actual_fault_matched: boolean;
  parts_used: PartUsed[];
  labor_hours: number;
  notes?: string | null;
  technician_id: string;
  photo_ids: string[];
}
