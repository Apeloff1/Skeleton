import React from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Banner, Button, SectionTitle } from '../primitives';
import { C } from '../theme';

export function AccountScreen({
  phase, email, role, error, busy, onSignIn, onSignOut, onRetry, onBack, onSetup,
}: {
  phase: 'loading' | 'unavailable' | 'in' | 'out';
  email: string | null;
  role: string;
  error: string | null;
  busy: boolean;
  onSignIn: () => void;
  onSignOut: () => void;
  onRetry: () => void;
  onBack: () => void;
  onSetup: () => void;
}) {
  return (
    <ScrollView contentContainerStyle={st.body} testID="studio-account">
      <SectionTitle>Account</SectionTitle>
      {phase === 'loading' ? (
        <View style={st.row} accessibilityLiveRegion="polite">
          <ActivityIndicator color={C.accent} accessibilityLabel="Checking your session" />
          <Text style={st.copy}>Checking your session…</Text>
        </View>
      ) : null}
      {phase === 'unavailable' ? (
        <View>
          <Banner tone="bad" testID="studio-account-error">{error || 'The account service did not answer.'}</Banner>
          <View style={st.row}>
            <Button label="Try again" onPress={onRetry} busy={busy} testID="studio-retry-auth" />
            <Button label="Setup and readiness" tone="secondary" onPress={onSetup} testID="studio-setup" />
          </View>
        </View>
      ) : null}
      {phase === 'out' ? (
        <View>
          <Text style={st.copy}>You are not signed in. Projects on this device stay here until you sign in on a studio that keeps them.</Text>
          <View style={st.row}>
            <Button label="Sign in" onPress={onSignIn} testID="studio-signin-link" />
          </View>
        </View>
      ) : null}
      {phase === 'in' ? (
        <View>
          <Text style={st.copy} accessibilityLabel={email ? `Signed in as ${email}, role ${role}` : `Signed in, role ${role}`}>
            {email ? `Signed in as ${email}` : 'Signed in'}
          </Text>
          <Text style={st.meta}>Role: {role}</Text>
          <View style={st.row}>
            <Button label="Sign out" tone="danger" onPress={onSignOut} busy={busy} testID="studio-signout" />
          </View>
        </View>
      ) : null}
      <View style={st.row}>
        <Button label="Back to projects" tone="ghost" onPress={onBack} testID="studio-back" />
      </View>
    </ScrollView>
  );
}

const st = StyleSheet.create({
  body: { padding: 16, paddingBottom: 40, gap: 8 },
  copy: { color: C.text, fontSize: 15, lineHeight: 22 },
  meta: { color: C.mute, fontSize: 13, marginTop: 4 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginTop: 8 },
});
