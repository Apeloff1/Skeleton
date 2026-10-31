import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, SafeAreaView, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Clipboard from 'expo-clipboard';
import { readAppReadiness, type AppReadiness } from '../../product/appReadinessClient';
import s, { colors } from './AppSetupWorkspace.styles';
import { getAuthEpoch, subscribeAuthChanges } from '../../auth/gameforgeAuth';

const COMMANDS = [
  { title: 'Install and start', command: 'python scripts/install_app.py --production --start', text: 'Run from the repository in your Python 3.11+ environment on the host machine, with Docker running. Production mode serves the built web app. The installer reports missing prerequisites.' },
  { title: 'Configure the installation owner', command: 'python -m skeleton app setup --admin-email owner@example.com --admin-password-file /absolute/private/owner-password.txt', text: 'Replace the example email and path with your own. Prepare a private UTF-8 password file with at least 16 characters and at most 72 UTF-8 bytes (Unix mode 0600), then run this command and recreate the backend with python -m skeleton app up --production --no-build. Registration creates a viewer; it does not grant capture or administrator permissions.' },
  { title: 'Optional pinned local model', command: 'python scripts/provision_local_ai.py --target linux-x86_64-glibc --download --context-size 12288 --output ./data/local-ai', text: 'Prepare the pinned model/runtime files for a Linux x86-64 glibc host. Other hosts require the provisioner’s explicit container preparation option and a compatible Linux AMD64 engine. Finish its printed activation steps and mount the deployment directory before selecting the local model. Downloading files alone does not make chat ready; the larger context still needs sufficient model memory.' },
  { title: 'Inspect first-install diagnostics', command: 'python -m skeleton app doctor --live --studio --json', text: 'Inspect runtime dependencies and configuration. A healthy web server alone does not confirm a working model or crawler.' },
  { title: 'Inspect native studio setup', command: 'python -m skeleton app doctor --studio --json', text: 'Inspect host toolchains, approved native cores and local learning prerequisites. Host tools do not establish availability inside the running backend; use the studio’s observed server diagnostics too.' },
  { title: 'Inspect running services', command: 'python -m skeleton app status --live', text: 'Check the application, AI engine and storage. Configure model weights or approved provider credentials through the host setup.' },
];
export default function AppSetupWorkspace() {
  const router = useRouter();
  const [snapshot, setSnapshot] = useState<AppReadiness | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const request = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    request.current?.abort(); const current = new AbortController(); request.current = current; setBusy(true); setError('');
    try { const value = await readAppReadiness(current.signal); if (!current.signal.aborted && value.accountEpoch === getAuthEpoch()) setSnapshot(value); }
    catch (err) { if (!current.signal.aborted) setError(err instanceof Error ? err.message : 'Readiness could not be checked.'); }
    finally { if (request.current === current) setBusy(false); }
  }, []);
  useEffect(() => { void refresh(); return () => request.current?.abort(); }, [refresh]);
  useEffect(() => subscribeAuthChanges(() => {
    request.current?.abort(); setSnapshot(null); setBusy(false);
    setError('Your account changed. Check readiness again for the current account.');
  }), []);
  const button = (label: string, onPress: () => void, disabled = false) => <TouchableOpacity accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={[s.button, disabled && s.disabled]}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
  return <SafeAreaView style={s.safe}><ScrollView contentContainerStyle={s.page} keyboardShouldPersistTaps="handled">
    <View style={s.row}><View style={s.grow}><Text style={s.eyebrow}>SKELETON · GET STARTED</Text><Text style={s.title}>Make the app ready</Text></View>{button('Home', () => router.push('/product' as never))}</View>
    <Text style={s.subtitle}>Check what is running, finish setup on your host, then start an AI conversation or capture web knowledge. You can read this guide before signing in.</Text>
    <View style={s.twoColumns}><View style={[s.column, s.card]}>
      <View style={s.row}><Text style={[s.heading, s.grow]}>Observed readiness</Text>{busy && <ActivityIndicator color={colors.accent} />}{button(busy ? 'Checking…' : 'Check again', () => void refresh(), busy)}</View>
      <Text style={s.small}>{snapshot ? `Checked ${new Date(snapshot.observedAt).toLocaleTimeString()}. Each capability is checked separately.` : 'No readiness verdict until the services respond.'}</Text>
      {error ? <Text accessibilityRole="alert" style={s.error}>{error}</Text> : null}
      {snapshot?.checks.map(check => <View key={check.id} style={s.check}><View style={s.row}><Text style={[s.label, s.grow]}>{check.label}</Text><View style={s.badge}><Text style={[s.badgeText, check.status === 'ready' && s.success]}>{({ ready: 'Ready', blocked: 'Needs setup', unknown: 'Not observed', sign_in: 'Sign in' })[check.status]}</Text></View></View><Text style={s.message}>{check.message}</Text>{check.action && check.status !== 'ready' && <Text selectable style={s.small}>{check.action}</Text>}{check.status !== 'ready' && ['account', 'chat', 'crawler', 'dragon'].includes(check.id) && button(check.id === 'dragon' ? 'Open review & practice' : check.id === 'crawler' ? 'Open web capture' : check.id === 'account' ? 'Sign in through AI chat' : 'Inspect AI models', () => router.push((check.id === 'dragon' ? '/crawler?pane=review' : check.id === 'crawler' ? '/crawler' : check.id === 'chat' ? '/ai-models' : '/jeeves-chat') as never))}</View>)}
      {!snapshot && !busy && <Text style={s.message}>Start the application, then check again. The instructions remain available if the backend is offline.</Text>}
    </View><View style={[s.column, s.card]}><Text style={s.heading}>First installation</Text><Text style={s.small}>These commands run on your host. This page does not start services or change credentials.</Text>
      {COMMANDS.map(item => <View key={item.title} style={s.check}><Text style={s.label}>{item.title}</Text><Text style={s.message}>{item.text}</Text><Text selectable style={s.code}>{item.command}</Text>{button('Copy command', () => { void Clipboard.setStringAsync(item.command).then(() => setNotice('Command copied. Run it in your host terminal.')).catch(() => setNotice('Select and copy the command text.')); })}</View>)}
      <Text style={s.small}>Use a trained local model or a configured approved provider. Keep credentials in host configuration. Check Docker is installed and its daemon is running when using the container installer.</Text>
    </View></View>
    <View style={s.card}><View style={s.row}><Ionicons name="compass-outline" size={24} color={colors.accent} /><Text style={s.heading}>Choose your next step</Text></View><Text style={s.message}>AI chat uses canonical conversation history. Web capture uses an explicit bounded queue and keeps captured material unreviewed until a separate review is completed.</Text><View style={s.row}>{button('Open AI chat', () => router.push('/jeeves-chat' as never))}{button('Open web capture', () => router.push('/crawler' as never))}{button('Open game studio', () => router.push('/game-learning' as never))}{button('Connection settings', () => router.push('/settings/api' as never))}</View></View>
    {snapshot && button('Copy readiness summary', () => { if (snapshot.accountEpoch !== getAuthEpoch()) { setNotice('Your account changed. Check readiness before copying a new summary.'); return; } void Clipboard.setStringAsync(JSON.stringify({ observed_at: new Date(snapshot.observedAt).toISOString(), checks: snapshot.checks.map(({ id, status, message }) => ({ id, status, message })) }, null, 2)).then(() => setNotice('Readiness summary copied. It contains no credentials.')).catch(() => setNotice('Clipboard is unavailable.')); })}
    {!!notice && <Text accessibilityLiveRegion="polite" style={s.small}>{notice}</Text>}
  </ScrollView></SafeAreaView>;
}
