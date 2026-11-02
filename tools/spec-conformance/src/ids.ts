/** Requirement IDs (FR-7.2, NFR-5) and TEST_PLAN IDs (T-COMP-3). */
export const T_ID = /\bT-[A-Z][A-Z0-9]*-\d+\b/g;
export const REQ_ID = /\b(?:FR-\d+(?:\.\d+)?|NFR-\d+)\b/g;

const unique = (xs: Iterable<string>) => [...new Set(xs)];

export const findTestIds = (text: string) => unique(text.match(T_ID) ?? []);
export const findReqIds = (text: string) => unique(text.match(REQ_ID) ?? []);

/**
 * Matches a T-ID inside a test name in any of the naming styles TEST_PLAN allows:
 * `T-COMP-3 ...` (JS, Maestro) and `test_T_COMP_3_...` (pytest). `T-COMP-1` never matches
 * `T-COMP-10`.
 */
export function idPattern(id: string): RegExp {
  const parts = id.split('-').map((p) => p.replace(/[^A-Za-z0-9]/g, ''));
  return new RegExp(`(?<![A-Za-z0-9])${parts.join('[-_]')}(?![0-9])`);
}

/** True if the ID token occurs in a document (spec, TEST_PLAN). */
export function documentHasId(doc: string, id: string): boolean {
  const escaped = id.replace(/[.]/g, '\\.');
  return new RegExp(`(?<![A-Za-z0-9.-])${escaped}(?![0-9]|\\.\\d)`).test(doc);
}
