// M3-T4 rule tests: the lint half of T-THEME-1 (status solids only in HealthScore/RiskBadge)
// and T-INBOX-2 (OfferCard: status color only on the risk line, i.e. via RiskBadge).
import { fileURLToPath } from 'node:url';
import { RuleTester } from 'eslint';
import tseslint from 'typescript-eslint';
import { describe, expect, it } from 'vitest';
import { checkCss } from '../eslint/check-css.mjs';
import plugin from '../eslint/index.mjs';
import rule from '../eslint/no-status-color.mjs';
import { STATUS_HEX, findStatusColor, isAllowedFile } from '../eslint/patterns.mjs';
import { status, STATUS_BANDS } from '../src/status';

RuleTester.describe = describe;
RuleTester.it = it;
RuleTester.itOnly = it.only;

const tester = new RuleTester({
  languageOptions: {
    parser: tseslint.parser,
    parserOptions: { ecmaFeatures: { jsx: true } },
    ecmaVersion: 2022,
    sourceType: 'module',
  },
});

const OFFER_CARD = 'apps/web/components/OfferCard.tsx';
const err = (messageId: string) => ({ messageId });

describe('T-THEME-1 status palette in the rule matches the tokens', () => {
  it('lists exactly the light + dark status values and --crit-bright', () => {
    const fromTokens = (['light', 'dark'] as const).flatMap((m) =>
      STATUS_BANDS.flatMap((b) => {
        const c = status[m][b];
        return [c.solid, c.fill, c.text].map((h) => h.slice(1).toUpperCase());
      }),
    );
    expect([...STATUS_HEX].sort()).toEqual([...fromTokens, 'FF5C5C'].sort());
  });

  it('is exposed as the insmartfix plugin', () => {
    expect(plugin.rules['no-status-color']).toBe(rule);
  });
});

describe('T-THEME-1 T-INBOX-2 insmartfix/no-status-color', () => {
  tester.run('no-status-color', rule, {
    valid: [
      // Neutral and brand tokens are fine anywhere.
      { filename: OFFER_CARD, code: "import { theme, colors } from '@insmartfix/tokens';" },
      {
        filename: OFFER_CARD,
        code: "const s = { color: 'var(--text-secondary)', fill: '#0396A6' };",
      },
      { filename: OFFER_CARD, code: 'const c = `var(--brand)`;' },
      // Lookalikes: longer hex runs and unrelated custom properties.
      { filename: OFFER_CARD, code: "const id = '#15A34A9F1';" },
      { filename: OFFER_CARD, code: "const v = 'var(--statusbar-height)';" },
      { filename: OFFER_CARD, code: "const c = 'rgb(21, 163, 75)';" },
      // The two reserved components may use status color however they like.
      {
        filename: 'packages/ui-web/src/HealthScore.tsx',
        code: "import { status } from '@insmartfix/tokens/status'; const c = '#E0A106'; const v = 'var(--status-medium)';",
      },
      {
        filename: 'apps/mobile/src/ui/RiskBadge.tsx',
        code: "import { statusColors } from '@insmartfix/tokens/status';",
      },
      { filename: 'packages/ui-web/src/RiskBadge.test.tsx', code: "const x = '#DC2626';" },
      // Custom allow-list option.
      {
        filename: 'src/Legend.tsx',
        code: "import '@insmartfix/tokens/status';",
        options: [{ allow: ['Legend'] }],
      },
    ],
    invalid: [
      // Importing the status export outside HealthScore/RiskBadge (every form).
      {
        filename: OFFER_CARD,
        code: "import { status } from '@insmartfix/tokens/status';",
        errors: [err('statusImport')],
      },
      {
        filename: OFFER_CARD,
        code: "import * as s from '../../../packages/tokens/src/status';",
        errors: [err('statusImport')],
      },
      {
        filename: OFFER_CARD,
        code: "export { status } from '@insmartfix/tokens/status';",
        errors: [err('statusImport')],
      },
      {
        filename: OFFER_CARD,
        code: "export * from '@insmartfix/tokens/status';",
        errors: [err('statusImport')],
      },
      {
        filename: OFFER_CARD,
        code: "const m = await import('@insmartfix/tokens/status');",
        errors: [err('statusImport')],
      },
      {
        filename: 'apps/mobile/app/inbox.tsx',
        code: "const { status } = require('@insmartfix/tokens/status');",
        errors: [err('statusImport')],
      },
      {
        filename: OFFER_CARD,
        code: "import { status as s, statusColors, theme } from '@insmartfix/tokens';",
        errors: [err('statusBinding'), err('statusBinding')],
      },
      // Status literals: hex (any case, with alpha), rgb(), CSS variables, templates, JSX text.
      { filename: OFFER_CARD, code: "const c = '#DC2626';", errors: [err('statusColor')] },
      { filename: OFFER_CARD, code: "const c = '#dc2626';", errors: [err('statusColor')] },
      { filename: OFFER_CARD, code: "const c = '#DC262680';", errors: [err('statusColor')] },
      {
        filename: OFFER_CARD,
        code: "const c = { borderColor: 'rgba(220, 38, 38, 0.4)' };",
        errors: [err('statusColor')],
      },
      {
        filename: OFFER_CARD,
        code: "const c = { color: 'var(--status-critical)' };",
        errors: [err('statusColor')],
      },
      {
        filename: OFFER_CARD,
        code: "const c = { '--status-high-bg': 'x' };",
        errors: [err('statusColor')],
      },
      {
        filename: OFFER_CARD,
        code: 'const c = `1px solid var(--status-high-fg)`;',
        errors: [err('statusColor')],
      },
      {
        filename: OFFER_CARD,
        code: 'const el = <style>{`.x{color:#E5661B}`}</style>;',
        errors: [err('statusColor')],
      },
      {
        filename: OFFER_CARD,
        code: 'const el = <span style={{ color: "#15A34A" }}>ok</span>;',
        errors: [err('statusColor')],
      },
      { filename: OFFER_CARD, code: 'const el = <i>#FF5C5C</i>;', errors: [err('statusColor')] },
      {
        filename: 'apps/mobile/app/jobs/[id].tsx',
        code: "const s = { backgroundColor: '#3A1515' };",
        errors: [err('statusColor')],
      },
      // The SLA countdown must never take a status color (design §7.5).
      {
        filename: 'packages/ui-web/src/SlaCountdown.tsx',
        code: "const urgent = { color: 'var(--status-critical)', fontWeight: 700 };",
        errors: [err('statusColor')],
      },
    ],
  });
});

describe('T-THEME-1 status color in stylesheets (check-css)', () => {
  const dir = fileURLToPath(new URL('./fixtures/css', import.meta.url));

  it('reports status color in ordinary stylesheets and allows HealthScore/RiskBadge', () => {
    const problems = checkCss([dir]).map((p) => ({
      file: p.file.slice(dir.length + 1),
      line: p.line,
      match: p.match,
    }));
    expect(problems).toEqual([
      { file: 'components/OfferCard.module.css', line: 2, match: '--status-high' },
      { file: 'components/OfferCard.module.css', line: 3, match: '#e0a106' },
      { file: 'globals.css', line: 2, match: 'rgb(220, 38, 38)' },
    ]);
  });

  it('finds the earliest match and recognizes allowed files', () => {
    expect(findStatusColor('a #FBE9E9 b var(--status-x)')).toMatchObject({ kind: 'hex' });
    expect(findStatusColor('var(--crit-bright) #FBE9E9')).toMatchObject({ kind: 'var' });
    expect(findStatusColor('nothing here')).toBeNull();
    expect(isAllowedFile('a/b/HealthScore.module.css')).toBe(true);
    expect(isAllowedFile('a\\b\\RiskBadge.tsx')).toBe(true);
    expect(isAllowedFile('a/b/OfferCard.tsx')).toBe(false);
    expect(isAllowedFile('')).toBe(false);
  });
});
