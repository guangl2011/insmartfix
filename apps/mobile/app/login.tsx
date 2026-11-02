import { View } from 'react-native';
import { TopBar } from '@/src/shell';

/** Login (design §6.1). Filled in M5-T3. */
export default function LoginScreen() {
  return (
    <View testID="login-screen" style={{ flex: 1 }}>
      <TopBar title="Sign in" />
    </View>
  );
}
