import { brandRoles, neutral, typeScale } from '@insmartfix/tokens';
import { presetColors, presetFontSizes, uiWebPreset } from '../src/tailwind-preset';

describe('Tailwind preset from tokens (NFR-2, NFR-4, NFR-9)', () => {
  it('maps every neutral and brand role to its CSS variable (light/dark follow the device)', () => {
    expect(presetColors['surface-0']).toBe('var(--surface-0)');
    expect(presetColors['text-secondary']).toBe('var(--text-secondary)');
    expect(presetColors['brand']).toBe('var(--brand)');
    expect(presetColors['brand-text']).toBe('var(--brand-text)');
    expect(presetColors['on-brand']).toBe('var(--on-brand)');
    const roles = Object.keys(neutral.light).length + Object.keys(brandRoles.light).length;
    expect(Object.keys(presetColors)).toHaveLength(roles + 3);
  });

  it('contains no status color and no hex at all (status is HealthScore/RiskBadge only)', () => {
    const json = JSON.stringify(uiWebPreset);
    expect(json).not.toMatch(/status/i);
    expect(json).not.toMatch(/#[0-9a-f]{3,8}\b/i);
  });

  it('replaces the font-size scale with the token type scale, all ≥ 16 px', () => {
    expect(Object.keys(presetFontSizes)).toEqual(
      Object.keys(typeScale).map((k) => k.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)),
    );
    for (const [size] of Object.values(presetFontSizes))
      expect(parseInt(size, 10)).toBeGreaterThanOrEqual(16);
    expect(presetFontSizes['action']).toEqual(['19px', { lineHeight: '24px', fontWeight: '700' }]);
    expect(presetFontSizes).not.toHaveProperty('sm');
  });

  it('T-ERGO-1 (web primitives): exposes the 44 px tap target', () => {
    expect(uiWebPreset.theme.extend.minHeight.tap).toBe('44px');
    expect(uiWebPreset.theme.extend.minWidth.tap).toBe('44px');
    expect(uiWebPreset.theme.extend.minHeight.button).toBe('48px');
  });
});
