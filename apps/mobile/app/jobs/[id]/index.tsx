import { useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';
import { TopBar } from '@/src/shell';

/** Work-order detail (design §6.3). Filled in M5-T6. */
export default function JobScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return (
    <View testID="job-screen" accessibilityLabel={`Work order ${id}`} style={{ flex: 1 }}>
      <TopBar title="Work order" />
    </View>
  );
}
