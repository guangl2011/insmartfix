import { View } from 'react-native';
import { TopBar } from '@/src/shell';

/** Account (design §6.7). Filled in M5-T10. */
export default function AccountScreen() {
  return (
    <View testID="account-screen" style={{ flex: 1 }}>
      <TopBar title="Account" />
    </View>
  );
}
