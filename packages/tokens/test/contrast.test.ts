// WCAG contrast over every text/background pair the tokens define (supports T-THEME-1, T-A11Y-1;
// NFR-3, NFR-9). If a pair here fails, fix the role assignment, not the threshold.
import { describe, expect, it } from 'vitest';
import { AA, colors, contrastRatio, isLargeText, relativeLuminance, typeScale } from '../src/index';
import { status, STATUS_BANDS } from '../src/status';

const MODES = ['light', 'dark'] as const;
const SURFACES = ['surface0', 'surface1', 'surface2'] as const;

describe('contrast helpers', () => {
  it('match the WCAG reference values', () => {
    expect(contrastRatio('#FFFFFF', '#000000')).toBeCloseTo(21, 5);
    expect(contrastRatio('#000000', '#FFFFFF')).toBeCloseTo(21, 5);
    expect(contrastRatio('#777777', '#777777')).toBe(1);
    expect(relativeLuminance('#FFFFFF')).toBe(1);
    expect(relativeLuminance('#020202')).toBeCloseTo(0.000607, 6);
    expect(() => relativeLuminance('teal')).toThrow(/#RRGGBB/);
  });

  it('classify WCAG large text', () => {
    expect(isLargeText({ size: 24, weight: 'regular' })).toBe(true);
    expect(isLargeText({ size: 19, weight: 'bold' })).toBe(true);
    expect(isLargeText({ size: 19, weight: 'semibold' })).toBe(false);
    expect(isLargeText({ size: 18, weight: 'bold' })).toBe(false);
  });
});

describe.each(MODES)('%s mode', (mode) => {
  const c = colors(mode);

  it.each(SURFACES)('body text roles are AA (4.5:1) on %s', (surface) => {
    for (const role of ['textPrimary', 'textSecondary', 'brandText'] as const)
      expect(contrastRatio(c[role], c[surface]), role).toBeGreaterThanOrEqual(AA.text);
  });

  it.each(SURFACES)('the focus ring reaches 3:1 on %s (WCAG 1.4.11)', (surface) => {
    expect(contrastRatio(c.focusRing, c[surface])).toBeGreaterThanOrEqual(AA.nonText);
  });

  it('the primary button label is large text and ≥ 3:1 on the brand fill and pressed fill', () => {
    expect(isLargeText(typeScale.action)).toBe(true);
    expect(contrastRatio(c.onBrand, c.brand)).toBeGreaterThanOrEqual(AA.largeText);
    expect(contrastRatio(c.onBrand, c.brandPressed)).toBeGreaterThanOrEqual(AA.text);
  });

  it('text-muted is not a body-text role (below 4.5:1) — hints and disabled only', () => {
    // Guards the documented restriction: if this ever passes AA, the restriction can be lifted.
    expect(SURFACES.some((s) => contrastRatio(c.textMuted, c[s]) < AA.text)).toBe(true);
  });

  it.each(STATUS_BANDS)('status %s: pill text on fill is AA (4.5:1)', (band) => {
    const s = status[mode][band];
    expect(contrastRatio(s.text, s.fill)).toBeGreaterThanOrEqual(AA.text);
  });
});
