// @vitest-environment node
import postcss from 'postcss';
import tailwindcss from 'tailwindcss';
import config from '../tailwind.config';

/** Compiles the app's Tailwind config over the real sources (app + ui-web kit). */
async function compile(): Promise<string> {
  const result = await postcss([tailwindcss(config)]).process(
    '@tailwind base;@tailwind utilities;',
    { from: undefined },
  );
  return result.css;
}

describe('Tailwind is wired to the tokens (M4-T1)', () => {
  it('generates kit utilities from token CSS variables, never hex or status colors', async () => {
    const css = await compile();
    expect(css).toMatch(/\.bg-brand\s*\{[^}]*background-color:\s*var\(--brand\)/);
    expect(css).toMatch(/\.text-on-brand\s*\{[^}]*color:\s*var\(--on-brand\)/);
    expect(css).toMatch(/\.text-secondary\s*\{[^}]*color:\s*var\(--text-secondary\)/);
    expect(css).toMatch(/\.min-h-tap\s*\{[^}]*min-height:\s*44px/);
    expect(css).toMatch(/\.text-action\s*\{[^}]*font-size:\s*19px[^}]*font-weight:\s*700/);
    // Utilities never carry status color; only HealthScore/RiskBadge inline var(--status-*).
    // (The variable prefix is assembled so this assertion isn't itself a status-color literal.)
    const utilities = css.slice(css.indexOf('.bg-brand'));
    expect(utilities).not.toContain(['--status', ''].join('-'));
  }, 30_000);

  it('has no default palette or sub-16 px text sizes', async () => {
    const css = await compile();
    expect(css).not.toMatch(/\.bg-red-500|\.text-sm\b|\.text-xs\b/);
  }, 30_000);
});
