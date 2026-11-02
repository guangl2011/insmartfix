import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  brand,
  cssVariables,
  getTheme,
  renderCss,
  status,
  theme,
  type StatusBand,
} from '../src/index';

const doc = readFileSync(
  fileURLToPath(new URL('../../../docs/design/COLOR_LANGUAGE.md', import.meta.url)),
  'utf8',
);
const BANDS: Record<string, StatusBand> = {
  Healthy: 'healthy',
  Medium: 'medium',
  High: 'high',
  Critical: 'critical',
};
const hexes = (line: string) =>
  [...line.matchAll(/`(#[0-9A-Fa-f]{6})`/g)].map((m) => m[1]!.toUpperCase());

/** Rows of the §3 status tables, keyed by band: light rows have a bolded band name and 3 hex cells. */
function statusTable(kind: 'light' | 'dark'): Record<StatusBand, string[]> {
  const out = {} as Record<StatusBand, string[]>;
  const section = doc.slice(doc.indexOf('## 3 · Status'), doc.indexOf('## 4 · Data-viz'));
  const darkStart = section.indexOf('Light-mode dark');
  const part = kind === 'light' ? section.slice(0, darkStart) : section.slice(darkStart);
  for (const line of part.split('\n')) {
    const m = /^\|\s*\**(Healthy|Medium|High|Critical)\**\s*\|/.exec(line);
    if (m) out[BANDS[m[1]!]!] = hexes(line);
  }
  return out;
}

describe('tokens match COLOR_LANGUAGE v1.3', () => {
  it('brand primary is #0396A6 (D5) and the doc agrees', () => {
    expect(brand.primary).toBe('#0396A6');
    expect(doc).toMatch(/`--teal`\*\*\s*\|\s*\*\*`#0396A6`\*\*/);
    expect(theme.light.colors.brand).toBe('#0396A6');
  });

  it.each(['light', 'dark'] as const)('%s status hex values match the doc §3 table', (mode) => {
    const table = statusTable(mode);
    expect(Object.keys(table).sort()).toEqual(['critical', 'healthy', 'high', 'medium']);
    for (const band of Object.keys(table) as StatusBand[]) {
      const c = status[mode][band];
      expect([c.solid, c.fill, c.text], `${mode} ${band}`).toEqual(table[band]);
    }
  });

  it('every token hex appears in the doc (no invented colors)', () => {
    const docHex = new Set(
      hexes(doc).concat([...doc.matchAll(/#[0-9A-Fa-f]{6}/g)].map((m) => m[0].toUpperCase())),
    );
    for (const mode of ['light', 'dark'] as const) {
      for (const v of Object.values(cssVariables(mode))) {
        if (/^#[0-9A-F]{6}$/i.test(v) && v !== '#FFFFFF')
          expect(docHex, v).toContain(v.toUpperCase());
      }
    }
  });
});

describe('theme objects', () => {
  it('light and dark differ only where the doc says', () => {
    expect(getTheme('dark').colors.surface0).toBe('#0D1417');
    expect(getTheme('light').colors.surface0).toBe('#F4F6F8');
    expect(getTheme(null).mode).toBe('light');
    expect(getTheme(undefined).mode).toBe('light');
    expect(theme.dark.colors.brand).toBe(theme.light.colors.brand);
  });

  it('enforces NFR-2 ergonomics minimums', () => {
    expect(theme.light.ergonomics.minTapTarget).toBeGreaterThanOrEqual(44);
    expect(theme.light.ergonomics.minBodyFontSize).toBeGreaterThanOrEqual(16);
  });
});

describe('tokens.css', () => {
  it('is up to date with src/index.ts (run `pnpm --filter @insmartfix/tokens generate`)', () => {
    const css = readFileSync(fileURLToPath(new URL('../tokens.css', import.meta.url)), 'utf8');
    expect(css).toBe(renderCss());
  });

  it('declares light defaults and dark overrides', () => {
    const css = renderCss();
    expect(css).toContain('--brand-600: #0396A6;');
    expect(css).toContain('@media (prefers-color-scheme: dark)');
    expect(css).toContain('--status-critical: #F05252;');
  });
});
