import { View } from 'react-native';
import { TopBar } from '@/src/shell';

/** Offer Inbox (design §6.2). Filled in M5-T4. */
export default function InboxScreen() {
  return (
    <View testID="inbox-screen" style={{ flex: 1 }}>
      <TopBar title="Inbox" />
    </View>
  );
}
