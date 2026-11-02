/**
 * Health score (0–100) with its band (COLOR_LANGUAGE v1.3 §3). One of the two components allowed
 * to use the reserved status scale (NFR-4). The band solid is drawn as a bar beside the number;
 * the number and the band label are neutral text roles (the light Medium solid is ~2:1, so it is
 * never a text color), and the band is never shown by color alone.
 */
import { healthBand, STATUS_LABELS } from '@insmartfix/tokens/status';
import { cx } from './cx';

export interface HealthScoreProps {
  score: number;
  /** `inline` for the offer-card risk line; `full` adds the band label and a meter (detail). */
  size?: 'inline' | 'full';
  className?: string;
}

export function HealthScore({ score, size = 'inline', className }: HealthScoreProps) {
  const value = Math.max(0, Math.min(100, Math.round(score)));
  const band = healthBand(value);
  const label = STATUS_LABELS[band];
  return (
    <span
      role="img"
      aria-label={`Health score ${value} of 100, ${label}`}
      data-band={band}
      className={cx('inline-flex items-center gap-2', className)}
    >
      <span
        aria-hidden="true"
        data-testid="health-band"
        className={cx('inline-block rounded-sm', size === 'full' ? 'h-6 w-2' : 'h-4 w-1.5')}
        style={{ backgroundColor: `var(--status-${band})` }}
      />
      <span aria-hidden="true" className="text-body-strong text-primary">
        Health {value}
      </span>
      {size === 'full' ? (
        <span aria-hidden="true" className="text-body text-secondary">
          {label}
        </span>
      ) : null}
    </span>
  );
}
