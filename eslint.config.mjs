// Root flat config shared by every JS/TS workspace package.
// Each package runs `eslint .`; ESLint resolves this file by walking up from the package dir.
import path from 'node:path';
import js from '@eslint/js';
import nextPlugin from '@next/eslint-plugin-next';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';
import insmartfix from './packages/tokens/eslint/index.mjs';

// NFR-4 / T-THEME-1 / T-INBOX-2: the reserved status scale (COLOR_LANGUAGE v1.3 §3) may only be
// used by the HealthScore and RiskBadge components. The rule lives with the tokens it guards
// (M3-T4); stylesheets are covered by packages/tokens/eslint/check-css.mjs in the lint scripts.
export default tseslint.config(
  {
    ignores: [
      '**/node_modules/**',
      '**/.next/**',
      '**/dist/**',
      '**/coverage/**',
      '**/.expo/**',
      '**/.turbo/**',
      '**/playwright-report/**',
      '**/test-results/**',
      'apps/api/**',
      'apps/mobile/android/**',
      'apps/mobile/ios/**',
      'packages/contracts/src/schema.d.ts',
      '**/next-env.d.ts',
      '**/expo-env.d.ts',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.node, ...globals.browser },
    },
    plugins: { 'react-hooks': reactHooks, insmartfix },
    rules: {
      ...reactHooks.configs.recommended.rules,
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      'insmartfix/no-status-color': 'error',
    },
  },
  {
    files: ['**/*.{js,cjs}'],
    languageOptions: { sourceType: 'commonjs' },
    rules: { '@typescript-eslint/no-require-imports': 'off' },
  },
  {
    files: ['apps/web/**/*.{ts,tsx}'],
    plugins: { '@next/next': nextPlugin },
    rules: {
      ...nextPlugin.configs.recommended.rules,
      ...nextPlugin.configs['core-web-vitals'].rules,
    },
    settings: { next: { rootDir: path.join(import.meta.dirname, 'apps/web') } },
  },
  {
    files: ['apps/mobile/**/*.{ts,tsx,js}'],
    languageOptions: { globals: { ...globals.jest } },
  },
  {
    // The tokens package defines the palette (and the rule's own fixtures). HealthScore.* and
    // RiskBadge.* are allowed by the rule itself.
    files: ['packages/tokens/**'],
    rules: { 'insmartfix/no-status-color': 'off' },
  },
);
