import { cx } from './cx';

/** Inline progress indicator for busy buttons. Decorative: the button carries `aria-busy`. */
export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      data-testid="spinner"
      className={cx(
        'inline-block h-5 w-5 animate-spin rounded-full border-2 border-current border-r-transparent motion-reduce:animate-none',
        className,
      )}
    />
  );
}
