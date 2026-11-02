/**
 * Failure-risk pill (COLOR_LANGUAGE v1.3 §3). One of the two components allowed to use the
 * reserved status scale (NFR-4). Text is the band's `-fg` on its `-bg` fill (AA body contrast),
 * and the band always carries its label ("High risk").
 */
import { riskBand, STATUS_LABELS, type FailureRisk } from '@insmartfix/tokens/status';
import { cx } from './cx';

/** "Low risk" / "Medium risk" / "High risk" / "Critical risk" (same copy as mobile). */
export function riskLabel(risk: FailureRisk): string {
  const band = STATUS_LABELS[riskBand(risk)];
  return `${risk === 'LOW' ? 'Low' : band} risk`;
}

export interface RiskBadgeProps {
  risk: FailureRisk;
  className?: string;
}

export function RiskBadge({ risk, className }: RiskBadgeProps) {
  const band = riskBand(risk);
  const label = riskLabel(risk);
  return (
    <span
      data-band={band}
      className={cx('inline-flex items-center rounded-lg px-2.5 text-body-strong', className)}
      style={{ backgroundColor: `var(--status-${band}-bg)`, color: `var(--status-${band}-fg)` }}
    >
      <span className="sr-only">Failure risk: </span>
      {label}
    </span>
  );
}
