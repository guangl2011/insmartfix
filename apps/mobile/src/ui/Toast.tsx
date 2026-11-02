import { useEffect } from 'react';
import { AccessibilityInfo, StyleSheet, Text, View } from 'react-native';
import { textStyle, useTheme } from '../theme';

export const TOAST_MS = 4000;

export interface ToastProps {
  /** Null hides the toast. A new message restarts the timer. */
  message: string | null;
  onHide: () => void;
  durationMs?: number;
  testID?: string;
}

/**
 * Non-alarming transient notice (design §6.2 stale-offer toast). Neutral surface, announced to
 * screen readers, dismissed automatically; it never blocks input (no modal trap, design §8).
 */
export function Toast({ message, onHide, durationMs = TOAST_MS, testID = 'toast' }: ToastProps) {
  const theme = useTheme();

  useEffect(() => {
    if (message === null) return;
    AccessibilityInfo.announceForAccessibility?.(message);
    const t = setTimeout(onHide, durationMs);
    return () => clearTimeout(t);
  }, [message, onHide, durationMs]);

  if (message === null) return null;
  return (
    <View pointerEvents="box-none" style={styles.wrap}>
      <View
        testID={testID}
        accessible
        accessibilityRole="alert"
        accessibilityLiveRegion="polite"
        accessibilityLabel={message}
        pointerEvents="none"
        style={[
          styles.toast,
          { backgroundColor: theme.colors.textPrimary, borderRadius: theme.radii.lg },
        ]}
      >
        <Text style={[textStyle(theme, 'body'), { color: theme.colors.surface2 }]}>{message}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { position: 'absolute', left: 16, right: 16, bottom: 96, alignItems: 'center' },
  toast: { paddingHorizontal: 16, paddingVertical: 12, maxWidth: 560 },
});
