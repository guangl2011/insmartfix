import type { PrClaims } from './body.ts';
import { documentHasId, idPattern } from './ids.ts';
import type { TestResult } from './results.ts';
import { PER_PR_RUNNERS, type Runner, type TestSource } from './scan.ts';

export type Verdict = 'pass' | 'deferred' | 'fail';

export interface IdReport {
  id: string;
  verdict: Verdict;
  definedIn: string[];
  passed: number;
  failed: number;
  skipped: number;
  reason: string;
}

export interface Report {
  ok: boolean;
  tests: IdReport[];
  missingRequirements: string[];
  notes: string[];
}

export interface Inputs {
  claims: PrClaims;
  spec: string;
  testPlan: string;
  sources: TestSource[];
  results: TestResult[];
}

function judge(
  id: string,
  testPlan: string,
  sources: TestSource[],
  results: TestResult[],
): IdReport {
  const re = idPattern(id);
  const defs = sources.filter((s) => re.test(s.text));
  const runners = new Set<Runner>(defs.map((d) => d.runner));
  const hits = results.filter((r) => re.test(r.name));
  const count = (s: TestResult['status']) => hits.filter((h) => h.status === s).length;
  const r = {
    id,
    definedIn: defs.map((d) => `${d.path} (${d.runner})`),
    passed: count('passed'),
    failed: count('failed'),
    skipped: count('skipped'),
  };
  const fail = (reason: string): IdReport => ({ ...r, verdict: 'fail', reason });
  if (!documentHasId(testPlan, id)) return fail('not a TEST_PLAN §6 ID');
  if (r.failed) return fail(`${r.failed} matching test(s) failed in this run`);
  if (r.passed) return { ...r, verdict: 'pass', reason: `${r.passed} matching test(s) passed` };
  if (!defs.length && !hits.length) return fail('no test is named with this ID');
  const perPr = [...runners].filter((x) => PER_PR_RUNNERS.has(x));
  if (perPr.length || hits.length) {
    return fail(
      hits.length
        ? 'matching tests were all skipped'
        : `defined in ${perPr.join('/')} but no result for it in this run`,
    );
  }
  return {
    ...r,
    verdict: 'deferred',
    reason: `only in ${[...runners].join('/')} (not run per PR; proven by the nightly run)`,
  };
}

export function evaluate({ claims, spec, testPlan, sources, results }: Inputs): Report {
  const notes: string[] = [];
  if (!claims.hasRequirementsSection) notes.push('No "Requirements covered" section.');
  if (!claims.hasTestsSection) notes.push('No "Tests proving them" section.');
  if (!claims.tests.length) {
    notes.push('No T-IDs listed: treated as a docs-only / scaffold / tooling PR.');
  }
  if (claims.requirements.length && !claims.tests.length) {
    notes.push(`Requirements listed without tests: ${claims.requirements.join(', ')}.`);
  }
  const missingRequirements = claims.requirements.filter((id) => !documentHasId(spec, id));
  const tests = claims.tests.map((id) => judge(id, testPlan, sources, results));
  const ok = !missingRequirements.length && tests.every((t) => t.verdict !== 'fail');
  return { ok, tests, missingRequirements, notes };
}

const ICON: Record<Verdict, string> = { pass: 'pass', deferred: 'nightly', fail: 'FAIL' };

export function toMarkdown(report: Report): string {
  const lines = ['### Spec conformance (DEVELOPMENT_PROCESS §2 step 5)', ''];
  lines.push(report.ok ? '**Result: pass**' : '**Result: FAIL**', '');
  for (const n of report.notes) lines.push(`- ${n}`);
  for (const id of report.missingRequirements) lines.push(`- FAIL \`${id}\` is not in the spec`);
  if (report.notes.length || report.missingRequirements.length) lines.push('');
  if (report.tests.length) {
    lines.push('| Test ID | Verdict | Passed | Failed | Skipped | Why | Defined in |');
    lines.push('|---|---|---|---|---|---|---|');
    for (const t of report.tests) {
      const where = t.definedIn.join('<br>') || '—';
      lines.push(
        `| ${t.id} | ${ICON[t.verdict]} | ${t.passed} | ${t.failed} | ${t.skipped} | ${t.reason} | ${where} |`,
      );
    }
  }
  return `${lines.join('\n')}\n`;
}
