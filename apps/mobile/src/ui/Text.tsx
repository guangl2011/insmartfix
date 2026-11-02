import type { TypeStyleName } from '@insmartfix/tokens';
import type { ReactNode } from 'react';
import { Text as RNText, type TextProps as RNTextProps } from 'react-native';
import { textStyle, useTheme } from '../theme';

export type TextTone = 'primary' | 'secondary' | 'muted' | 'brand';

export interface AppTextProps extends Omit<RNTextProps, 'children'> {
  variant?: TypeStyleName;
  tone?: TextTone;
  children?: ReactNode;
}

/** Text in a token type style (all ≥ 16 pt, NFR-2) and a neutral or brand-text role. */
export function AppText({ variant = 'body', tone = 'primary', style, ...rest }: AppTextProps) {
  const theme = useTheme();
  const c = theme.colors;
  const color =
    tone === 'secondary'
      ? c.textSecondary
      : tone === 'muted'
        ? c.textMuted
        : tone === 'brand'
          ? c.brandText
          : c.textPrimary;
  return <RNText {...rest} style={[textStyle(theme, variant), { color }, style]} />;
}
