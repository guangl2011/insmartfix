/**
 * Ergonomics + color-discipline oracles over a rendered host tree (T-ERGO-1, T-THEME-1 / T-INBOX-2
 * render half). Used by every screen-state test in M5.
 */
import { StyleSheet, type TextStyle, type ViewStyle } from 'react-native';
import type { TestInstance } from 'test-renderer';
// eslint-disable-next-line insmartfix/no-status-color -- test oracle: must know the reserved hexes.
import { status } from '@insmartfix/tokens/status';

const MIN_TARGET = 44;
const MIN_BODY = 16;
const INTERACTIVE_ROLES = new Set([
  'button',
  'link',
  'checkbox',
  'switch',
  'radio',
  'tab',
  'togglebutton',
]);

const flat = (style: unknown) =>
  (StyleSheet.flatten(style as ViewStyle) ?? {}) as ViewStyle & TextStyle;

function effectiveFontSize(node: TestInstance): number | undefined {
  for (let n: TestInstance | null = node; n; n = n.parent) {
    if (n.type !== 'Text') continue;
    const size = flat(n.props.style).fontSize;
    if (size !== undefined) return size;
  }
  return undefined;
}

const hasText = (n: TestInstance) =>
  n.children.some((c) => typeof c === 'string' && c.trim() !== '');

function slop(n: TestInstance, a: 'top' | 'left', b: 'bottom' | 'right'): number {
  const s = n.props.hitSlop as
    number | Partial<Record<'top' | 'bottom' | 'left' | 'right', number>> | undefined;
  if (typeof s === 'number') return 2 * s;
  return (s?.[a] ?? 0) + (s?.[b] ?? 0);
}

const describeNode = (n: TestInstance) =>
  `${n.type}${n.props.testID ? `#${n.props.testID}` : ''}${n.props.accessibilityLabel ? ` "${n.props.accessibilityLabel}"` : ''}`;

/** Every visible text ≥ 16 pt and every interactive element ≥ 44 × 44 pt (incl. hitSlop). */
export function ergonomicsViolations(root: TestInstance): string[] {
  const out: string[] = [];
  for (const t of root.queryAll((n) => n.type === 'Text' && hasText(n))) {
    const size = effectiveFontSize(t);
    if (size === undefined || size < MIN_BODY)
      out.push(`${describeNode(t)} font ${size ?? 'default(14)'}`);
  }
  const interactive = root.queryAll(
    (n) =>
      n.type === 'TextInput' ||
      ((INTERACTIVE_ROLES.has(n.props.accessibilityRole) || INTERACTIVE_ROLES.has(n.props.role)) &&
        n.type !== 'Text'),
  );
  for (const n of interactive) {
    const s = flat(n.props.style);
    // A full-screen backdrop (absoluteFill) is as large as the screen.
    if (s.position === 'absolute' && s.top === 0 && s.bottom === 0) continue;
    const h =
      (typeof s.minHeight === 'number'
        ? s.minHeight
        : typeof s.height === 'number'
          ? s.height
          : 0) + slop(n, 'top', 'bottom');
    if (h < MIN_TARGET) out.push(`${describeNode(n)} height ${h}`);
    const w =
      typeof s.minWidth === 'number'
        ? s.minWidth
        : typeof s.width === 'number'
          ? s.width
          : undefined;
    if (w !== undefined && w + slop(n, 'left', 'right') < MIN_TARGET)
      out.push(`${describeNode(n)} width ${w}`);
  }
  return out;
}

const STATUS_HEX = new Set(
  Object.values(status).flatMap((bands) =>
    Object.values(bands).flatMap((c) => [c.solid, c.fill, c.text].map((h) => h.toUpperCase())),
  ),
);
const COLOR_KEYS = ['color', 'backgroundColor', 'borderColor', 'tintColor'] as const;

function insideAllowed(node: TestInstance): boolean {
  for (
    let f = node.unstable_fiber as { type?: unknown; return?: unknown } | null;
    f;
    f = f.return as typeof f
  ) {
    const t = f.type as { name?: string; displayName?: string } | string | undefined;
    const name =
      typeof t === 'function' || typeof t === 'object' ? (t?.displayName ?? t?.name) : undefined;
    if (name === 'HealthScore' || name === 'RiskBadge') return true;
  }
  return false;
}

/** Host nodes painted with a reserved status color outside HealthScore / RiskBadge (NFR-4). */
export function statusColorLeaks(root: TestInstance): string[] {
  const out: string[] = [];
  for (const n of root.queryAll(() => true)) {
    const s = flat(n.props.style) as Record<string, unknown>;
    for (const k of COLOR_KEYS) {
      const v = s[k];
      if (typeof v === 'string' && STATUS_HEX.has(v.toUpperCase()) && !insideAllowed(n))
        out.push(`${describeNode(n)} ${k}=${v}`);
    }
  }
  return out;
}

/** Hosts painted with a reserved status color (inside the allowed components). */
export function statusColorUses(root: TestInstance): string[] {
  const out: string[] = [];
  for (const n of root.queryAll(() => true)) {
    const s = flat(n.props.style) as Record<string, unknown>;
    for (const k of COLOR_KEYS) {
      const v = s[k];
      if (typeof v === 'string' && STATUS_HEX.has(v.toUpperCase()))
        out.push(`${describeNode(n)} ${k}=${v}`);
    }
  }
  return out;
}

/** Hosts painted with the brand fill (the "one teal per view" check counts primaries). */
export function brandFills(root: TestInstance, brand: string): TestInstance[] {
  return root.queryAll((n) => flat(n.props.style).backgroundColor === brand);
}
