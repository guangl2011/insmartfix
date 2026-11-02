import { cx } from './cx';

export interface SkeletonProps {
  /** Number of placeholder text lines. */
  lines?: number;
  className?: string;
}

/** A neutral placeholder block (design §6.2: skeleton cards, never a spinner). */
export function Skeleton({ lines = 3, className }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      data-testid="skeleton"
      className={cx(
        'flex flex-col gap-3 rounded-lg border border-border bg-surface-2 p-4',
        className,
      )}
    >
      {Array.from({ length: lines }, (_, i) => (
        <span
          key={i}
          className={cx(
            'block h-4 rounded-sm bg-surface-1 animate-pulse motion-reduce:animate-none',
            i === 0 ? 'w-3/4' : i === lines - 1 ? 'w-1/2' : 'w-full',
          )}
        />
      ))}
    </div>
  );
}

export interface SkeletonListProps {
  count?: number;
  /** Announced once to screen readers, e.g. "Loading your jobs". */
  label: string;
  lines?: number;
}

/** A list of skeleton cards with a single polite status announcement. */
export function SkeletonList({ count = 3, label, lines = 3 }: SkeletonListProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      data-testid="skeleton-list"
      className="flex flex-col gap-3"
    >
      <span className="sr-only">{label}</span>
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} lines={lines} />
      ))}
    </div>
  );
}
