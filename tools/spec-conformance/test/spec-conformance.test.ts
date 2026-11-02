import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { parsePrBody, section } from '../src/body.ts';
import { evaluate, toMarkdown } from '../src/evaluate.ts';
import { documentHasId, idPattern } from '../src/ids.ts';
import { parseJestJson, parseJUnit } from '../src/results.ts';
import { classify } from '../src/scan.ts';
import { loadResults, main, run } from '../src/run.ts';

const ROOT = join(import.meta.dirname, 'fixtures/repo');
const SPEC = 'docs/specs/SPEC.md';
const PLAN = 'docs/testing/TEST_PLAN.md';

const body = (reqs: string, tests: string) => `## Summary
Mentions T-GHOST-1 and FR-99.9 outside the sections, which must be ignored.

## Requirements covered
<!-- FR/NFR IDs, e.g. FR-2.6, FR-5.3 -->
${reqs}

## Tests proving them
<!-- TEST_PLAN IDs, e.g. T-INBOX-5, T-DISP-1. All must exist and pass. -->
${tests}

## Automated gate checklist
- [x] T-AUTH-1 mentioned here is not a claim
`;

const check = (md: string) =>
  run({ root: ROOT, body: md, resultsDirs: ['results'], spec: SPEC, testPlan: PLAN });
const verdicts = (md: string) => Object.fromEntries(check(md).tests.map((t) => [t.id, t.verdict]));

describe('PR body parsing', () => {
  it('reads only the two sections and ignores template comments', () => {
    const claims = parsePrBody(body('FR-7.2, NFR-5', '- T-COMP-3\n- T-COMP-3 (core slice)'));
    expect(claims).toEqual({
      requirements: ['FR-7.2', 'NFR-5'],
      tests: ['T-COMP-3'],
      hasRequirementsSection: true,
      hasTestsSection: true,
    });
  });

  it('handles missing sections, CRLF, deeper headings and an unclosed comment', () => {
    expect(parsePrBody('just a description')).toMatchObject({
      tests: [],
      hasRequirementsSection: false,
      hasTestsSection: false,
    });
    const md =
      '# PR\r\n### Tests proving them ###\r\nT-COMP-1\r\n#### detail\r\nT-COMP-5\r\n## Next\r\nT-AUTH-1';
    expect(parsePrBody(md).tests).toEqual(['T-COMP-1', 'T-COMP-5']);
    expect(section('## Tests proving them\nT-COMP-1 <!-- T-AUTH-1', 'tests')).toBe('T-COMP-1 ');
  });
});

describe('ID matching', () => {
  it('matches JS and pytest naming but not a longer number or a prefix word', () => {
    const re = idPattern('T-AUTH-1');
    expect(re.test("it('T-AUTH-1 login')")).toBe(true);
    expect(re.test('def test_T_AUTH_1_login():')).toBe(true);
    expect(re.test('test_T_AUTH_10_jwt')).toBe(false);
    expect(re.test('XT-AUTH-1')).toBe(false);
  });

  it('finds FR, NFR and T-IDs in documents without prefix collisions', () => {
    const doc = '**FR-7.12** x | NFR-50 | T-AUTH-10 | ### FR-3 Title';
    expect(documentHasId(doc, 'FR-7.12')).toBe(true);
    expect(documentHasId(doc, 'FR-7.1')).toBe(false);
    expect(documentHasId(doc, 'NFR-5')).toBe(false);
    expect(documentHasId(doc, 'T-AUTH-1')).toBe(false);
    expect(documentHasId(doc, 'FR-3')).toBe(true);
    expect(documentHasId('FR-3.1 only', 'FR-3')).toBe(false);
  });
});

describe('result parsing', () => {
  it('reads JUnit statuses, attributes in either quote style, and XML entities', () => {
    const xml = readFileSync(join(ROOT, 'results/junit-core.xml'), 'utf8');
    expect(parseJUnit(xml, 'x').map((r) => [r.name, r.status])).toEqual([
      ['test/drafts.test.ts draft store > T-COMP-3 draft survives a reload', 'passed'],
      ['test/drafts.test.ts T-COMP-1 rejects missing failure code', 'passed'],
      ['test/drafts.test.ts T-SKIP-1 is skipped', 'skipped'],
    ]);
    const err = parseJUnit('<testcase name="a &#x41;&#66;&bogus;"><error/></testcase>', 'y');
    expect(err).toEqual([{ name: 'a AB&bogus;', status: 'failed', file: 'y' }]);
  });

  it('reads jest JSON and rejects other JSON', () => {
    const json = readFileSync(join(ROOT, 'results/jest-mobile.json'), 'utf8');
    expect(parseJestJson(json, 'j')?.map((r) => r.status)).toEqual(['passed', 'skipped']);
    expect(parseJestJson('{"total":{}}', 'c')).toBeNull();
    expect(parseJestJson('nope', 'c')).toBeNull();
    const failed = parseJestJson(
      '{"testResults":[{"assertionResults":[{"title":"t","status":"failed"},{}]}]}',
      'f',
    );
    expect(failed).toEqual([
      { name: 't', status: 'failed', file: 'f' },
      { name: '', status: 'skipped', file: 'f' },
    ]);
  });

  it('loads every results file in a directory, a single file, or nothing', () => {
    expect(loadResults([join(ROOT, 'results')])).toHaveLength(7);
    expect(loadResults([join(ROOT, 'results/junit-api.xml')])).toHaveLength(2);
    expect(loadResults([join(ROOT, 'does-not-exist')])).toEqual([]);
  });
});

describe('test source discovery', () => {
  it('classifies each runner by path', () => {
    expect(classify('apps/api/tests/test_auth.py')).toBe('pytest');
    expect(classify('apps/api/tests/conftest.py')).toBeNull();
    expect(classify('packages/core/test/drafts.test.ts')).toBe('vitest');
    expect(classify('apps/web/src/__tests__/a.tsx')).toBe('vitest');
    expect(classify('apps/mobile/src/queue.test.tsx')).toBe('jest');
    expect(classify('apps/web/e2e/nav.spec.ts')).toBe('playwright');
    expect(classify('apps/mobile/e2e/T-NAV-1.yaml')).toBe('maestro');
    expect(classify('apps/mobile/e2e/config.yaml')).toBeNull();
    expect(classify('tools/spec-conformance/test/x.test.ts')).toBeNull();
    expect(classify('README.md')).toBeNull();
  });
});

describe('conformance verdicts', () => {
  it('passes IDs whose tests passed across pytest, vitest and jest', () => {
    const r = check(body('FR-7.1, FR-7.2, NFR-5', 'T-AUTH-10, T-COMP-3, T-COMP-1, T-COMP-5'));
    expect(r.ok).toBe(true);
    expect(r.tests.every((t) => t.verdict === 'pass')).toBe(true);
    expect(r.tests.find((t) => t.id === 'T-COMP-3')?.definedIn).toEqual([
      'packages/core/test/drafts.test.ts (vitest)',
    ]);
  });

  it('fails a failed test, a skipped-only test, an unknown ID and a test nobody wrote', () => {
    const md = body('FR-7.2', 'T-INBOX-5, T-SKIP-1, T-NOPE-1, T-GHOST-1');
    expect(verdicts(md)).toEqual({
      'T-INBOX-5': 'fail',
      'T-SKIP-1': 'fail',
      'T-NOPE-1': 'fail',
      'T-GHOST-1': 'fail',
    });
    const reasons = check(md).tests.map((t) => t.reason);
    expect(reasons).toEqual([
      '1 matching test(s) failed in this run',
      'matching tests were all skipped',
      'not a TEST_PLAN §6 ID',
      'no test is named with this ID',
    ]);
  });

  it('fails a per-PR suite test that has no result in the run', () => {
    const r = run({
      root: ROOT,
      body: body('', 'T-COMP-3'),
      resultsDirs: [],
      spec: SPEC,
      testPlan: PLAN,
    });
    expect(r.ok).toBe(false);
    expect(r.tests[0]?.reason).toBe('defined in vitest but no result for it in this run');
  });

  it('defers Maestro and Playwright-only IDs to the nightly run without failing', () => {
    const r = check(body('', 'T-PHOTO-2, T-NAV-1'));
    expect(r.ok).toBe(true);
    expect(r.tests.map((t) => t.verdict)).toEqual(['deferred', 'deferred']);
  });

  it('fails requirement IDs that are not in the spec', () => {
    const r = check(body('FR-7.2, FR-7.9, NFR-12', 'T-COMP-3'));
    expect(r.ok).toBe(false);
    expect(r.missingRequirements).toEqual(['FR-7.9', 'NFR-12']);
  });

  it('tolerates docs-only and scaffold PRs that list no T-IDs', () => {
    const docs = check(body('', 'n/a (docs only)'));
    expect(docs.ok).toBe(true);
    expect(docs.notes).toContain(
      'No T-IDs listed: treated as a docs-only / scaffold / tooling PR.',
    );
    const scaffold = check(body('NFR-5', ''));
    expect(scaffold.ok).toBe(true);
    expect(scaffold.notes).toContain('Requirements listed without tests: NFR-5.');
    const bare = check('Bump a dependency.');
    expect(bare.ok).toBe(true);
    expect(bare.notes).toHaveLength(3);
  });

  it('renders a markdown summary for the job page', () => {
    const md = toMarkdown(check(body('FR-7.9', 'T-COMP-3, T-NAV-1, T-INBOX-5')));
    expect(md).toContain('**Result: FAIL**');
    expect(md).toContain('FAIL `FR-7.9` is not in the spec');
    expect(md).toContain('| T-NAV-1 | nightly |');
    expect(
      toMarkdown(
        evaluate({ claims: parsePrBody(''), spec: '', testPlan: '', sources: [], results: [] }),
      ),
    ).toContain('**Result: pass**');
  });
});

describe('CLI', () => {
  it('reads the body from a file or PR_BODY, writes the step summary and sets the exit code', () => {
    const dir = mkdtempSync(join(tmpdir(), 'spec-conf-'));
    const bodyFile = join(dir, 'body.md');
    const summary = join(dir, 'summary.md');
    writeFileSync(bodyFile, body('FR-7.2', 'T-COMP-3'));
    const out = vi.spyOn(process.stdout, 'write').mockImplementation(() => true);
    try {
      const args = ['--root', ROOT, '--spec', SPEC, '--test-plan', PLAN];
      expect(
        main([...args, '--body-file', bodyFile, '--results', 'results'], {
          GITHUB_STEP_SUMMARY: summary,
        }),
      ).toBe(0);
      expect(readFileSync(summary, 'utf8')).toContain('| T-COMP-3 | pass |');
      expect(main(args, { PR_BODY: body('', 'T-INBOX-5') })).toBe(1);
      expect(main(args, {})).toBe(0);
    } finally {
      out.mockRestore();
    }
  });
});
