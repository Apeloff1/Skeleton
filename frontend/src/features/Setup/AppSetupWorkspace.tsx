import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Platform, SafeAreaView, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Clipboard from 'expo-clipboard';
import { readAppReadiness, type AppReadiness } from '../../product/appReadinessClient';
import s, { colors } from './AppSetupWorkspace.styles';
import { getAuthEpoch, subscribeAuthChanges } from '../../auth/gameforgeAuth';
import { API_BASE, nativeBackendConfigurationIssue } from '../../utils/apiBase';
import { HOST_SHELLS, HOST_SHELL_COPY, commandsFor, detectHostShell, type HostShell } from './setupCommands';

export default function AppSetupWorkspace() {
  const router = useRouter();
  const [snapshot, setSnapshot] = useState<AppReadiness | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const request = useRef<AbortController | null>(null);
  const [shell, setShell] = useState<HostShell>(() => detectHostShell(Platform.OS, typeof navigator === 'undefined' ? null : navigator as never));
  const commands = commandsFor(shell);
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
      <View accessibilityRole="radiogroup" accessibilityLabel="Host computer" style={s.row} testID="setup-host-shell">{HOST_SHELLS.map(option => { const selected = option.id === shell; return <TouchableOpacity key={option.id} accessibilityRole="radio" accessibilityState={{ checked: selected, selected }} accessibilityLabel={option.label} accessibilityHint={option.hint} onPress={() => setShell(option.id)} style={[s.button, selected && { borderColor: colors.accent, backgroundColor: '#241b3a' }]} testID={'setup-host-' + option.id}><Text style={[s.buttonText, selected && { color: colors.text }]}>{selected ? '● ' : '○ '}{option.label}</Text></TouchableOpacity>; })}</View>
      <Text accessibilityLiveRegion="polite" style={s.small} testID="setup-host-copy">{HOST_SHELL_COPY[shell]}</Text>
      {commands.map(item => <View key={item.title} style={s.check}><Text style={s.label}>{item.title}</Text><Text style={s.message}>{item.text}</Text>{item.command ? <><Text selectable style={s.code} accessibilityLabel={item.title + ' command: ' + item.command}>{item.command}</Text>{button('Copy command', () => { const command = item.command as string; void Clipboard.setStringAsync(command).then(() => setNotice('Command copied. Run it in your host terminal.')).catch(() => setNotice('Select and copy the command text.')); })}</> : <Text style={s.small} testID="setup-command-unsupported">Not available in this shell.</Text>}{item.note ? <Text style={s.small}>{item.note}</Text> : null}</View>)}
      <Text style={s.small}>Jeeves chat uses one pinned local model only. Image/audio/video and web knowledge are advisory context, not alternative AI providers. A trusted protected inference bootstrap is required for real application chat.</Text>
    </View></View>
    <View style={s.card}><View style={s.row}><Ionicons name="compass-outline" size={24} color={colors.accent} /><Text style={s.heading}>Choose your next step</Text></View><Text style={s.message}>Local Jeeves chat uses canonical conversation history and offline model execution. Web and multimodal captures remain untrusted advisory evidence until separate review.</Text><View style={s.row}>{button('Open AI chat', () => router.push('/jeeves-chat' as never))}{button('Open web capture', () => router.push('/crawler' as never))}{button('Open game studio', () => router.push('/game-learning' as never))}{button('Connection settings', () => router.push('/settings/api' as never))}</View></View>
    {snapshot && button('Copy readiness summary', () => { if (snapshot.accountEpoch !== getAuthEpoch()) { setNotice('Your account changed. Check readiness before copying a new summary.'); return; } void Clipboard.setStringAsync(JSON.stringify({ observed_at: new Date(snapshot.observedAt).toISOString(), checks: snapshot.checks.map(({ id, status, message }) => ({ id, status, message })) }, null, 2)).then(() => setNotice('Readiness summary copied. It contains no credentials.')).catch(() => setNotice('Clipboard is unavailable.')); })}
    {!!notice && <Text accessibilityLiveRegion="polite" style={s.small}>{notice}</Text>}
  </ScrollView></SafeAreaView>;
}
