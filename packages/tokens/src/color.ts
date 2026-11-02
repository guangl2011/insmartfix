/**
 * Color tokens — docs/design/COLOR_LANGUAGE.md v1.3, app register only.
 * The app is the LIGHT register; dark mode is the "app dark theme" (§3, §7), never the navy
 * marketing register. The reserved status scale is NOT here: it lives in `@insmartfix/tokens/status`
 * so the `insmartfix/no-status-color` lint rule can confine it to HealthScore / RiskBadge (NFR-4).
 */

export type ColorMode = 'light' | 'dark';

/** §1 Brand — cyan-teal 5-stop ramp. Primary is #0396A6 (v1.3, spec D5). */
export const brand = {
  tint: '#E6F8FA',
  lite: '#5BCCD9',
  bright: '#2DD4DE',
  primary: '#0396A6',
  deep: '#026873',
} as const;

/** §2a Neutral — the light register and the app dark theme (§7 dark block). */
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

/**
 * Brand roles per mode. Values are only stops from §1; the choice per role follows §10:
 * - `brand` fills the single primary button (flat teal, never the gradient). White on it is
 *   3.5:1, so its label must use the large `action` type style (see type.ts).
 * - `brandText` is teal used as text (links, inline accents): `--teal-deep` on light (§10), and
 *   `--teal-bright` on the dark ground, where teal steps up to stay legible (§1, §9).
 * - `focusRing` must reach 3:1 against every surface (WCAG 1.4.11).
 */
export const brandRoles = {
  light: {
    brand: brand.primary,
    brandPressed: brand.deep,
    onBrand: '#FFFFFF',
    brandText: brand.deep,
    focusRing: brand.primary,
  },
  dark: {
    brand: brand.primary,
    brandPressed: brand.deep,
    onBrand: '#FFFFFF',
    brandText: brand.bright,
    focusRing: brand.bright,
  },
} as const;

/** §4 Data-viz — fixed-order categorical series (never status hues). */
export const series = {
  light: ['#0396A6', '#2A78D6', '#6D5AE0', '#D4537E', '#64748B', '#0E7490'],
  dark: ['#2DD4DE', '#3987E5', '#9085E9', '#E87BA4', '#94A3B8', '#22A7C4'],
} as const;

export type NeutralColors = { readonly [K in keyof (typeof neutral)['light']]: string };
export type BrandRoleColors = { readonly [K in keyof (typeof brandRoles)['light']]: string };
export type ModeColors = NeutralColors & BrandRoleColors;

/** Every non-status color role for one mode (what screens may use). */
export function colors(mode: ColorMode): ModeColors {
  return { ...neutral[mode], ...brandRoles[mode] };
}
