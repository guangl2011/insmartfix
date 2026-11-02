#!/usr/bin/env node
// CSS half of insmartfix/no-status-color: ESLint doesn't read stylesheets, so this scans
// *.css / *.scss under the given directories (default: cwd) for status hex, rgb() and
// --status-* / --crit-bright references outside HealthScore.* / RiskBadge.* files.
// Usage (a package's lint script): `eslint . && node ../../packages/tokens/eslint/check-css.mjs .`
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { pathToFileURL } from 'node:url';
import { findStatusColor, isAllowedFile } from './patterns.mjs';

const SKIP_DIRS = new Set(['node_modules', '.next', 'dist', 'coverage', '.turbo', '.expo']);

/** @param {string} dir @returns {string[]} */
function stylesheets(dir) {
  const out = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.isDirectory()) {
      if (!SKIP_DIRS.has(e.name)) out.push(...stylesheets(join(dir, e.name)));
    } else if (/\.s?css$/.test(e.name)) out.push(join(dir, e.name));
  }
  return out;
}

/**
 * @param {string[]} dirs
 * @returns {{ file: string, line: number, match: string }[]}
 */
export function checkCss(dirs) {
  const problems = [];
  for (const dir of dirs) {
    for (const file of stylesheets(dir)) {
      if (isAllowedFile(file)) continue;
      readFileSync(file, 'utf8')
        .split('\n')
        .forEach((text, i) => {
          const hit = findStatusColor(text);
          if (hit) problems.push({ file, line: i + 1, match: hit.match });
        });
    }
  }
  return problems;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  const dirs = process.argv.slice(2);
  const problems = checkCss(dirs.length ? dirs : ['.']);
  for (const p of problems)
    console.error(
      `${relative(process.cwd(), p.file)}:${p.line}  error  Status color '${p.match}' is reserved for HealthScore/RiskBadge (NFR-4)  insmartfix/no-status-color`,
    );
  if (problems.length) process.exit(1);
}
