import { Redirect } from 'expo-router';
import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useSession, type SignInResult } from '@/src/auth';
import { MIN_TARGET, textStyle, useTheme } from '@/src/theme';
import { AppText, Button } from '@/src/ui';

/** Copy from design §6.1 / FR-1.1 (word for word). */
export const LOGIN_COPY = {
  tagline: 'Jobs that arrive diagnosed.',
  invalid: 'Email or password is incorrect',
  network: "Can't reach InsmartFix. Check your connection and try again.",
  rateLimited: 'Too many sign-in attempts. Wait a minute and try again.',
  server: 'Something went wrong on our side. Try again.',
} as const;

type Failure = Exclude<SignInResult, { ok: true }>['reason'];

const MESSAGE: Record<Failure, string> = {
  invalid: LOGIN_COPY.invalid,
  network: LOGIN_COPY.network,
  rate_limited: LOGIN_COPY.rateLimited,
  server: LOGIN_COPY.server,
};

/** Login (design §6.1, FR-1.1, FR-1.5). */
export default function LoginScreen() {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const { status, signIn } = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);

  // Signed in (at launch or just now) → the Inbox.
  if (status === 'signedIn') return <Redirect href="/inbox" />;

  const canSubmit = email.trim() !== '' && password !== '' && !submitting;
  const submit = () => {
    void attempt();
  };
  const attempt = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setFailure(null);
    const result = await signIn(email, password);
    setSubmitting(false);
    if (!result.ok) setFailure(result.reason);
  };

  const c = theme.colors;
  const input = [
    textStyle(theme, 'body'),
    styles.input,
    { color: c.textPrimary, backgroundColor: c.surface2, borderColor: c.borderStrong },
  ];

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      testID="login-screen"
    >
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + 48, paddingBottom: insets.bottom + 24 },
        ]}
      >
        <View style={styles.brand}>
          <AppText variant="display" accessibilityRole="header">
            InsmartFix
          </AppText>
          <AppText tone="secondary">{LOGIN_COPY.tagline}</AppText>
        </View>

        <View style={styles.field}>
          <AppText variant="bodyStrong" nativeID="email-label">
            Email
          </AppText>
          <TextInput
            testID="login-email"
            accessibilityLabel="Email"
            accessibilityLabelledBy="email-label"
            value={email}
            onChangeText={setEmail}
            editable={!submitting}
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
            keyboardType="email-address"
            textContentType="username"
            returnKeyType="next"
            placeholderTextColor={c.textSecondary}
            style={input}
          />
        </View>
        <View style={styles.field}>
          <AppText variant="bodyStrong" nativeID="password-label">
            Password
          </AppText>
          <TextInput
            testID="login-password"
            accessibilityLabel="Password"
            accessibilityLabelledBy="password-label"
            value={password}
            onChangeText={setPassword}
            editable={!submitting}
            secureTextEntry
            autoCapitalize="none"
            autoComplete="current-password"
            textContentType="password"
            returnKeyType="go"
            onSubmitEditing={submit}
            placeholderTextColor={c.textSecondary}
            style={input}
          />
        </View>

        {failure ? (
          <View style={styles.error} testID="login-error">
            <AppText accessibilityRole="alert" variant="bodyStrong">
              {MESSAGE[failure]}
            </AppText>
            {failure === 'network' ? (
              <Button label="Retry" onPress={submit} testID="login-retry" />
            ) : null}
          </View>
        ) : null}

        <Button
          label="Sign in"
          variant="primary"
          block
          onPress={submit}
          disabled={!canSubmit}
          busy={submitting}
        />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: {
    flexGrow: 1,
    justifyContent: 'center',
    paddingHorizontal: 24,
    gap: 20,
    maxWidth: 480,
    width: '100%',
    alignSelf: 'center',
  },
  brand: { gap: 4, marginBottom: 12 },
  field: { gap: 6 },
  input: { minHeight: MIN_TARGET + 4, borderWidth: 1, borderRadius: 6, paddingHorizontal: 12 },
  error: { gap: 12, alignItems: 'flex-start' },
});
