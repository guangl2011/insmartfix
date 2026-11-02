import axe from 'axe-core';

/**
 * Serious/critical axe violations in jsdom (NFR-3, T-A11Y-1 component slice). jsdom has no layout
 * or computed colors, so color-contrast is covered by the tokens contrast test and by Playwright
 * in a real browser; `region` is off because components render outside page landmarks.
 */
export async function axeViolations(container: Element): Promise<string[]> {
  const results = await axe.run(container, {
    rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    resultTypes: ['violations'],
  });
  return results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(' ')).join(', ')})`);
}
