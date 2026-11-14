import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, SafeAreaView, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Clipboard from 'expo-clipboard';
import { readAppReadiness, type AppReadiness } from '../../product/appReadinessClient';
import s, { colors } from './AppSetupWorkspace.styles';
import { getAuthEpoch, subscribeAuthChanges } from '../../auth/gameforgeAuth';
import { API_BASE, nativeBackendConfigurationIssue } from '../../utils/apiBase';

const COMMANDS = [
  { title: 'Launch Jeeves offline desktop', command: 'python scripts/launch_jeeves_desktop.py', text: 'Open the independent native Jeeves workbench on your computer. Select the installed GGUF and approved private SQLite state. This runs local inference without an external provider or network service; it does not replace protected canonical backend qualification for the mobile client.' },
  { title: 'Create Jeeves local model manifest', command: 'python scripts/build_jeeves_local_manifest.py --model /ABSOLUTE/OWNED_MODEL.gguf --executable /ABSOLUTE/llama-cli --output /ABSOLUTE/jeeves.json --profile qwen3-completion-chat', text: 'Use an already-owned licensed GGUF and compatible real llama.cpp executable. This creates a digest-pinned, read-only deployment identity named jeeves. It does not download weights or pretend that Jeeves was newly trained.' },
  { title: 'Execute a real local model completion', command: 'python scripts/install_ai_chat.py --deployment /ABSOLUTE/jeeves.json --live-local', text: 'Runs the pinned local model process on your host; a passing result must include a real bound local output receipt. This proves host inference only, not protected app readiness.' },
  { title: 'Configure Jeeves as the only local primary AI', command: 'python scripts/install_ai_chat.py --deployment /ABSOLUTE/jeeves.json --apply', text: 'Creates a private Compose configuration with local-only engine and backend, model_id=jeeves, no hosted fallback, and mandatory protected inference guard. For an existing private .env, explicitly add --force.' },
  { title: 'Start Jeeves, the backend and storage', command: 'python scripts/install_ai_chat.py --deployment /ABSOLUTE/jeeves.json --apply --force --start', text: 'Starts the local model stack with pinned read-only mounts. Docker startup does not mean an AI answered; the trusted local tokenizer, reviewer and canonical writer bootstrap are required.' },
  { title: 'Verify a genuine local-only Jeeves conversation', command: 'python scripts/ai_chat_installed_smoke.py --base-url https://YOUR_BACKEND_HOST --login-email owner@example.com --exercise', text: 'Checks one actual authenticated turn using only provider_id=local and model_id=jeeves, verifies local provider receipts, durable assistant persistence and exact-key replay. No remote model fallback.' },
  { title: 'Recover a saved reply without generating again', command: 'python scripts/ai_chat_installed_smoke.py --base-url https://YOUR_BACKEND_HOST --login-email owner@example.com --recover-thread THREAD_ID --recover-request REQUEST_ID', text: 'Reads the original turn and its local provider receipt only. A dropped connection must never cause a duplicate model run or a switch to another model.' },
  { title: 'Build a connected Jeeves Android client', command: 'cd frontend && EXPO_PUBLIC_BACKEND_URL=https://YOUR_BACKEND_HOST npx eas build --profile apk --platform android', text: 'The local GGUF runs on your computer/server, NOT inside the phone. The phone connects to your own authenticated HTTPS backend, never to an external model provider.' },
  { title: 'Inspect the protected runtime', command: 'python -m skeleton app doctor --live --studio --json', text: 'Check storage, engine, local model, protected tokenizer/snapshot/reviewer and device prerequisites individually. Healthy HTTP is not model inference.' },
  { title: 'Optional explicit model acquisition', command: 'python scripts/provision_local_ai.py --help', text: 'Model acquisition is separate from inference. You may supply already-owned files for completely offline setup. Downloads require explicit operator consent and do not make the model active.' },
];
export default function AppSetupWorkspace() {
  const router = useRouter();
  const [snapshot, setSnapshot] = useState<AppReadiness | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const request = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    request.current?.abort(); const current = new AbortController(); request.current = current; setBusy(true); setSnapshot(null); setError('');
    try { const value = await readAppReadiness(current.signal); if (!current.signal.aborted && value.accountEpoch === getAuthEpoch()) setSnapshot(value); }
    catch { if (!current.signal.aborted) setError('READINESS_UNOBSERVED: Services could not be verified. Setup remains available; run the host doctor command and retry.'); }
    finally { if (request.current === current) setBusy(false); }
  }, []);
  useEffect(() => { void refresh(); return () => request.current?.abort(); }, [refresh]);
  useEffect(() => subscribeAuthChanges(() => {
    request.current?.abort(); setSnapshot(null); setBusy(false);
    setError('ACCOUNT_CHANGED: Your account changed. Check readiness again for the current account.');
  }), []);
  const button = (label: string, onPress: () => void, disabled = false) => <TouchableOpacity accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={[s.button, disabled && s.disabled]}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
  return <SafeAreaView style={s.safe}><ScrollView contentContainerStyle={s.page} keyboardShouldPersistTaps="handled">
    <View style={s.row}><View style={s.grow}><Text style={s.eyebrow}>SKELETON · GET STARTED</Text><Text style={s.title}>Make the app ready</Text></View>{button('Home', () => router.push('/product' as never))}</View>
    <Text style={s.subtitle}>Check your local Jeeves model, protected engine and storage. Multimodal capture is advisory, never a second primary model or cloud fallback. You can read this guide before signing in.</Text>
    <View style={s.twoColumns}><View style={[s.column, s.card]}>
      <View style={s.row}><Text style={[s.heading, s.grow]}>Observed readiness</Text>{busy && <ActivityIndicator color={colors.accent} />}{button(busy ? 'Checking…' : 'Check again', () => void refresh(), busy)}</View>
      <Text style={s.small}>{snapshot ? `Checked ${new Date(snapshot.observedAt).toLocaleTimeString()}. Each capability is checked separately.` : 'No readiness verdict until the services respond.'}</Text>
      {nativeBackendConfigurationIssue() ? <Text accessibilityRole="alert" style={s.error}>{nativeBackendConfigurationIssue()}</Text> : null}
      <Text selectable style={s.small}>Application API: {API_BASE || 'Not configured in this build'}</Text>
      {error ? <Text accessibilityRole="alert" style={s.error}>{error}</Text> : null}
      {snapshot?.checks.map(check => <View key={check.id} style={s.check}><View style={s.row}><Text style={[s.label, s.grow]}>{check.label}</Text><View style={s.badge}><Text style={[s.badgeText, check.status === 'ready' && s.success]}>{({ ready: 'Ready', blocked: 'Needs setup', unknown: 'Not observed', sign_in: 'Sign in' })[check.status]}</Text></View></View><Text style={s.message}>{check.message}</Text>{check.action && check.status !== 'ready' && <Text selectable style={s.small}>{check.action}</Text>}{check.status !== 'ready' && ['account', 'chat', 'crawler', 'dragon'].includes(check.id) && button(check.id === 'dragon' ? 'Open review & practice' : check.id === 'crawler' ? 'Open web capture' : check.id === 'account' ? 'Sign in through AI chat' : 'Inspect AI models', () => router.push((check.id === 'dragon' ? '/crawler?pane=review' : check.id === 'crawler' ? '/crawler' : check.id === 'chat' ? '/ai-models' : '/jeeves-chat') as never))}</View>)}
      {!snapshot && !busy && <Text style={s.message}>Start the application, then check again. The instructions remain available if the backend is offline.</Text>}
    </View><View style={[s.column, s.card]}><Text style={s.heading}>First installation</Text><Text style={s.small}>These commands run on your host. This page does not start services or change credentials.</Text>
      {COMMANDS.map(item => <View key={item.title} style={s.check}><Text style={s.label}>{item.title}</Text><Text style={s.message}>{item.text}</Text><Text selectable style={s.code}>{item.command}</Text>{button('Copy command', () => { void Clipboard.setStringAsync(item.command).then(() => setNotice('Command copied. Run it in your host terminal.')).catch(() => setNotice('Select and copy the command text.')); })}</View>)}
      <Text style={s.small}>Jeeves chat uses one pinned local model only. Image/audio/video and web knowledge are advisory context, not alternative AI providers. A trusted protected inference bootstrap is required for real application chat.</Text>
    </View></View>
    <View style={s.card}><View style={s.row}><Ionicons name="compass-outline" size={24} color={colors.accent} /><Text style={s.heading}>Choose your next step</Text></View><Text style={s.message}>Local Jeeves chat uses canonical conversation history and offline model execution. Web and multimodal captures remain untrusted advisory evidence until separate review.</Text><View style={s.row}>{button('Open AI chat', () => router.push('/jeeves-chat' as never))}{button('Open web capture', () => router.push('/crawler' as never))}{button('Open game studio', () => router.push('/game-learning' as never))}{button('Connection settings', () => router.push('/settings/api' as never))}</View></View>
    {snapshot && button('Copy readiness summary', () => { if (snapshot.accountEpoch !== getAuthEpoch()) { setNotice('Your account changed. Check readiness before copying a new summary.'); return; } void Clipboard.setStringAsync(JSON.stringify({ observed_at: new Date(snapshot.observedAt).toISOString(), checks: snapshot.checks.map(({ id, status, message }) => ({ id, status, message })) }, null, 2)).then(() => setNotice('Readiness summary copied. It contains no credentials.')).catch(() => setNotice('Clipboard is unavailable.')); })}
    {!!notice && <Text accessibilityLiveRegion="polite" style={s.small}>{notice}</Text>}
  </ScrollView></SafeAreaView>;
}
