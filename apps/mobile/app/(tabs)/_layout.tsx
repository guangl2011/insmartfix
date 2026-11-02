import { Tabs } from 'expo-router';
import { RequireSession } from '@/src/auth';
import { BottomNav } from '@/src/shell';
import { useTheme } from '@/src/theme';

/** Bottom nav: Inbox, Account and the disabled Voice intake stub (FR-9.1, design §5). */
export default function TabsLayout() {
  const theme = useTheme();
  return (
    <RequireSession>
      <Tabs
        tabBar={(props) => <BottomNav state={props.state} navigateToTab={props.navigateToTab} />}
        screenOptions={{
          headerShown: false,
          sceneStyle: { backgroundColor: theme.colors.surface0 },
        }}
      >
        <Tabs.Screen name="inbox" options={{ title: 'Inbox' }} />
        <Tabs.Screen name="account" options={{ title: 'Account' }} />
      </Tabs>
    </RequireSession>
  );
}
