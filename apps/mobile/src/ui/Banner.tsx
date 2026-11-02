import { StyleSheet, Text, View } from 'react-native';
import { textStyle, useTheme } from '../theme';

export interface BannerProps {
  /** e.g. "You're offline — showing your last update" (FR-2.7). */
  message: string;
  testID?: string;
}

/** Thin persistent banner (offline, queued). Neutral tones only; announced politely. */
export function Banner({ message, testID }: BannerProps) {
  const theme = useTheme();
  return (
    <View
      testID={testID}
      accessible
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      accessibilityLabel={message}
      style={[
        styles.bar,
        { backgroundColor: theme.colors.surface1, borderColor: theme.colors.borderStrong },
      ]}
    >
      <Text style={[textStyle(theme, 'body'), { color: theme.colors.textPrimary }]}>{message}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { borderBottomWidth: 1, paddingHorizontal: 16, paddingVertical: 10 },
});
