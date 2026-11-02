import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import * as tokens from '../src/index';
import {
  brand,
  brandRoles,
  colors,
  cssVariables,
  getTheme,
  MIN_TAP_TARGET,
  neutral,
  renderCss,
  series,
  theme,
  typeScale,
} from '../src/index';
import {
  healthBand,
  riskBand,
  status,
  STATUS_BANDS,
  STATUS_LABELS,
  statusColors,
  type StatusBand,
} from '../src/status';

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

/** `--name:#HEX` pairs from a §7 CSS block (light = :root, dark = the media query). */
function docCss(kind: 'light' | 'dark'): Record<string, string> {
  const css = doc.slice(doc.indexOf('```css'), doc.indexOf('```', doc.indexOf('```css') + 6));
  const dark = css.indexOf('@media (prefers-color-scheme: dark)');
  const part = kind === 'light' ? css.slice(0, dark) : css.slice(dark);
  return Object.fromEntries(
    [...part.matchAll(/(--[a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})/g)].map((m) => [m[1]!, m[2]!]),
  );
}

describe('tokens match COLOR_LANGUAGE v1.3', () => {
  it('brand primary is #0396A6 (D5) and the doc agrees', () => {
    expect(brand.primary).toBe('#0396A6');
    expect(doc).toMatch(/`--teal`\*\*\s*\|\s*\*\*`#0396A6`\*\*/);
    expect(theme.light.colors.brand).toBe('#0396A6');
    expect(theme.dark.colors.brand).toBe('#0396A6');
    expect(cssVariables('light')['--brand']).toBe('#0396A6');
  });

  it.each(['light', 'dark'] as const)('%s status hex values match the doc §3 table', (mode) => {
    const table = statusTable(mode);
    expect(Object.keys(table).sort()).toEqual(['critical', 'healthy', 'high', 'medium']);
    for (const band of Object.keys(table) as StatusBand[]) {
      const c = status[mode][band];
      expect([c.solid, c.fill, c.text], `${mode} ${band}`).toEqual(table[band]);
    }
  });

  it.each(['light', 'dark'] as const)(
    '%s CSS variables equal every app variable the doc §7 block declares',
    (mode) => {
      const ours = cssVariables(mode);
      const theirs = docCss(mode);
      // Marketing-only navy register and on-navy critical are intentionally not app tokens (§5).
      const appOnly = Object.entries(theirs).filter(
        ([k]) => !/^--(navy|accent-band|crit-bright|bg|card|line|ink)/.test(k),
      );
      expect(appOnly.length).toBeGreaterThan(20);
      for (const [k, v] of appOnly) expect(ours[k], k).toBe(v);
    },
  );

  it('every token hex appears in the doc (no invented colors)', () => {
    const docHex = new Set([...doc.matchAll(/#[0-9A-Fa-f]{6}/g)].map((m) => m[0].toUpperCase()));
    for (const mode of ['light', 'dark'] as const) {
      for (const v of Object.values(cssVariables(mode))) {
        if (/^#[0-9A-F]{6}$/i.test(v) && v !== '#FFFFFF')
          expect(docHex, v).toContain(v.toUpperCase());
      }
    }
  });

  it('keeps the navy marketing register out of the app', () => {
    const css = renderCss();
    for (const navy of ['#0C1420', '#111E2E', '#16263A', '--navy', '--accent-band'])
      expect(css).not.toContain(navy);
  });
});

describe('status is a separate export (NFR-4)', () => {
  it('is not reachable from the main entry point or the theme objects', () => {
    expect(Object.keys(tokens)).not.toContain('status');
    expect(Object.keys(tokens).some((k) => /status/i.test(k))).toBe(false);
    for (const mode of ['light', 'dark'] as const) {
      expect(theme[mode]).not.toHaveProperty('status');
      const all = JSON.stringify(theme[mode]).toUpperCase();
      for (const band of STATUS_BANDS) {
        const c = status[mode][band];
        for (const hex of [c.solid, c.fill, c.text]) expect(all).not.toContain(hex);
      }
    }
  });

  it('maps health scores and risk levels to bands with labels (§3)', () => {
    expect([100, 80, 79, 60, 59, 40, 39, 0].map(healthBand)).toEqual([
      'healthy',
      'healthy',
      'medium',
      'medium',
      'high',
      'high',
      'critical',
      'critical',
    ]);
    expect((['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] as const).map(riskBand)).toEqual(STATUS_BANDS);
    expect(STATUS_BANDS.map((b) => STATUS_LABELS[b])).toEqual([
      'Healthy',
      'Medium',
      'High',
      'Critical',
    ]);
    expect(statusColors('dark', 'critical')).toBe(status.dark.critical);
  });
});

describe('theme objects (RN)', () => {
  it('light is the default; dark follows the device (NFR-9)', () => {
    expect(getTheme('dark').colors.surface0).toBe('#0D1417');
    expect(getTheme('light').colors.surface0).toBe('#F4F6F8');
    expect(getTheme(null).mode).toBe('light');
    expect(getTheme(undefined).mode).toBe('light');
    expect(theme.dark.colors).toEqual(colors('dark'));
    expect(theme.light.colors).toEqual({ ...neutral.light, ...brandRoles.light });
    expect(theme.dark.series).toBe(series.dark);
  });

  it('carries RN text styles built from the type scale', () => {
    expect(theme.light.text.body).toEqual({
      fontFamily: 'Inter',
      fontSize: 16,
      lineHeight: 24,
      fontWeight: '400',
    });
    expect(theme.light.text.action.fontWeight).toBe('700');
    expect(theme.light.text.mono.fontFamily).toBe('IBM Plex Mono');
  });

  it('enforces NFR-2 ergonomics minimums (supports T-ERGO-1)', () => {
    expect(MIN_TAP_TARGET).toBeGreaterThanOrEqual(44);
    expect(theme.light.ergonomics.minTapTarget).toBe(MIN_TAP_TARGET);
    expect(theme.light.ergonomics.minBodyFontSize).toBeGreaterThanOrEqual(16);
    for (const [name, s] of Object.entries(typeScale))
      expect(s.size, name).toBeGreaterThanOrEqual(16);
    expect(theme.light.layout.primaryButtonHeight).toBeGreaterThanOrEqual(MIN_TAP_TARGET);
  });
});

describe('tokens.css', () => {
  it('is up to date with build/css.ts (run `pnpm --filter @insmartfix/tokens generate`)', () => {
    const css = readFileSync(fileURLToPath(new URL('../tokens.css', import.meta.url)), 'utf8');
    expect(css).toBe(renderCss());
  });

  it('declares light defaults and app-dark overrides, honoring an explicit data-theme', () => {
    const css = renderCss();
    expect(css).toContain('--brand-600: #0396A6;');
    expect(css).toContain('--type-body-size: 16px;');
    expect(css).toContain('--tap-min: 44px;');
    expect(css).toMatch(
      /@media \(prefers-color-scheme: dark\) \{\n {2}:root:not\(\[data-theme='light'\]\) \{[^}]*--surface-0: #0D1417;/,
    );
    expect(css).toMatch(/:root\[data-theme='dark'\] \{[^}]*--status-critical: #F05252;/);
    expect(cssVariables('dark')['--brand-text']).toBe(brand.bright);
    expect(cssVariables('light')['--brand-text']).toBe(brand.deep);
  });
});
