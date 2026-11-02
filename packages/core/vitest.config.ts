import { defineConfig } from 'vitest/config';

// TEST_PLAN §4: packages/core >= 95% lines, >= 90% branches.
export default defineConfig({
  test: {
    include: ['test/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/**'],
      reporter: ['text-summary', 'json-summary', 'lcov'],
      thresholds: { lines: 95, branches: 90 },
    },
  },
});
