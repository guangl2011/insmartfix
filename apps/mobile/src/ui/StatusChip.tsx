import { StyleSheet, Text, View } from 'react-native';
import { textStyle, useTheme } from '../theme';

/**
 * Dispatch / lifecycle pill (design §7.1): neutral or brand tones, always a text label, never a
 * reserved status color (NFR-4).
 */
export type ChipTone = 'neutral' | 'brand';

export interface StatusChipProps {
  label: string;
  tone?: ChipTone;
  testID?: string;
}

export function StatusChip({ label, tone = 'neutral', testID }: StatusChipProps) {
  const theme = useTheme();
  const c = theme.colors;
  return (
    <View
      testID={testID}
      accessible
      accessibilityLabel={`Status: ${label}`}
      style={[
        styles.chip,
        {
          borderRadius: theme.radii.lg,
          borderColor: tone === 'brand' ? c.brandText : c.borderStrong,
        },
        { backgroundColor: c.surface1 },
      ]}
    >
      <Text
        style={[
          textStyle(theme, 'bodyStrong'),
          { color: tone === 'brand' ? c.brandText : c.textSecondary },
        ]}
      >
        {label}
      </Text>
    </View>
  );
}

/** Pill copy for each dispatch state / lifecycle stage (design §7.1). */
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

const styles = StyleSheet.create({
  chip: {
    alignSelf: 'flex-start',
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 2,
  },
});
