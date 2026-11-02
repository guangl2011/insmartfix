import { readdirSync, readFileSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

export type Runner = 'pytest' | 'vitest' | 'jest' | 'playwright' | 'maestro';

/** Suites per-PR CI runs in full; an ID defined only in the others is proven by the nightly run. */
export const PER_PR_RUNNERS: ReadonlySet<Runner> = new Set(['pytest', 'vitest', 'jest']);

export interface TestSource {
  path: string;
  runner: Runner;
  text: string;
}

const SKIP_DIRS = new Set([
  'node_modules',
  '.git',
  '.venv',
  '.next',
  '.turbo',
  'coverage',
  'dist',
  'build',
  'test-results',
  'playwright-report',
]);

/** Which runner owns a repo-relative file, or null if it is not a test source. */
export function classify(path: string): Runner | null {
  const p = path.split(sep).join('/');
  // This tool's own self-tests quote sample IDs; they never prove a requirement.
  if (p.startsWith('tools/spec-conformance/')) return null;
  if (/^apps\/mobile\/e2e\/.+\.ya?ml$/.test(p))
    return p.endsWith('/config.yaml') ? null : 'maestro';
  if (/^apps\/web\/e2e\/.+\.(spec|test)\.[cm]?[jt]sx?$/.test(p)) return 'playwright';
  if (/(^|\/)(test_[^/]*|[^/]*_test)\.py$/.test(p)) return 'pytest';
  if (/\.(test|spec)\.[cm]?[jt]sx?$/.test(p) || /\/__tests__\/.+\.[cm]?[jt]sx?$/.test(p)) {
    return p.startsWith('apps/mobile/') ? 'jest' : 'vitest';
  }
  return null;
}

export function scanTestSources(root: string): TestSource[] {
  const out: TestSource[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) {
        if (!SKIP_DIRS.has(entry.name)) walk(full);
        continue;
      }
      const path = relative(root, full).split(sep).join('/');
      const runner = classify(path);
      if (runner) out.push({ path, runner, text: `${path}\n${readFileSync(full, 'utf8')}` });
    }
  };
  walk(root);
  return out;
}
