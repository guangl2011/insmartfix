import { ActivityIndicator, Pressable, StyleSheet, Text, View, type ViewStyle } from 'react-native';
import { MIN_TARGET, textStyle, useTheme } from '../theme';

export type ButtonVariant = 'primary' | 'secondary' | 'quiet';

/** Every primary button renders with this testID, so a screen test can assert "exactly one". */
export const PRIMARY_ACTION_TESTID = 'primary-action';

export interface ButtonProps {
  label: string;
  onPress: () => void;
  /**
   * `primary` is the single brand-teal action of the view (design §3.6, NFR-4) and belongs in the
   * sticky action bar. `secondary` is outlined neutral; `quiet` is a text-only neutral action.
   */
  variant?: ButtonVariant;
  disabled?: boolean;
  /** Shows a spinner and disables the button (e.g. "Accepting…", "Signing in"). */
  busy?: boolean;
  /** Screen-reader label when it should differ from `label`. */
  accessibilityLabel?: string;
  accessibilityHint?: string;
  /** Ignored for `primary` (always {@link PRIMARY_ACTION_TESTID}). */
  testID?: string;
  style?: ViewStyle;
  /** Stretch to the container width (sticky bar, forms). */
  block?: boolean;
}

export function Button({
  label,
  onPress,
  variant = 'secondary',
  disabled = false,
  busy = false,
  accessibilityLabel,
  accessibilityHint,
  testID,
  style,
  block = false,
}: ButtonProps) {
  const theme = useTheme();
  const c = theme.colors;
  const inactive = disabled || busy;
  const fg = variant === 'primary' ? c.onBrand : c.textPrimary;

  return (
    <Pressable
      testID={variant === 'primary' ? PRIMARY_ACTION_TESTID : testID}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: inactive, busy }}
      disabled={inactive}
      onPress={onPress}
      style={({ pressed }) => [
        styles.base,
        { minHeight: theme.layout.primaryButtonHeight, borderRadius: theme.radii.lg },
        variant === 'primary' && {
          backgroundColor: pressed ? c.brandPressed : c.brand,
        },
        variant === 'secondary' && {
          backgroundColor: pressed ? c.surface1 : c.surface2,
          borderColor: c.borderStrong,
          borderWidth: 1,
        },
        variant === 'quiet' && { backgroundColor: pressed ? c.surface1 : 'transparent' },
        block && styles.block,
        inactive && styles.inactive,
        style,
      ]}
    >
      <View style={styles.row}>
        {busy ? <ActivityIndicator color={fg} accessibilityElementsHidden /> : null}
        <Text
          style={[textStyle(theme, variant === 'quiet' ? 'bodyStrong' : 'action'), { color: fg }]}
          numberOfLines={1}
        >
          {label}
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minWidth: MIN_TARGET,
    paddingHorizontal: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  block: { alignSelf: 'stretch' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  inactive: { opacity: 0.55 },
});
