import { StyleSheet, Text, View } from 'react-native';
import { textStyle, useTheme } from '../theme';
import { Button } from './Button';

export interface ErrorStateProps {
  /** e.g. "Couldn't load your jobs" (design §6.2) or "Couldn't load this job" (§6.3). */
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  /** Disables Retry while a retry is in flight. */
  retrying?: boolean;
  testID?: string;
}

/**
 * A named error state with Retry. Retry is a neutral secondary action: the view's single brand
 * primary stays in the sticky action bar (design §3.6).
 */
export function ErrorState({
  message,
  onRetry,
  retryLabel = 'Retry',
  retrying = false,
  testID,
}: ErrorStateProps) {
  const theme = useTheme();
  return (
    <View
      testID={testID}
      style={[
        styles.box,
        { backgroundColor: theme.colors.surface2, borderColor: theme.colors.borderStrong },
      ]}
    >
      <Text
        accessibilityRole="alert"
        style={[textStyle(theme, 'bodyStrong'), { color: theme.colors.textPrimary }]}
      >
        {message}
      </Text>
      {onRetry ? (
        <Button
          label={retryLabel}
          onPress={onRetry}
          busy={retrying}
          testID={testID ? `${testID}-retry` : 'retry'}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { borderWidth: 1, borderRadius: 6, padding: 16, gap: 12, alignItems: 'flex-start' },
});
