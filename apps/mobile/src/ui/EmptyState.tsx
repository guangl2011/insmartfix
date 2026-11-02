import type { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { textStyle, useTheme } from '../theme';

export interface EmptyStateProps {
  /** Calm, plain copy (design §6.2: "No open offers right now. …"). */
  message: string;
  title?: string;
  action?: ReactNode;
  testID?: string;
}

export function EmptyState({ message, title, action, testID }: EmptyStateProps) {
  const theme = useTheme();
  return (
    <View
      testID={testID}
      style={[
        styles.box,
        { backgroundColor: theme.colors.surface2, borderColor: theme.colors.border },
      ]}
    >
      {title ? (
        <Text
          accessibilityRole="header"
          style={[textStyle(theme, 'title'), { color: theme.colors.textPrimary }]}
        >
          {title}
        </Text>
      ) : null}
      <Text style={[textStyle(theme, 'body'), { color: theme.colors.textSecondary }]}>
        {message}
      </Text>
      {action}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { borderWidth: 1, borderRadius: 6, padding: 20, gap: 12 },
});
