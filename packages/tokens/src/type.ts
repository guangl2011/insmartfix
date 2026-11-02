/**
 * Type tokens — COLOR_LANGUAGE v1.3 §6 faces; sizes per NFR-2 (body ≥ 16 px) and design §7.
 * Every style is ≥ 16 px so no screen text drops under the field-legibility floor (T-ERGO-1).
 */

export const fonts = {
  display: '"Space Grotesk","Inter",system-ui,sans-serif',
  sans: '"Inter",system-ui,sans-serif',
  mono: '"IBM Plex Mono","SF Mono",ui-monospace,monospace',
} as const;

/** Font weights. The SLA countdown maps regular / medium / bold onto these (design §7.5). */
export const fontWeight = { regular: 400, medium: 500, semibold: 600, bold: 700 } as const;
export type FontWeightName = keyof typeof fontWeight;

export interface TypeStyle {
  readonly family: keyof typeof fonts;
  /** px (web) / dp (RN). */
  readonly size: number;
  readonly lineHeight: number;
  readonly weight: FontWeightName;
}

export const typeScale = {
  /** Secondary metadata (site, timestamps). Still ≥ 16 px. */
  caption: { family: 'sans', size: 16, lineHeight: 22, weight: 'regular' },
  body: { family: 'sans', size: 16, lineHeight: 24, weight: 'regular' },
  bodyStrong: { family: 'sans', size: 16, lineHeight: 24, weight: 'semibold' },
  /** SLA countdown and codes; the weight varies with urgency (design §7.5). */
  mono: { family: 'mono', size: 16, lineHeight: 24, weight: 'regular' },
  /**
   * Button labels. 19 px bold is WCAG "large text" (≥ 14 pt bold), which is what makes white on
   * the brand fill (3.5:1) compliant. Do not shrink it or lighten it.
   */
  action: { family: 'sans', size: 19, lineHeight: 24, weight: 'bold' },
  title: { family: 'sans', size: 20, lineHeight: 28, weight: 'semibold' },
  headline: { family: 'display', size: 24, lineHeight: 30, weight: 'bold' },
  display: { family: 'display', size: 28, lineHeight: 34, weight: 'bold' },
} as const satisfies Record<string, TypeStyle>;

export type TypeStyleName = keyof typeof typeScale;

/** WCAG large text: ≥ 24 px, or ≥ 18.66 px (14 pt) at bold weight. */
export function isLargeText(style: Pick<TypeStyle, 'size' | 'weight'>): boolean {
  return style.size >= 24 || (style.size >= 18.66 && fontWeight[style.weight] >= 700);
}
