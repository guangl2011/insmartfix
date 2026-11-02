/**
 * React Native theme objects (apps/mobile), light + app-dark. Status colors are deliberately not
 * part of the theme: HealthScore / RiskBadge import `@insmartfix/tokens/status` (NFR-4).
 */
import { colors, series, type ColorMode, type ModeColors } from '../src/color';
import { ergonomics, layout, radii, space } from '../src/space';
import { fontWeight, typeScale, type TypeStyleName } from '../src/type';

/** Font family names as registered with expo-font (RN has no CSS fallback stacks). */
export const rnFontFamily = {
  display: 'Space Grotesk',
  sans: 'Inter',
  mono: 'IBM Plex Mono',
} as const;

export interface RnTextStyle {
  fontFamily: string;
  fontSize: number;
  lineHeight: number;
  fontWeight: '400' | '500' | '600' | '700';
}

export interface Theme {
  mode: ColorMode;
  colors: ModeColors;
  series: readonly string[];
  text: Readonly<Record<TypeStyleName, RnTextStyle>>;
  space: typeof space;
  radii: typeof radii;
  ergonomics: typeof ergonomics;
  layout: typeof layout;
}

function rnText(): Record<TypeStyleName, RnTextStyle> {
  const out = {} as Record<TypeStyleName, RnTextStyle>;
  for (const [name, s] of Object.entries(typeScale) as [
    TypeStyleName,
    (typeof typeScale)[TypeStyleName],
  ][]) {
    out[name] = {
      fontFamily: rnFontFamily[s.family],
      fontSize: s.size,
      lineHeight: s.lineHeight,
      fontWeight: String(fontWeight[s.weight]) as RnTextStyle['fontWeight'],
    };
  }
  return out;
}

function buildTheme(mode: ColorMode): Theme {
  return {
    mode,
    colors: colors(mode),
    series: series[mode],
    text: rnText(),
    space,
    radii,
    ergonomics,
    layout,
  };
}

export const theme: Readonly<Record<ColorMode, Theme>> = {
  light: buildTheme('light'),
  dark: buildTheme('dark'),
};

/** Light is the default; dark only when the device asks for it (NFR-9). */
export function getTheme(mode: ColorMode | null | undefined): Theme {
  return mode === 'dark' ? theme.dark : theme.light;
}
