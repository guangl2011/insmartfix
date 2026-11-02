/**
 * Mobile theme (M5-T1): COLOR_LANGUAGE v1.3 tokens from `@insmartfix/tokens`, light by default and
 * following the device dark setting (NFR-9). Status colors are deliberately absent: only
 * `HealthScore` and `RiskBadge` import `@insmartfix/tokens/status` (NFR-4).
 */
import { getTheme, type ColorMode, type Theme, type TypeStyleName } from '@insmartfix/tokens';
import { createContext, useContext, type ReactNode } from 'react';
import { Platform, useColorScheme, type TextStyle } from 'react-native';

export type { Theme } from '@insmartfix/tokens';

const ThemeModeContext = createContext<ColorMode | null>(null);

export interface ThemeProviderProps {
  /** Forces a mode (tests, screenshots). Omit to follow the device setting. */
  mode?: ColorMode;
  children: ReactNode;
}

export function ThemeProvider({ mode, children }: ThemeProviderProps) {
  const system = useColorScheme();
  const resolved: ColorMode = mode ?? (system === 'dark' ? 'dark' : 'light');
  return <ThemeModeContext.Provider value={resolved}>{children}</ThemeModeContext.Provider>;
}

/** Light by default; follows the device dark setting (NFR-9) unless a provider forces a mode. */
export function useTheme(): Theme {
  const forced = useContext(ThemeModeContext);
  const system = useColorScheme();
  return getTheme(forced ?? (system === 'dark' ? 'dark' : 'light'));
}

/**
 * The app uses the platform's system UI face for sans/display (design §7.2 "neutral system/sans
 * stack"; no font download on cold start, NFR-1) and the platform monospace for micro-labels.
 */
const MONO = Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' });

/** RN text style for a token type style (every style is ≥ 16 pt, NFR-2). */
export function textStyle(theme: Theme, name: TypeStyleName): TextStyle {
  const t = theme.text[name];
  return {
    fontSize: t.fontSize,
    lineHeight: t.lineHeight,
    fontWeight: t.fontWeight,
    ...(name === 'mono' ? { fontFamily: MONO } : {}),
  };
}

/** Minimum hit target (NFR-2, T-ERGO-1). */
export const MIN_TARGET = 44;

/** hitSlop that grows a box of `size` pt to the 44 pt minimum. */
export function hitSlopFor(size: number) {
  const pad = Math.max(0, Math.ceil((MIN_TARGET - size) / 2));
  return { top: pad, bottom: pad, left: pad, right: pad };
}
