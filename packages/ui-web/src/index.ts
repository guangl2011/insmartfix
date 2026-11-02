/**
 * @insmartfix/ui-web — the web component kit (design §7.4).
 * HealthScore and RiskBadge are the only status-color consumers (NFR-4, lint-enforced).
 * The Tailwind preset is `@insmartfix/ui-web/tailwind-preset`.
 */
export { Banner, type BannerProps } from './Banner';
export { Button, type ButtonProps, type ButtonVariant } from './Button';
export { cx, focusRing } from './cx';
export { EmptyState, type EmptyStateProps } from './EmptyState';
export { ErrorState, type ErrorStateProps } from './ErrorState';
export { HealthScore, type HealthScoreProps } from './HealthScore';
export { RiskBadge, riskLabel, type RiskBadgeProps } from './RiskBadge';
export { Sheet, type SheetProps } from './Sheet';
export { Skeleton, SkeletonList, type SkeletonListProps, type SkeletonProps } from './Skeleton';
export { Spinner } from './Spinner';
export {
  DISPATCH_LABELS,
  StatusChip,
  dispatchLabel,
  type ChipTone,
  type DispatchLabelKey,
  type StatusChipProps,
} from './StatusChip';
export { TOAST_MS, Toast, type ToastProps } from './Toast';
