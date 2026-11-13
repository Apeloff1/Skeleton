/**
 * Sign-in against the existing account client. Guest continuation is offered
 * only when the backend says auth is not enforced.
 */
import React from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { credentialError } from '../../foundation/model';
import { Banner, Button, Field, SectionTitle } from '../primitives';
import { C } from '../theme';

export function SignInScreen({
  phase, error, enforced, busy, intentCreate, onSubmit, onGoogle, onRetry, onGuest, onSetup,
}: {
  phase: 'loading' | 'unavailable' | 'form';
  error: string | null;
  enforced: boolean;
  busy: boolean;
  intentCreate: boolean;
  onSubmit: (email: string, password: string, mode: 'login' | 'register') => void;
  onGoogle: () => void;
  onRetry: () => void;
  onGuest: () => void;
  onSetup: () => void;
}) {
  const [mode, setMode] = React.useState<'login' | 'register'>('login');
  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [localError, setLocalError] = React.useState<string | null>(null);
  const shown = localError || error;

  const submit = () => {
    const problem = credentialError(email, password);
    if (problem) { setLocalError(problem); return; }
    setLocalError(null);
    onSubmit(email, password, mode);
  };

  if (phase === 'loading') {
    return (
      <View style={st.center} testID="studio-signin" accessibilityLiveRegion="polite">
        <ActivityIndicator color={C.accent} accessibilityLabel="Checking your session" />
        <Text style={st.bodyText}>Checking your session…</Text>
        <Button label="Setup and readiness" tone="ghost" onPress={onSetup} testID="studio-setup" />
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={st.body} keyboardShouldPersistTaps="handled" testID="studio-signin">
      <SectionTitle>Sign in</SectionTitle>
      <Text style={st.bodyText}>
        Uses the studio account already on this app: email and password, or Google. No separate account service was added.
      </Text>
      {intentCreate ? <Banner tone="idle" testID="studio-signin-intent">Sign in to start your first project. The brief opens after the account is accepted.</Banner> : null}
      {phase === 'unavailable' ? (
        <View>
          <Banner tone="bad" testID="studio-signin-error">{shown || 'The account service did not answer.'}</Banner>
          <View style={st.row}>
            <Button label="Try again" onPress={onRetry} busy={busy} testID="studio-retry-auth" />
            <Button label="Setup and readiness" tone="secondary" onPress={onSetup} testID="studio-setup" />
            {enforced ? null : <Button label="Continue on this device" tone="ghost" onPress={onGuest} testID="studio-guest" a11yHint="The account service is not required right now" />}
          </View>
        </View>
      ) : (
        <View>
          <Field label="Email" value={email} onChangeText={setEmail} keyboard="email-address" placeholder="you@studio.test" disabled={busy} testID="studio-email" />
          <Field label="Password" value={password} onChangeText={setPassword} secure placeholder="password" disabled={busy} onSubmit={submit} testID="studio-password" />
          {shown ? <Banner tone="bad" testID="studio-signin-error">{shown}</Banner> : null}
          <View style={st.row}>
            <Button label={mode === 'login' ? 'Sign in' : 'Create account'} onPress={submit} busy={busy} testID="studio-submit" />
            <Button label="Continue with Google" tone="secondary" onPress={onGoogle} disabled={busy} testID="studio-google" />
          </View>
          <Button
            label={mode === 'login' ? 'New here? Create an account' : 'Have an account? Sign in'}
            tone="ghost"
            onPress={() => { setMode(mode === 'login' ? 'register' : 'login'); setLocalError(null); }}
            disabled={busy}
            testID="studio-mode"
          />
          <View style={st.row}>
            <Button label="Setup and readiness" tone="ghost" onPress={onSetup} testID="studio-setup" />
            {enforced ? null : <Button label="Continue on this device" tone="ghost" onPress={onGuest} testID="studio-guest" a11yHint="Auth is not enforced. Projects stay on this device." />}
          </View>
        </View>
      )}
    </ScrollView>
  );
}

const st = StyleSheet.create({
  body: { padding: 16, paddingBottom: 40, gap: 8 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 24 },
  bodyText: { color: C.text, fontSize: 15, lineHeight: 22 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
});
