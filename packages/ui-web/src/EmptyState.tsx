import type { ReactNode } from 'react';
import { cx } from './cx';

export interface EmptyStateProps {
  /** Calm, plain copy (design §6.2: "No open offers right now. …"). */
  message: string;
  title?: string;
  action?: ReactNode;
  className?: string;
  'data-testid'?: string;
}

/** A named, designed empty state (design §3.4 "honest states"). */
export function EmptyState({ message, title, action, className, ...rest }: EmptyStateProps) {
  return (
    <div
      data-testid={rest['data-testid']}
      className={cx(
        'flex flex-col gap-3 rounded-lg border border-border bg-surface-2 p-5',
        className,
      )}
    >
      {title ? <h2 className="m-0 text-title text-primary">{title}</h2> : null}
      <p className="m-0 text-body text-secondary">{message}</p>
      {action}
    </div>
  );
}
