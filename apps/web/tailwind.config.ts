import uiWebPreset from '@insmartfix/ui-web/tailwind-preset';
import type { Config } from 'tailwindcss';

/**
 * Tailwind wired to @insmartfix/tokens through the ui-web preset (M4-T1). Colors are token CSS
 * variables (light + app-dark), the type scale is ≥ 16 px only, and there is no status color.
 */
const config: Config = {
  presets: [uiWebPreset as Partial<Config>],
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
    '../../packages/ui-web/src/**/*.{ts,tsx}',
  ],
  darkMode: 'media',
};

export default config;
