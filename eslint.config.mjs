// Root flat config shared by every JS/TS workspace package.
// Each package runs `eslint .`; ESLint resolves this file by walking up from the package dir.
import path from 'node:path';
import js from '@eslint/js';
import nextPlugin from '@next/eslint-plugin-next';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

// NFR-4 / T-THEME-1: the reserved status scale (COLOR_LANGUAGE v1.3 §3, light + dark) may only
// appear in packages/tokens and in the HealthScore / RiskBadge components.
const STATUS_HEX = [
  '15A34A',
  'E9F7EE',
  '14532A',
  'E0A106',
  'FBF1DB',
  '6E4A05',
  'E5661B',
  'FCEBDF',
  '77320F',
  'DC2626',
  'FBE9E9',
  '7E1D1D',
  '22C55E',
  '123122',
  '86EFAC',
  'F5B942',
  '3A2C0C',
  'FCD97D',
  'FB7B3C',
  '3A1F10',
  'FDBA8C',
  'F05252',
  '3A1515',
  'FCA5A5',
  'FF5C5C',
];
const statusHexPattern = `/#(${STATUS_HEX.join('|')})\\b/i`;
const statusColorRule = [
  'error',
  {
    selector: `Literal[value=${statusHexPattern}]`,
    message:
      'Status colors are reserved for HealthScore/RiskBadge (NFR-4). Use a token role instead.',
  },
  {
    selector: `TemplateElement[value.raw=${statusHexPattern}]`,
    message:
      'Status colors are reserved for HealthScore/RiskBadge (NFR-4). Use a token role instead.',
  },
  {
    selector: 'Literal[value=/var\\(--status-/]',
    message: 'Status tokens are reserved for HealthScore/RiskBadge (NFR-4).',
  },
];

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
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      'no-restricted-syntax': statusColorRule,
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
    // The only places allowed to reference status colors directly.
    files: ['packages/tokens/**', '**/HealthScore.*', '**/RiskBadge.*'],
    rules: { 'no-restricted-syntax': 'off' },
  },
);
