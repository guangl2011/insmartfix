/**
 * §3 Status — the reserved risk scale (COLOR_LANGUAGE v1.3). Reserved, load-bearing color:
 * import this module ONLY from the HealthScore and RiskBadge components (NFR-4, enforced by the
 * `insmartfix/no-status-color` lint rule). Always pair a band with its text label.
 *
 * Contrast rules (checked in test/contrast.test.ts):
 * - `text` on `fill` is AA body text (≥ 4.5:1) — the risk pill.
 * - `solid` is a graphic (bar, swatch, dot), not a text color: the light Medium solid is ~2:1
 *   against the surfaces, so a health number must be drawn in a text role, beside the solid.
 */
import type { ColorMode } from './color';

export type StatusBand = 'healthy' | 'medium' | 'high' | 'critical';
export type FailureRisk = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface StatusColors {
  /** Band solid: health-score bar/swatch; full-bleed CRITICAL banner with white text. */
  readonly solid: string;
  /** Risk pill background. */
  readonly fill: string;
  /** Text on the pill fill. */
  readonly text: string;
}

export const STATUS_BANDS: readonly StatusBand[] = ['healthy', 'medium', 'high', 'critical'];

export const status: Readonly<Record<ColorMode, Readonly<Record<StatusBand, StatusColors>>>> = {
  light: {
    healthy: { solid: '#15A34A', fill: '#E9F7EE', text: '#14532A' },
    medium: { solid: '#E0A106', fill: '#FBF1DB', text: '#6E4A05' },
    high: { solid: '#E5661B', fill: '#FCEBDF', text: '#77320F' },
    critical: { solid: '#DC2626', fill: '#FBE9E9', text: '#7E1D1D' },
  },
  dark: {
    healthy: { solid: '#22C55E', fill: '#123122', text: '#86EFAC' },
    medium: { solid: '#F5B942', fill: '#3A2C0C', text: '#FCD97D' },
    high: { solid: '#FB7B3C', fill: '#3A1F10', text: '#FDBA8C' },
    critical: { solid: '#F05252', fill: '#3A1515', text: '#FCA5A5' },
  },
};

/** Text labels that must accompany every band (never color alone, §3). */
export const STATUS_LABELS: Readonly<Record<StatusBand, string>> = {
  healthy: 'Healthy',
  medium: 'Medium',
  high: 'High',
  critical: 'Critical',
};

/** Health Score → band: 80–100 Healthy, 60–79 Medium, 40–59 High, < 40 Critical (§3). */
export function healthBand(score: number): StatusBand {
  if (score >= 80) return 'healthy';
  if (score >= 60) return 'medium';
  if (score >= 40) return 'high';
  return 'critical';
}

const RISK_BANDS: Readonly<Record<FailureRisk, StatusBand>> = {
  LOW: 'healthy',
  MEDIUM: 'medium',
  HIGH: 'high',
  CRITICAL: 'critical',
};

/** Failure Risk → band: LOW / MEDIUM / HIGH / CRITICAL map 1:1 (§3). */
export function riskBand(risk: FailureRisk): StatusBand {
  return RISK_BANDS[risk];
}

export function statusColors(mode: ColorMode, band: StatusBand): StatusColors {
  return status[mode][band];
}
