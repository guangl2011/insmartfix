import { Button } from './Button';
import { cx } from './cx';

export interface ErrorStateProps {
  /** e.g. "Couldn't load your jobs" (design §6.2) or "Couldn't load this job" (§6.3). */
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  /** Busy Retry while a retry is in flight. */
  retrying?: boolean;
  className?: string;
  'data-testid'?: string;
}

/**
 * A named error state with Retry. Retry is a neutral secondary action: the view's single brand
 * primary stays in the sticky action bar (design §3.6). The caller keeps showing last-known data
 * beside it (design §6.2 "don't blank the screen").
 */
export function ErrorState({
  message,
  onRetry,
  retryLabel = 'Retry',
  retrying = false,
  className,
  ...rest
}: ErrorStateProps) {
  return (
    <div
      data-testid={rest['data-testid']}
      className={cx(
        'flex flex-col items-start gap-3 rounded-lg border border-border-strong bg-surface-2 p-4',
        className,
      )}
    >
      <p role="alert" className="m-0 text-body-strong text-primary">
        {message}
      </p>
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry} busy={retrying}>
          {retryLabel}
        </Button>
      ) : null}
    </div>
  );
}
