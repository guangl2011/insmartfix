import { appendFileSync, existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { parsePrBody } from './body.ts';
import { evaluate, toMarkdown, type Report } from './evaluate.ts';
import { parseJestJson, parseJUnit, type TestResult } from './results.ts';
import { scanTestSources } from './scan.ts';

export interface Options {
  root: string;
  body: string;
  resultsDirs: string[];
  spec: string;
  testPlan: string;
}

function files(dir: string): string[] {
  if (!existsSync(dir)) return [];
  if (statSync(dir).isFile()) return [dir];
  return readdirSync(dir, { recursive: true, withFileTypes: false })
    .map((f) => join(dir, String(f)))
    .filter((f) => statSync(f).isFile());
}

export function loadResults(dirs: string[]): TestResult[] {
  const out: TestResult[] = [];
  for (const file of dirs.flatMap(files)) {
    const text = readFileSync(file, 'utf8');
    if (file.endsWith('.xml')) out.push(...parseJUnit(text, file));
    else if (file.endsWith('.json')) out.push(...(parseJestJson(text, file) ?? []));
  }
  return out;
}

export function run(o: Options): Report {
  return evaluate({
    claims: parsePrBody(o.body),
    spec: readFileSync(resolve(o.root, o.spec), 'utf8'),
    testPlan: readFileSync(resolve(o.root, o.testPlan), 'utf8'),
    sources: scanTestSources(o.root),
    results: loadResults(o.resultsDirs.map((d) => resolve(o.root, d))),
  });
}

/** CLI entry: returns the exit code. */
export function main(argv: string[], env: Record<string, string | undefined>): number {
  const get = (flag: string) => {
    const i = argv.indexOf(flag);
    return i >= 0 ? argv[i + 1] : undefined;
  };
  const bodyFile = get('--body-file');
  const body = bodyFile ? readFileSync(bodyFile, 'utf8') : (env.PR_BODY ?? '');
  const resultsDirs = argv.flatMap((a, i) => (argv[i - 1] === '--results' ? [a] : []));
  const report = run({
    root: get('--root') ?? process.cwd(),
    body,
    resultsDirs: resultsDirs.length ? resultsDirs : ['test-results'],
    spec: get('--spec') ?? 'docs/specs/INSMARTFIX_V1_SPEC.md',
    testPlan: get('--test-plan') ?? 'docs/testing/TEST_PLAN.md',
  });
  const md = toMarkdown(report);
  process.stdout.write(md);
  if (env.GITHUB_STEP_SUMMARY) appendFileSync(env.GITHUB_STEP_SUMMARY, md);
  return report.ok ? 0 : 1;
}
