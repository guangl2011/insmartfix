/**
 * SLA countdown formatter — design §7.5, the NON-COLOR urgency system (FR-2.4, T-SLA-1).
 *
 * | Remaining              | Label        | Weight      | Glyph            |
 * |------------------------|--------------|-------------|------------------|
 * | > 5 min                | `12m left`   | regular     | ⟡                |
 * | 1–5 min                | `4m left`    | medium      | ⟡                |
 * | < 60 s                 | `45s left`   | bold        | ⟡ (subtle pulse) |
 * | past deadline          | `Expiring`   | bold        | ⟡                |
 * | server-expired         | `Expired`    | bold, muted | —                |
 *
 * Urgency is carried by label and weight only. The result has no color field on purpose: time
 * must never borrow the reserved risk scale (red is risk, not time).
 *
 * Counts round UP, so a deadline 3 min 58 s away still reads `4m left` and the label never
 * promises less time than the server grants. Past an hour, minutes roll into hours (`1h 30m left`).
 */

export const SLA_GLYPH = '⟡';

export type SlaWeight = 'regular' | 'medium' | 'bold';
export type SlaState = 'normal' | 'soon' | 'urgent' | 'expiring' | 'expired';

export interface SlaDisplay {
  /** Visible text, e.g. `4m left`. */
  label: string;
  weight: SlaWeight;
  /** `⟡`, or null once the server has expired the offer. */
  glyph: typeof SLA_GLYPH | null;
  /** Subtle pulse on the glyph under 60 s (respect prefers-reduced-motion when rendering). */
  pulse: boolean;
  /** Muted text (server-expired only). Muted is a neutral text role, never a status color. */
  muted: boolean;
  state: SlaState;
  /** Screen-reader text (NFR-3, T-A11Y-2). */
  accessibleLabel: string;
}

export interface FormatSlaOptions {
  /** The server reports the offer EXPIRED; overrides the local countdown (design §6.2 race). */
  serverExpired?: boolean;
}

const MINUTE = 60_000;
const SECOND = 1_000;

const plural = (n: number, unit: string) => `${n} ${unit}${n === 1 ? '' : 's'}`;

function minutesLabel(totalMinutes: number): { label: string; spoken: string } {
  if (totalMinutes <= 60)
    return { label: `${totalMinutes}m left`, spoken: plural(totalMinutes, 'minute') };
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  return m === 0
    ? { label: `${h}h left`, spoken: plural(h, 'hour') }
    : { label: `${h}h ${m}m left`, spoken: `${plural(h, 'hour')} ${plural(m, 'minute')}` };
}

/** Formats time remaining until `sla_deadline` (milliseconds, measured on the server clock). */
export function formatSla(remainingMs: number, options: FormatSlaOptions = {}): SlaDisplay {
  if (options.serverExpired) {
    return {
      label: 'Expired',
      weight: 'bold',
      glyph: null,
      pulse: false,
      muted: true,
      state: 'expired',
      accessibleLabel: 'Offer expired',
    };
  }
  if (!(remainingMs > 0)) {
    // Advisory until the server confirms (design §7.5). NaN lands here too.
    return {
      label: 'Expiring',
      weight: 'bold',
      glyph: SLA_GLYPH,
      pulse: false,
      muted: false,
      state: 'expiring',
      accessibleLabel: 'Offer expiring',
    };
  }
  if (remainingMs < MINUTE) {
    const s = Math.ceil(remainingMs / SECOND);
    return {
      label: `${s}s left`,
      weight: 'bold',
      glyph: SLA_GLYPH,
      pulse: true,
      muted: false,
      state: 'urgent',
      accessibleLabel: `Time to accept: ${plural(s, 'second')} left`,
    };
  }
  const { label, spoken } = minutesLabel(Math.ceil(remainingMs / MINUTE));
  const soon = remainingMs <= 5 * MINUTE;
  return {
    label,
    weight: soon ? 'medium' : 'regular',
    glyph: SLA_GLYPH,
    pulse: false,
    muted: false,
    state: soon ? 'soon' : 'normal',
    accessibleLabel: `Time to accept: ${spoken} left`,
  };
}
