#!/usr/bin/env node
/**
 * Spec-conformance gate (DEVELOPMENT_PROCESS §2 step 5, plan M1-T10).
 *
 *   node tools/spec-conformance/check.ts --body-file pr.md --results test-results [--results more]
 *
 * Reads the PR body's "Requirements covered" and "Tests proving them" sections. Every FR/NFR ID
 * must exist in the spec. Every T-ID must be a TEST_PLAN ID, be the name of a real test (pytest,
 * vitest, jest, Playwright or Maestro), and have passed in this run's JUnit / jest-JSON results.
 * IDs that only exist in suites per-PR CI doesn't run (Maestro, non-smoke Playwright) are
 * reported as "nightly". A body with no T-IDs (docs-only, scaffold) passes with a note.
 */
import { main } from './src/run.ts';

process.exitCode = main(process.argv.slice(2), process.env);
