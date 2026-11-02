import type { ReactNode } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { MIN_TARGET, textStyle, useTheme } from '../theme';

export interface SheetProps {
  visible: boolean;
  title: string;
  /** Called on backdrop tap, the Close button and the Android back gesture (no modal trap). */
  onDismiss: () => void;
  children: ReactNode;
  testID?: string;
}

/** Light, dismissible bottom sheet (design §6.4 decline sheet, §8 "no modal traps"). */
export function Sheet({ visible, title, onDismiss, children, testID = 'sheet' }: SheetProps) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onDismiss}>
      <View style={styles.root}>
        <Pressable
          testID={`${testID}-backdrop`}
          accessibilityRole="button"
          accessibilityLabel="Close"
          onPress={onDismiss}
          style={[StyleSheet.absoluteFill, styles.backdrop]}
        />
        <View
          testID={testID}
          accessibilityViewIsModal
          style={[
            styles.panel,
            {
              backgroundColor: theme.colors.surface2,
              borderColor: theme.colors.border,
              paddingBottom: 16 + insets.bottom,
            },
          ]}
        >
          <View style={styles.header}>
            <Text
              accessibilityRole="header"
              style={[textStyle(theme, 'title'), styles.title, { color: theme.colors.textPrimary }]}
            >
              {title}
            </Text>
            <Pressable
              testID={`${testID}-close`}
              accessibilityRole="button"
              accessibilityLabel="Close"
              onPress={onDismiss}
              style={styles.close}
            >
              <Text style={[textStyle(theme, 'bodyStrong'), { color: theme.colors.textSecondary }]}>
                Close
              </Text>
            </Pressable>
          </View>
          {children}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, justifyContent: 'flex-end' },
  backdrop: { backgroundColor: 'rgba(11, 26, 36, 0.4)' },
  panel: {
    borderTopLeftRadius: 12,
    borderTopRightRadius: 12,
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingTop: 8,
    gap: 12,
  },
  header: { flexDirection: 'row', alignItems: 'center' },
  title: { flex: 1 },
  close: {
    minHeight: MIN_TARGET,
    minWidth: MIN_TARGET,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
});
