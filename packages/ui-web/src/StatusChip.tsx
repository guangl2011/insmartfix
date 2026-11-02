import { cx } from './cx';

export type ChipTone = 'neutral' | 'brand';

/** Pill copy for each dispatch state / lifecycle stage (design §7.1). Same map as mobile. */
export const DISPATCH_LABELS = {
  UNDISPATCHED: 'Undispatched',
  PENDING: 'Pending',
  ACCEPTED: 'Accepted',
  IN_PROGRESS: 'In progress',
  ESCALATED: 'Escalated',
  NO_CONTRACTORS: 'No contractors',
  COMPLETED: 'Completed',
  EN_ROUTE: 'En route',
  ARRIVED: 'Arrived',
} as const;

export type DispatchLabelKey = keyof typeof DISPATCH_LABELS;

/** The pill for a WO: the lifecycle stage wins while in progress (En route / Arrived). */
export function dispatchLabel(state: string, stage?: string | null): string {
  if (state !== 'COMPLETED' && stage && stage in DISPATCH_LABELS)
    return DISPATCH_LABELS[stage as DispatchLabelKey];
  return state in DISPATCH_LABELS ? DISPATCH_LABELS[state as DispatchLabelKey] : state;
}

export interface StatusChipProps {
  label: string;
  tone?: ChipTone;
  className?: string;
}

/**
 * Dispatch / lifecycle pill (design §7.1): neutral or brand tones with a text label, never a
 * reserved status color (NFR-4, T-INBOX-2).
 */
export function StatusChip({ label, tone = 'neutral', className }: StatusChipProps) {
  return (
    <span
      data-tone={tone}
      className={cx(
        'inline-flex items-center rounded-lg border bg-surface-1 px-2.5 text-body-strong',
        tone === 'brand'
          ? 'border-brand-text text-brand-text'
          : 'border-border-strong text-secondary',
        className,
      )}
    >
      <span className="sr-only">Status: </span>
      {label}
    </span>
  );
}
