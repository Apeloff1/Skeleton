/**
 * StudioLoginGate — gates the CNS Studio route behind authentication.
 *
 * Renders children when authenticated (or when the backend reports auth is not
 * enforced). Otherwise shows a login screen offering Emergent Google sign-in,
 * email/password login and register. Cyan is intentionally never used.
 */
import React from 'react';
import {
  View, Text, StyleSheet, SafeAreaView, TextInput, TouchableOpacity,
  ActivityIndicator, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import {
  checkMe, loginEmail, registerEmail, googleLogin, completeWebRedirect,
} from './gameforgeAuth';

const GREEN = '#22c55e';
const BLUE = '#3b82f6';
const PURPLE = '#a78bfa';
const CARD = '#111827';
const BG = '#0b1220';
const MUTE = '#94a3b8';
const RED = '#ef4444';

type Status = 'loading' | 'authed' | 'unauth';

export interface AuthState {
  role: string;
  user: any;
  enforced: boolean;
  refresh: () => void;
}

const AuthCtx = React.createContext<AuthState>({ role: 'anonymous', user: null, enforced: false, refresh: () => {} });
export const useStudioAuth = () => React.useContext(AuthCtx);

export default function StudioLoginGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [status, setStatus] = React.useState<Status>('loading');
  const [enforced, setEnforced] = React.useState(false);
  const [role, setRole] = React.useState('anonymous');
  const [user, setUser] = React.useState<any>(null);

  // form state
  const [mode, setMode] = React.useState<'login' | 'register'>('login');
  const [email, setEmail] = React.useState('');
  const [pass, setPass] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState('');

  const refresh = React.useCallback(async () => {
    const me = await checkMe();
    setEnforced(me.enforced);
    setRole(me.role);
    setUser(me.user);
    setStatus(me.authenticated || !me.enforced ? 'authed' : 'unauth');
  }, []);

  React.useEffect(() => {
    (async () => {
      await completeWebRedirect(); // finish any pending web Google redirect
      await refresh();
    })();
  }, [refresh]);

  const doGoogle = async () => {
    setBusy(true); setErr('');
    const r = await googleLogin();
    if (r.redirecting) return; // web navigates away
    if (r.ok) { await refresh(); }
    else if (r.error && r.error !== 'cancelled') setErr(r.error);
    setBusy(false);
  };

  const doEmail = async () => {
    if (!email.trim() || !pass || busy) return;
    setBusy(true); setErr('');
    const r = mode === 'login' ? await loginEmail(email, pass) : await registerEmail(email, pass);
    if (r.ok) await refresh();
    else setErr(r.error || 'Failed');
    setBusy(false);
  };

  const authValue: AuthState = { role, user, enforced, refresh };

  if (status === 'loading') {
    return (
      <SafeAreaView style={[st.root, st.center]}>
        <ActivityIndicator color={GREEN} size="large" />
        <Text style={st.loadingTxt}>Verifying session…</Text>
      </SafeAreaView>
    );
  }

  if (status === 'unauth') {
    return (
      <SafeAreaView style={st.root}>
        <View style={st.header}>
          <TouchableOpacity testID="gate-back" onPress={() => router.back()} style={{ padding: 4 }} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="chevron-back" size={22} color={GREEN} />
          </TouchableOpacity>
          <Text style={st.headerTitle}>Sign in to CNS Studio</Text>
        </View>
        <View style={st.body}>
          <View style={st.badgeRow}>
            <Ionicons name="shield-checkmark" size={16} color={GREEN} />
            <Text style={st.badgeTxt}>Production access is protected</Text>
          </View>

          <TouchableOpacity testID="gate-google" style={[st.googleBtn]} onPress={doGoogle} disabled={busy}>
            <Ionicons name="logo-google" size={18} color="#fff" />
            <Text style={st.googleTxt}>Continue with Google</Text>
          </TouchableOpacity>

          <View style={st.divider}><View style={st.line} /><Text style={st.orTxt}>or {mode === 'login' ? 'sign in' : 'register'} with email</Text><View style={st.line} /></View>

          <TextInput testID="gate-email" style={st.input} value={email} onChangeText={setEmail}
            placeholder="email" placeholderTextColor={MUTE} autoCapitalize="none" keyboardType="email-address" editable={!busy} />
          <TextInput testID="gate-pass" style={[st.input, { marginTop: 10 }]} value={pass} onChangeText={setPass}
            placeholder="password" placeholderTextColor={MUTE} secureTextEntry editable={!busy}
            onSubmitEditing={doEmail} />

          <TouchableOpacity testID="gate-submit" style={[st.primaryBtn, busy && { opacity: 0.6 }]} onPress={doEmail} disabled={busy}>
            {busy ? <ActivityIndicator color="#04120a" size="small" /> :
              <Text style={st.primaryTxt}>{mode === 'login' ? 'Sign in' : 'Create account'}</Text>}
          </TouchableOpacity>

          <TouchableOpacity onPress={() => { setMode(mode === 'login' ? 'register' : 'login'); setErr(''); }} disabled={busy} style={{ marginTop: 14 }}>
            <Text style={st.switchTxt}>
              {mode === 'login' ? "New here? Create an account" : 'Have an account? Sign in'}
            </Text>
          </TouchableOpacity>

          {!!err && <Text testID="gate-error" style={st.errTxt}>{err}</Text>}
        </View>
      </SafeAreaView>
    );
  }

  return <AuthCtx.Provider value={authValue}>{children}</AuthCtx.Provider>;
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: BG },
  center: { alignItems: 'center', justifyContent: 'center' },
  loadingTxt: { color: MUTE, marginTop: 12, fontSize: 13 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1f2937' },
  headerTitle: { color: '#f1f5f9', fontSize: 16, fontWeight: '700' },
  body: { padding: 20, paddingTop: 32 },
  badgeRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginBottom: 24 },
  badgeTxt: { color: MUTE, fontSize: 12 },
  googleBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, backgroundColor: BLUE, borderRadius: 12, paddingVertical: 14 },
  googleTxt: { color: '#fff', fontSize: 15, fontWeight: '700' },
  divider: { flexDirection: 'row', alignItems: 'center', gap: 10, marginVertical: 22 },
  line: { flex: 1, height: StyleSheet.hairlineWidth, backgroundColor: '#243043' },
  orTxt: { color: MUTE, fontSize: 11 },
  input: { backgroundColor: CARD, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 13, color: '#f1f5f9', fontSize: 14, borderWidth: StyleSheet.hairlineWidth, borderColor: '#243043' },
  primaryBtn: { backgroundColor: GREEN, borderRadius: 12, paddingVertical: 14, alignItems: 'center', marginTop: 16 },
  primaryTxt: { color: '#04120a', fontSize: 15, fontWeight: '800' },
  switchTxt: { color: PURPLE, fontSize: 13, textAlign: 'center', fontWeight: '600' },
  errTxt: { color: RED, fontSize: 13, marginTop: 16, textAlign: 'center' },
});
