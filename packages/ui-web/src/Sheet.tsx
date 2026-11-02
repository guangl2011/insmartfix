'use client';
import { useEffect, useId, useRef, type ReactNode } from 'react';
import { cx, focusRing } from './cx';

export interface SheetProps {
  open: boolean;
  title: string;
  /** Called on backdrop click, the Close button and Escape (no modal trap, design §8). */
  onDismiss: () => void;
  children: ReactNode;
  className?: string;
}

/**
 * Light, dismissible bottom sheet (design §6.4 decline sheet). Focus moves into the sheet when it
 * opens and returns to the opener when it closes; Escape, the backdrop and Close all dismiss it.
 */
export function Sheet({ open, title, onDismiss, children, className }: SheetProps) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);
  // Latest handler without re-running the focus effect (an inline onDismiss would otherwise
  // steal focus from a field inside the sheet on every parent render).
  const dismiss = useRef(onDismiss);
  useEffect(() => {
    dismiss.current = onDismiss;
  }, [onDismiss]);

  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement;
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') dismiss.current();
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      if (opener.current instanceof HTMLElement) opener.current.focus();
    };
  }, [open]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end">
      <button
        type="button"
        aria-label="Close"
        tabIndex={-1}
        data-testid="sheet-backdrop"
        onClick={onDismiss}
        className="absolute inset-0 h-full w-full cursor-default bg-text-primary opacity-40"
      />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        data-testid="sheet"
        className={cx(
          'relative mx-auto flex w-full max-w-content flex-col gap-4 rounded-t-lg border border-border bg-surface-2 p-4 pb-6 outline-none',
          className,
        )}
      >
        <div className="flex items-center justify-between gap-3">
          <h2 id={titleId} className="m-0 text-title text-primary">
            {title}
          </h2>
          <button
            type="button"
            onClick={onDismiss}
            className={cx(
              'min-h-tap min-w-tap rounded-lg px-3 text-body-strong text-secondary',
              focusRing,
            )}
          >
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
