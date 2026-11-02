import 'react-native-url-polyfill/auto';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { getMobileConfig } from '@/src/config';
import { getAppServices, ServicesProvider, type AppServices } from '@/src/data';
import { initCrashReporting } from '@/src/observability/crash';
import { ThemeProvider, useTheme } from '@/src/theme';

function ThemedStack() {
  const theme = useTheme();
  return (
    <>
      <StatusBar style={theme.mode === 'dark' ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: theme.colors.surface0 },
        }}
      />
    </>
  );
}

// Once per process, before the first render (NFR-7; off without a DSN).
initCrashReporting({ dsn: getMobileConfig().sentryDsn });

export interface RootLayoutProps {
  /** Tests inject fakes; the app uses the process-wide services. */
  services?: AppServices;
}

export default function RootLayout({ services }: RootLayoutProps = {}) {
  const s = services ?? getAppServices();
  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <ServicesProvider services={s}>
          <ThemedStack />
        </ServicesProvider>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
