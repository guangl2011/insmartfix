/**
 * Tailwind preset generated from `@insmartfix/tokens` (COLOR_LANGUAGE v1.3, NFR-2, NFR-4, NFR-9).
 *
 * - Colors are the token CSS variables, so light / app-dark switch with the device setting and
 *   no hex is ever written in a component. Tailwind's default palette is replaced, not extended:
 *   `bg-red-500` and friends don't exist here.
 * - The reserved status scale is deliberately absent. Only HealthScore and RiskBadge may use it,
 *   via `var(--status-*)` (enforced by `insmartfix/no-status-color`).
 * - Font sizes are the token type scale only (every step ≥ 16 px, NFR-2), so `text-sm` and
 *   `text-xs` don't exist either.
 * - `tap` (44 px) sizes tap targets: `min-h-tap min-w-tap` (NFR-2, T-ERGO-1).
 */
import {
  brandRoles,
  ergonomics,
  fontWeight,
  layout,
  neutral,
  radii,
  typeScale,
} from '@insmartfix/tokens';

const kebab = (s: string) => s.replace(/[A-Z0-9]+/g, (m) => `-${m.toLowerCase()}`);
const varsOf = (keys: readonly string[]) =>
  Object.fromEntries(keys.map((k) => [kebab(k), `var(--${kebab(k)})`]));

/** Token color roles → `bg-surface-2`, `text-text-secondary`, `bg-brand`, `text-brand-text` … */
export const presetColors: Record<string, string> = {
  transparent: 'transparent',
  current: 'currentColor',
  inherit: 'inherit',
  ...varsOf(Object.keys(neutral.light)),
  ...varsOf(Object.keys(brandRoles.light)),
};

/** Type scale → `text-body`, `text-action` (19 px bold, the brand-button label), `text-title` … */
export const presetFontSizes: Record<string, [string, { lineHeight: string; fontWeight: string }]> =
  Object.fromEntries(
    Object.entries(typeScale).map(([name, s]) => [
      kebab(name),
      [
        `${s.size}px`,
        { lineHeight: `${s.lineHeight}px`, fontWeight: String(fontWeight[s.weight]) },
      ],
    ]),
  );

const px = (n: number) => `${n}px`;

export const uiWebPreset = {
  theme: {
    colors: presetColors,
    fontSize: presetFontSizes,
    fontFamily: { display: 'var(--display)', sans: 'var(--sans)', mono: 'var(--mono)' },
    borderRadius: {
      none: '0',
      sm: px(radii.sm),
      md: px(radii.md),
      DEFAULT: px(radii.lg),
      lg: px(radii.lg),
      full: '9999px',
    },
    extend: {
      // Short text aliases: `text-primary`, `text-secondary`, `text-muted` (muted = disabled or
      // decorative only: it is below 4.5:1). Teal text is `text-brand-text`, never `text-brand`.
      textColor: {
        primary: 'var(--text-primary)',
        secondary: 'var(--text-secondary)',
        muted: 'var(--text-muted)',
      },
      minHeight: { tap: px(ergonomics.minTapTarget), button: px(layout.primaryButtonHeight) },
      minWidth: { tap: px(ergonomics.minTapTarget) },
      height: { tap: px(ergonomics.minTapTarget), 'action-bar': px(layout.actionBarHeight) },
      width: { tap: px(ergonomics.minTapTarget) },
      maxWidth: { content: px(layout.maxContentWidth) },
      outlineColor: { focus: 'var(--focus-ring)' },
      ringColor: { focus: 'var(--focus-ring)' },
    },
  },
};

export default uiWebPreset;
