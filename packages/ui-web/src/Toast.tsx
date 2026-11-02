'use client';
import { useEffect } from 'react';
import { cx } from './cx';

export const TOAST_MS = 4000;

export interface ToastProps {
  /** Null hides the toast. A new message restarts the timer. */
  message: string | null;
  onHide: () => void;
  durationMs?: number;
  className?: string;
}

/**
 * Non-alarming transient notice (design §6.2 stale-offer toast). Neutral inverse surface,
 * announced politely, hidden automatically; it never takes focus or blocks input (design §8).
 * The live region is always mounted so screen readers pick up the first message too.
 */
export function Toast({ message, onHide, durationMs = TOAST_MS, className }: ToastProps) {
  useEffect(() => {
    if (message === null) return;
    const t = setTimeout(onHide, durationMs);
    return () => clearTimeout(t);
  }, [message, onHide, durationMs]);

  return (
    <div
      role="status"
      aria-live="polite"
      className={cx(
        'pointer-events-none fixed inset-x-4 bottom-24 z-40 flex justify-center',
        className,
      )}
    >
      {message !== null ? (
        <p
          data-testid="toast"
          className="m-0 max-w-content rounded-lg bg-text-primary px-4 py-3 text-body text-surface-2 shadow-lg"
        >
          {message}
        </p>
      ) : null}
    </div>
  );
}
