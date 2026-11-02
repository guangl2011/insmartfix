import { cx } from './cx';

export interface BannerProps {
  /** e.g. "You're offline — showing your last update" (FR-2.7). */
  message: string;
  className?: string;
  'data-testid'?: string;
}

/** Thin persistent banner (offline, queued). Neutral tones only; announced politely. */
export function Banner({ message, className, ...rest }: BannerProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid={rest['data-testid']}
      className={cx(
        'border-b border-border-strong bg-surface-1 px-4 py-2.5 text-body text-primary',
        className,
      )}
    >
      {message}
    </div>
  );
}
