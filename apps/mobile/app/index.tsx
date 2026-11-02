import { StyleSheet, Text, View } from 'react-native';
import { getMobileConfig } from '@/src/config';
import { useTheme } from '@/src/useTheme';

/** M0 placeholder screen. Replaced by the Offer Inbox in M5. */
export default function HomeScreen() {
  const theme = useTheme();
  const config = getMobileConfig();
  return (
    <View
      testID="home-screen"
      style={[styles.container, { backgroundColor: theme.colors.surface0 }]}
    >
      <Text accessibilityRole="header" style={[styles.title, { color: theme.colors.textPrimary }]}>
        InsmartFix
      </Text>
      <Text style={[styles.body, { color: theme.colors.textSecondary }]}>
        Contractor field app — scaffold.
      </Text>
      <Text testID="data-source" style={[styles.body, { color: theme.colors.textMuted }]}>
        Data source: {config.dataSource}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 8 },
  title: { fontSize: 32, fontWeight: '700' },
  body: { fontSize: 16 },
});
