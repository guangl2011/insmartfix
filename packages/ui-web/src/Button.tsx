import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cx, focusRing } from './cx';
import { Spinner } from './Spinner';

export type ButtonVariant = 'primary' | 'secondary' | 'quiet';

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  /**
   * `primary` is the view's ONE brand action (design §3.6, NFR-4): put it in the sticky action
   * bar. Everything else is `secondary` (outlined, neutral) or `quiet` (text-only).
   */
  variant?: ButtonVariant;
  /** Shows a spinner, sets `aria-busy` and disables the button (FR-1.5, FR-4.1). */
  busy?: boolean;
  /** Replaces the label while busy, e.g. "Accepting…". */
  busyLabel?: string;
  /** Stretches to the container width (sticky bar, forms). */
  block?: boolean;
  children: ReactNode;
}

const VARIANTS: Record<ButtonVariant, string> = {
  // White on #0396A6 is 3.55:1, so the label MUST be the 19 px bold `action` style (large text).
  primary:
    'bg-brand text-on-brand text-action hover:bg-brand-pressed active:bg-brand-pressed disabled:bg-border-strong disabled:text-text-primary',
  secondary:
    'bg-surface-2 text-primary text-action border border-border-strong hover:bg-surface-1 active:bg-surface-1',
  quiet: 'bg-transparent text-primary text-body-strong underline-offset-4 hover:underline',
};

/** Field-sized button: ≥ 48 px tall and ≥ 44 px wide (NFR-2, T-ERGO-1). */
export function Button({
  variant = 'secondary',
  busy = false,
  busyLabel,
  block = false,
  disabled,
  className,
  type = 'button',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      {...rest}
      data-variant={variant}
      aria-busy={busy || undefined}
      disabled={disabled || busy}
      className={cx(
        'inline-flex min-h-button min-w-tap items-center justify-center gap-2 rounded-lg px-5 select-none',
        'disabled:cursor-not-allowed',
        VARIANTS[variant],
        block && 'w-full',
        focusRing,
        className,
      )}
    >
      {busy ? <Spinner /> : null}
      <span>{busy && busyLabel ? busyLabel : children}</span>
    </button>
  );
}
