/**
 * Failure-risk pill (COLOR_LANGUAGE v1.3 §3). One of the two components allowed to use the
 * reserved status scale (NFR-4); the band always carries its text label ("High risk").
 */
import { riskBand, statusColors, STATUS_LABELS, type FailureRisk } from '@insmartfix/tokens/status';
import { StyleSheet, Text, View } from 'react-native';
import { textStyle, useTheme } from '../theme';

export interface RiskBadgeProps {
  risk: FailureRisk;
  testID?: string;
}

/** "Low risk" / "Medium risk" / "High risk" / "Critical risk". */
export function riskLabel(risk: FailureRisk): string {
  const band = STATUS_LABELS[riskBand(risk)];
  return `${risk === 'LOW' ? 'Low' : band} risk`;
}

export function RiskBadge({ risk, testID }: RiskBadgeProps) {
  const theme = useTheme();
  const c = statusColors(theme.mode, riskBand(risk));
  const label = riskLabel(risk);
  return (
    <View
      testID={testID}
      accessible
      accessibilityLabel={`Failure risk: ${label}`}
      style={[styles.pill, { backgroundColor: c.fill, borderRadius: theme.radii.lg }]}
    >
      <Text style={[textStyle(theme, 'bodyStrong'), { color: c.text }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: { alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 2 },
});
