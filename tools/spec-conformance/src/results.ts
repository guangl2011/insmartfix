export type Status = 'passed' | 'failed' | 'skipped';

export interface TestResult {
  /** Full test name, including describe blocks / class name. */
  name: string;
  status: Status;
  /** Results file it came from. */
  file: string;
}

const ENTITIES: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" };

function decode(s: string): string {
  return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e: string) => {
    if (e[0] === '#') {
      const code =
        e[1]?.toLowerCase() === 'x' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      return String.fromCodePoint(code);
    }
    return ENTITIES[e] ?? m;
  });
}

function attr(tag: string, name: string): string {
  const m = new RegExp(`\\s${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)')`).exec(tag);
  return m ? decode(m[1] ?? m[2] ?? '') : '';
}

/** JUnit XML from pytest, vitest, Playwright and Maestro. */
export function parseJUnit(xml: string, file: string): TestResult[] {
  const out: TestResult[] = [];
  const re = /<testcase\b([^>]*?)(\/>|>([\s\S]*?)<\/testcase>)/g;
  for (let m = re.exec(xml); m; m = re.exec(xml)) {
    const tag = m[1]!;
    const inner = m[3] ?? '';
    const status: Status = /<(failure|error)\b/.test(inner)
      ? 'failed'
      : /<skipped\b/.test(inner)
        ? 'skipped'
        : 'passed';
    const name = [attr(tag, 'classname'), attr(tag, 'name')].filter(Boolean).join(' ');
    out.push({ name, status, file });
  }
  return out;
}

interface JestAssertion {
  fullName?: string;
  title?: string;
  ancestorTitles?: string[];
  status?: string;
}

/** Jest / vitest `--json` output. Returns null if the JSON is something else (e.g. coverage). */
export function parseJestJson(json: string, file: string): TestResult[] | null {
  let data: unknown;
  try {
    data = JSON.parse(json);
  } catch {
    return null;
  }
  const suites = (data as { testResults?: unknown }).testResults;
  if (!Array.isArray(suites)) return null;
  const out: TestResult[] = [];
  for (const suite of suites as { name?: string; assertionResults?: JestAssertion[] }[]) {
    for (const a of suite.assertionResults ?? []) {
      const name =
        a.fullName ?? [...(a.ancestorTitles ?? []), a.title ?? ''].filter(Boolean).join(' ');
      const status: Status =
        a.status === 'passed' ? 'passed' : a.status === 'failed' ? 'failed' : 'skipped';
      out.push({ name: `${suite.name ?? ''} ${name}`.trim(), status, file });
    }
  }
  return out;
}
