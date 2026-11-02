import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../theme';
import { AppText } from '../ui';

export interface TopBarProps {
  title: string;
  /** Optional trailing control (e.g. a back button lives in `leading`). */
  leading?: ReactNode;
  trailing?: ReactNode;
}

/** Screen title bar (design §5 "top bar"), safe-area aware. */
export function TopBar({ title, leading, trailing }: TopBarProps) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <View
      style={[
        styles.bar,
        {
          paddingTop: insets.top + 8,
          backgroundColor: theme.colors.surface2,
          borderBottomColor: theme.colors.border,
        },
      ]}
    >
      {leading}
      <AppText variant="headline" accessibilityRole="header" style={styles.title} numberOfLines={1}>
        {title}
      </AppText>
      {trailing}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 16,
    paddingBottom: 8,
    minHeight: 56,
    borderBottomWidth: 1,
  },
  title: { flex: 1 },
});
