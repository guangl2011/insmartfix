import { Stack } from 'expo-router';
import { RequireSession } from '@/src/auth';

export default function JobsLayout() {
  return (
    <RequireSession>
      <Stack screenOptions={{ headerShown: false }} />
    </RequireSession>
  );
}
