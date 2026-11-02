import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// TEST_PLAN §4: apps/web >= 75% line coverage.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('.', import.meta.url)) } },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./test/setup.ts'],
    include: ['**/*.test.{ts,tsx}'],
    exclude: ['node_modules/**', '.next/**', 'e2e/**'],
    css: false,
    coverage: {
      provider: 'v8',
      include: ['app/**/*.{ts,tsx}', 'components/**/*.{ts,tsx}', 'lib/**/*.{ts,tsx}'],
      // The root layout is an <html>/<body> shell; it is exercised by the Playwright smoke instead.
      exclude: ['app/layout.tsx', '**/*.test.{ts,tsx}'],
      reporter: ['text-summary', 'json-summary', 'lcov'],
      thresholds: { lines: 75 },
    },
  },
});
