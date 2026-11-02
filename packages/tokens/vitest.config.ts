import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['test/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/**', 'build/**'],
      reporter: ['text-summary', 'json-summary', 'lcov'],
      thresholds: { lines: 95, branches: 90 },
    },
  },
});
