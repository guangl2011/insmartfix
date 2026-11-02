/** Spacing, radii and field-ergonomics tokens (NFR-2, COLOR_LANGUAGE v1.3 §6 radii). */

/** 4 px grid. */
export const space = {
  0: 0,
  1: 4,
  2: 8,
  3: 12,
  4: 16,
  5: 20,
  6: 24,
  8: 32,
  10: 40,
  12: 48,
} as const;
export type SpaceStep = keyof typeof space;

/** Small, technical radii (§6). */
export const radii = { sm: 3, md: 4, lg: 6 } as const;

/** NFR-2: tap targets ≥ 44×44 pt; body text ≥ 16 px. */
export const ergonomics = { minTapTarget: 44, minBodyFontSize: 16 } as const;

/** The 44 pt minimum tap target (NFR-2, T-ERGO-1). */
export const MIN_TAP_TARGET = ergonomics.minTapTarget;

/** Single-column field layout and the sticky bottom action bar (FR-3.7). */
export const layout = {
  maxContentWidth: 640,
  gutter: space[4],
  /** Sticky bar = one 48 px primary button + vertical padding. */
  actionBarHeight: 72,
  primaryButtonHeight: 48,
} as const;
