// Patterns for the reserved status scale (COLOR_LANGUAGE v1.3 §3, light + app-dark, plus the
// on-navy critical). Shared by the ESLint rule and the CSS checker. test/no-status-color.test.ts
// asserts STATUS_HEX equals the values in src/status.ts, so the two cannot drift.

/** @type {readonly string[]} */
export const STATUS_HEX = [
  // light: solid, fill, text-on-fill
  '15A34A',
  'E9F7EE',
  '14532A',
  'E0A106',
  'FBF1DB',
  '6E4A05',
  'E5661B',
  'FCEBDF',
  '77320F',
  'DC2626',
  'FBE9E9',
  '7E1D1D',
  // app dark
  '22C55E',
  '123122',
  '86EFAC',
  'F5B942',
  '3A2C0C',
  'FCD97D',
  'FB7B3C',
  '3A1F10',
  'FDBA8C',
  'F05252',
  '3A1515',
  'FCA5A5',
  // --crit-bright (critical on navy)
  'FF5C5C',
];

/** Component names (file basename before the first dot) allowed to use status color. */
export const ALLOWED_COMPONENTS = ['HealthScore', 'RiskBadge'];

/** Module specifiers that resolve to the status tokens. */
export const STATUS_MODULE =
  /^@insmartfix\/tokens\/status$|(^|\/)tokens\/src\/status(\.[cm]?[jt]s)?$/;

const rgb = (hex) => [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16)).join('\\s*,\\s*');

const PATTERNS = [
  // #RRGGBB, optionally with an alpha pair (#RRGGBBAA), not followed by more hex digits.
  { kind: 'hex', re: new RegExp(`#(?:${STATUS_HEX.join('|')})(?:[0-9a-f]{2})?(?![0-9a-f])`, 'i') },
  // rgb()/rgba() spelling of the same colors.
  { kind: 'rgb', re: new RegExp(`rgba?\\(\\s*(?:${STATUS_HEX.map(rgb).join('|')})\\s*[,)/]`, 'i') },
  // The CSS custom properties (var(--status-*), style keys, --crit-bright).
  { kind: 'var', re: /--(?:status-[a-z0-9-]*|crit-bright)/i },
];

/**
 * First reserved status color reference in a piece of text, or null.
 * @param {string} text
 * @returns {{ kind: 'hex' | 'rgb' | 'var', match: string, index: number } | null}
 */
export function findStatusColor(text) {
  let best = null;
  for (const { kind, re } of PATTERNS) {
    const m = re.exec(text);
    if (m && (best === null || m.index < best.index)) best = { kind, match: m[0], index: m.index };
  }
  return best;
}

/**
 * Whether a file may reference status color: HealthScore.* / RiskBadge.* (any extension,
 * including HealthScore.module.css and HealthScore.test.tsx).
 * @param {string} filename
 * @param {readonly string[]} [allowed]
 */
export function isAllowedFile(filename, allowed = ALLOWED_COMPONENTS) {
  const base = filename.split(/[\\/]/).pop() ?? '';
  return allowed.includes(base.split('.')[0] ?? '');
}
