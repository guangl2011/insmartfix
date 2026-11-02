import { findReqIds, findTestIds } from './ids.ts';

export interface PrClaims {
  /** FR/NFR IDs under "Requirements covered". */
  requirements: string[];
  /** TEST_PLAN IDs under "Tests proving them". */
  tests: string[];
  /** Which of the two headings were present. */
  hasRequirementsSection: boolean;
  hasTestsSection: boolean;
}

/** Removes template guidance comments (`<!-- e.g. T-INBOX-5 -->`) so examples never count. */
const stripComments = (md: string) => md.replace(/<!--[\s\S]*?(?:-->|$)/g, '');

/** Text under a `#`-level heading whose title starts with `title`, up to the next heading of the same or higher level. */
export function section(md: string, title: string): string | null {
  const lines = stripComments(md).replace(/\r\n?/g, '\n').split('\n');
  const want = title.toLowerCase();
  let level = 0;
  const out: string[] = [];
  for (const line of lines) {
    const h = /^(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line);
    if (h) {
      const depth = h[1]!.length;
      if (level && depth <= level) break;
      if (!level && h[2]!.toLowerCase().startsWith(want)) {
        level = depth;
        continue;
      }
    }
    if (level) out.push(line);
  }
  return level ? out.join('\n') : null;
}

export function parsePrBody(body: string): PrClaims {
  const req = section(body, 'Requirements covered');
  const tests = section(body, 'Tests proving them');
  return {
    requirements: req === null ? [] : findReqIds(req),
    tests: tests === null ? [] : findTestIds(tests),
    hasRequirementsSection: req !== null,
    hasTestsSection: tests !== null,
  };
}
