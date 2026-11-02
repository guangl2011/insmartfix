import { Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { MIN_TARGET, useTheme } from '../theme';
import { AppText } from '../ui';

/** Primary navigation (FR-9.1): Inbox and Account, plus the disabled Voice intake seam (D§14). */
export const NAV_ITEMS = [
  { route: 'inbox', label: 'Inbox' },
  { route: 'account', label: 'Account' },
] as const;
export const VOICE_STUB_LABEL = 'Voice intake';

/** The subset of the tab navigator's props the bar needs. */
export interface BottomNavProps {
  state: { index: number; routes: { key: string; name: string }[] };
  navigateToTab: (routeKey: string) => void;
}

export function BottomNav({ state, navigateToTab }: BottomNavProps) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const current = state.routes[state.index]?.name;
  const c = theme.colors;
  return (
    <View
      accessibilityRole="tablist"
      style={[
        styles.bar,
        { paddingBottom: insets.bottom, backgroundColor: c.surface2, borderTopColor: c.border },
      ]}
    >
      {NAV_ITEMS.map((item) => {
        const selected = current === item.route;
        const key = state.routes.find((r) => r.name === item.route)?.key;
        return (
          <Pressable
            key={item.route}
            testID={`nav-${item.route}`}
            accessibilityRole="tab"
            accessibilityLabel={item.label}
            accessibilityState={{ selected }}
            onPress={() => {
              if (!selected && key) navigateToTab(key);
            }}
            style={[styles.item, { borderTopColor: selected ? c.brand : 'transparent' }]}
          >
            <AppText variant="bodyStrong" tone={selected ? 'brand' : 'secondary'}>
              {item.label}
            </AppText>
          </Pressable>
        );
      })}
      <Pressable
        testID="nav-voice"
        accessibilityRole="tab"
        accessibilityLabel={VOICE_STUB_LABEL}
        accessibilityHint="Not available yet"
        accessibilityState={{ disabled: true, selected: false }}
        disabled
        style={[styles.item, { borderTopColor: 'transparent' }]}
      >
        <AppText variant="bodyStrong" tone="muted">
          {VOICE_STUB_LABEL}
        </AppText>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { flexDirection: 'row', borderTopWidth: 1 },
  item: {
    flex: 1,
    minHeight: MIN_TARGET + 12,
    alignItems: 'center',
    justifyContent: 'center',
    borderTopWidth: 3,
    paddingHorizontal: 4,
  },
});
