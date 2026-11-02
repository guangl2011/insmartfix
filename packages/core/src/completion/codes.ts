import type { FailureCode } from './types';

export interface FailureCodeOption extends FailureCode {
  /** True for the engine's predicted code, offered first. */
  predicted: boolean;
  /** Picker text: "Confirm: {label}" for the prediction, else the label. */
  display: string;
}

const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

const matches = (c: FailureCode, terms: string[]) => {
  const hay = fold(`${c.code} ${c.label} ${c.component_group}`);
  return terms.every((t) => hay.includes(t));
};

/**
 * Picker options (FR-7.1): codes for the asset's subtype, the predicted code first as
 * "Confirm: …", then the rest in catalog order. `query` filters by code, label or component
 * group (every word must match; case and accents ignored). A predicted code outside the subtype
 * or not in the catalog is not offered.
 */
export function orderFailureCodes(
  codes: readonly FailureCode[],
  predicted: string | null | undefined,
  subtype: string | null | undefined,
  query = '',
): FailureCodeOption[] {
  const terms = fold(query).split(/\s+/).filter(Boolean);
  const seen = new Set<string>();
  const inScope = codes.filter((c) => {
    if ((subtype && c.subtype !== subtype) || seen.has(c.code)) return false;
    seen.add(c.code);
    return matches(c, terms);
  });
  const first = inScope.find((c) => c.code === predicted);
  const rest = inScope.filter((c) => c !== first);
  return [
    ...(first ? [{ ...first, predicted: true, display: `Confirm: ${first.label}` }] : []),
    ...rest.map((c) => ({ ...c, predicted: false, display: c.label })),
  ];
}
