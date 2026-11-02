import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['test/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts', 'mocks/**/*.ts'],
      exclude: ['src/schema.d.ts'],
      reporter: ['text-summary', 'json-summary'],
    },
  },
});
