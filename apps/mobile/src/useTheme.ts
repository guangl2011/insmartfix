import { getTheme, type Theme } from '@insmartfix/tokens';
import { useColorScheme } from 'react-native';

/** Light by default; follows the device dark setting (NFR-9). */
export function useTheme(): Theme {
  return getTheme(useColorScheme() === 'dark' ? 'dark' : 'light');
}
