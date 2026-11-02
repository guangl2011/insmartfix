/**
 * Health score (0–100) with its band (COLOR_LANGUAGE v1.3 §3). One of the two components allowed
 * to use the reserved status scale (NFR-4). The band solid is a graphic beside the number; the
 * number and the band label are drawn in neutral text roles, never color alone.
 */
import { healthBand, statusColors, STATUS_LABELS } from '@insmartfix/tokens/status';
import { StyleSheet, Text, View } from 'react-native';
import { textStyle, useTheme } from '../theme';

export interface HealthScoreProps {
  score: number;
  /** `inline` for the offer card risk line; `full` adds the band label (detail summary). */
  size?: 'inline' | 'full';
  testID?: string;
}

export function HealthScore({ score, size = 'inline', testID }: HealthScoreProps) {
  const theme = useTheme();
  const value = Math.round(score);
  const band = healthBand(value);
  const label = STATUS_LABELS[band];
  return (
    <View
      testID={testID}
      accessible
      accessibilityLabel={`Health score ${value} of 100, ${label}`}
      style={styles.row}
    >
      <View
        testID={testID ? `${testID}-band` : undefined}
        style={[styles.swatch, { backgroundColor: statusColors(theme.mode, band).solid }]}
      />
      <Text style={[textStyle(theme, 'bodyStrong'), { color: theme.colors.textPrimary }]}>
        Health {value}
      </Text>
      {size === 'full' ? (
        <Text style={[textStyle(theme, 'body'), { color: theme.colors.textSecondary }]}>
          {label}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  swatch: { width: 12, height: 12, borderRadius: 2 },
});
