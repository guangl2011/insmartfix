// Contract drift check (spec §5, TEST_PLAN §2 "Contract"): regenerate openapi.json from the API
// and the TS types from openapi.json, then fail if either differs from what is committed.
import { execSync } from 'node:child_process';

const run = (cmd) => execSync(cmd, { stdio: 'inherit' });
run('pnpm run generate');
try {
  run('git diff --exit-code -- openapi.json src/schema.d.ts');
} catch {
  console.error(
    '\nContract drift: packages/contracts is out of date with apps/api.\n' +
      'Run `make contracts` and commit the result.',
  );
  process.exit(1);
}
console.log('contracts: no drift');
