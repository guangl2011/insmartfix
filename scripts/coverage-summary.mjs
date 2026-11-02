// Collects coverage/coverage-summary.json from every JS workspace package (vitest + jest both
// write it via the json-summary reporter) and prints a Markdown table for the CI job summary.
// Thresholds themselves are enforced inside each package's test config (TEST_PLAN §4).
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const root = new URL('..', import.meta.url).pathname;
const THRESHOLDS = {
  '@insmartfix/core': 'lines >= 95%, branches >= 90%',
  '@insmartfix/tokens': 'lines >= 95%, branches >= 90%',
  '@insmartfix/web': 'lines >= 75%',
  '@insmartfix/mobile': 'lines >= 75%',
};

const rows = [];
for (const group of ['apps', 'packages']) {
  for (const dir of readdirSync(join(root, group))) {
    const pkgDir = join(root, group, dir);
    const summary = join(pkgDir, 'coverage', 'coverage-summary.json');
    if (!existsSync(summary) || !existsSync(join(pkgDir, 'package.json'))) continue;
    const { name } = JSON.parse(readFileSync(join(pkgDir, 'package.json'), 'utf8'));
    const { total } = JSON.parse(readFileSync(summary, 'utf8'));
    rows.push(
      `| \`${name}\` | ${total.lines.pct}% | ${total.branches.pct}% | ${THRESHOLDS[name] ?? '—'} |`,
    );
  }
}

console.log('### JS coverage (TEST_PLAN §4)\n');
console.log('| Package | Lines | Branches | Enforced threshold |');
console.log('|---|---|---|---|');
console.log(rows.length ? rows.join('\n') : '| (no coverage reports found) | | | |');
