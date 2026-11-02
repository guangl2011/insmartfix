import { StyleSheet, View, type DimensionValue } from 'react-native';
import { useTheme } from '../theme';

export interface SkeletonProps {
  /** Number of placeholder lines. */
  lines?: number;
  /** Width of the last line, so the block reads as text. */
  lastLineWidth?: DimensionValue;
  testID?: string;
}

/** Placeholder shapes while data loads — never a spinner (design §6.2, T-INBOX-7). */
export function Skeleton({ lines = 3, lastLineWidth = '60%', testID }: SkeletonProps) {
  const theme = useTheme();
  return (
    <View
      testID={testID}
      accessible
      accessibilityLabel="Loading"
      accessibilityState={{ busy: true }}
      style={[
        styles.card,
        { backgroundColor: theme.colors.surface2, borderColor: theme.colors.border },
      ]}
    >
      {Array.from({ length: lines }, (_, i) => (
        <View
          key={i}
          style={[
            styles.line,
            { backgroundColor: theme.colors.surface1 },
            i === lines - 1 && { width: lastLineWidth },
          ]}
        />
      ))}
    </View>
  );
}

/** A skeleton shaped like an offer card. */
export function SkeletonCard({ testID }: { testID?: string }) {
  return <Skeleton lines={4} lastLineWidth="40%" testID={testID} />;
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: 6, padding: 16, gap: 10 },
  line: { height: 16, borderRadius: 3, width: '100%' },
});
