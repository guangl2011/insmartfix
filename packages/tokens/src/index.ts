/**
 * InsmartFix design tokens — derived from docs/design/COLOR_LANGUAGE.md v1.3.
 * The app uses the LIGHT register only (no navy); dark mode is the "app dark theme" (§3, §7).
 * Single source of truth: tokens.css is generated from this file (`pnpm --filter @insmartfix/tokens generate`).
 */

export type ColorMode = 'light' | 'dark';
export type StatusBand = 'healthy' | 'medium' | 'high' | 'critical';

export interface StatusColors {
  /** Big Health Score number, full-bleed CRITICAL banner. */
  solid: string;
  /** Risk pill background. */
  fill: string;
  /** Text on the pill fill. */
  text: string;
}

/** §1 Brand — cyan-teal 5-stop ramp. Primary is #0396A6 (v1.3). */
export const brand = {
  tint: '#E6F8FA',
  lite: '#5BCCD9',
  bright: '#2DD4DE',
  primary: '#0396A6',
  deep: '#026873',
} as const;

/** §2a Neutral — light register, and the app dark theme (§7 dark block). */
export const neutral = {
  light: {
    surface0: '#F4F6F8',
    surface1: '#EDF1F4',
    surface2: '#FFFFFF',
    border: '#E2E8EC',
    borderStrong: '#CBD5DC',
    textPrimary: '#0B1A24',
    textSecondary: '#54657A',
    textMuted: '#8495A6',
  },
  dark: {
    surface0: '#0D1417',
    surface1: '#1B262B',
    surface2: '#151E22',
    border: '#26333A',
    borderStrong: '#33434B',
    textPrimary: '#F1F5F7',
    textSecondary: '#9FB0B8',
    textMuted: '#6B7C84',
  },
} as const;

/** §3 Status — the reserved risk scale. Only HealthScore and RiskBadge may use these (NFR-4). */
export const status: Record<ColorMode, Record<StatusBand, StatusColors>> = {
  light: {
    healthy: { solid: '#15A34A', fill: '#E9F7EE', text: '#14532A' },
    medium: { solid: '#E0A106', fill: '#FBF1DB', text: '#6E4A05' },
    high: { solid: '#E5661B', fill: '#FCEBDF', text: '#77320F' },
    critical: { solid: '#DC2626', fill: '#FBE9E9', text: '#7E1D1D' },
  },
  dark: {
    healthy: { solid: '#22C55E', fill: '#123122', text: '#86EFAC' },
    medium: { solid: '#F5B942', fill: '#3A2C0C', text: '#FCD97D' },
    high: { solid: '#FB7B3C', fill: '#3A1F10', text: '#FDBA8C' },
    critical: { solid: '#F05252', fill: '#3A1515', text: '#FCA5A5' },
  },
};

/** §4 Data-viz — fixed-order categorical series (never status hues). */
export const series = {
  light: ['#0396A6', '#2A78D6', '#6D5AE0', '#D4537E', '#64748B', '#0E7490'],
  dark: ['#2DD4DE', '#3987E5', '#9085E9', '#E87BA4', '#94A3B8', '#22A7C4'],
} as const;

/** §6 Type + radii. */
export const fonts = {
  display: '"Space Grotesk","Inter",system-ui,sans-serif',
  sans: '"Inter",system-ui,sans-serif',
  mono: '"IBM Plex Mono","SF Mono",ui-monospace,monospace',
} as const;

export const radii = { sm: 3, md: 4, lg: 6 } as const;

/** NFR-2 field ergonomics. */
export const ergonomics = { minTapTarget: 44, minBodyFontSize: 16 } as const;

export interface Theme {
  mode: ColorMode;
  colors: {
    brand: string;
    brandDeep: string;
    brandTint: string;
    brandLite: string;
    onBrand: string;
  } & (typeof neutral)[ColorMode];
  status: Record<StatusBand, StatusColors>;
  series: readonly string[];
  radii: typeof radii;
  ergonomics: typeof ergonomics;
}

function buildTheme(mode: ColorMode): Theme {
  return {
    mode,
    colors: {
      brand: brand.primary,
      brandDeep: brand.deep,
      brandTint: brand.tint,
      brandLite: brand.lite,
      onBrand: '#FFFFFF',
      ...neutral[mode],
    },
    status: status[mode],
    series: series[mode],
    radii,
    ergonomics,
  };
}

/** React Native theme objects (apps/mobile), light + dark. */
export const theme: Record<ColorMode, Theme> = {
  light: buildTheme('light'),
  dark: buildTheme('dark'),
};

export function getTheme(mode: ColorMode | null | undefined): Theme {
  return mode === 'dark' ? theme.dark : theme.light;
}

/** CSS custom properties for one mode (names follow COLOR_LANGUAGE §7 app aliases). */
export function cssVariables(mode: ColorMode): Record<string, string> {
  const n = neutral[mode];
  const vars: Record<string, string> = {};
  if (mode === 'light') {
    Object.assign(vars, {
      '--teal-tint': brand.tint,
      '--teal-lite': brand.lite,
      '--teal-bright': brand.bright,
      '--teal': brand.primary,
      '--teal-deep': brand.deep,
      '--brand': 'var(--teal)',
      '--brand-50': brand.tint,
      '--brand-300': brand.lite,
      '--brand-400': brand.bright,
      '--brand-600': brand.primary,
      '--brand-800': brand.deep,
      '--on-brand': '#FFFFFF',
    });
  }
  Object.assign(vars, {
    '--surface-0': n.surface0,
    '--surface-1': n.surface1,
    '--surface-2': n.surface2,
    '--border': n.border,
    '--border-strong': n.borderStrong,
    '--text-primary': n.textPrimary,
    '--text-secondary': n.textSecondary,
    '--text-muted': n.textMuted,
  });
  for (const [band, c] of Object.entries(status[mode])) {
    vars[`--status-${band}`] = c.solid;
    vars[`--status-${band}-bg`] = c.fill;
    vars[`--status-${band}-fg`] = c.text;
  }
  series[mode].forEach((hex, i) => {
    vars[`--series-${i + 1}`] = hex;
  });
  if (mode === 'light') {
    Object.assign(vars, {
      '--display': fonts.display,
      '--sans': fonts.sans,
      '--mono': fonts.mono,
      '--r-sm': `${radii.sm}px`,
      '--r-md': `${radii.md}px`,
      '--r-lg': `${radii.lg}px`,
      '--tap-min': `${ergonomics.minTapTarget}px`,
    });
  }
  return vars;
}

function block(selector: string, vars: Record<string, string>, indent = ''): string {
  const body = Object.entries(vars)
    .map(([k, v]) => `${indent}  ${k}: ${v};`)
    .join('\n');
  return `${indent}${selector} {\n${body}\n${indent}}`;
}

/** Full stylesheet: light default, dark via prefers-color-scheme or an explicit data-theme. */
export function renderCss(): string {
  const dark = cssVariables('dark');
  return [
    '/* GENERATED by packages/tokens/scripts/generate-css.ts from src/index.ts — do not edit. */',
    '/* Source: docs/design/COLOR_LANGUAGE.md v1.3 (app = light register; dark = app dark theme). */',
    block(':root', cssVariables('light')),
    `@media (prefers-color-scheme: dark) {\n${block(":root:not([data-theme='light'])", dark, '  ')}\n}`,
    block(":root[data-theme='dark']", dark),
    '',
  ].join('\n\n');
}
