import React, { useState } from 'react';
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  authorizeCrawlAutomation, crawlRequestKey, getCrawl,
  type CrawlSession,
} from '../../src/product/crawlerClient';
import s, { colors as C } from './CrawlerWorkspace.styles';

type Props = {
  session: CrawlSession;
  canWrite: boolean;
  busy: boolean;
  run: (label: string, operation: (signal: AbortSignal) => Promise<CrawlSession>) => void;
  control: (action: 'pause' | 'resume' | 'cancel') => void;
  manual: () => void;
  refresh: () => void;
};

function Action({ label, press, disabled = false, primary = false }: {
  label: string; press: () => void; disabled?: boolean; primary?: boolean;
}) {
  return <TouchableOpacity accessibilityRole="button" accessibilityLabel={label}
    accessibilityState={{ disabled }} disabled={disabled} onPress={press}
    style={[s.button, primary && a.primary, disabled && s.disabled]}>
    <Text style={s.buttonText}>{label}</Text>
  </TouchableOpacity>;
}
function when(value?: string | null) {
  return value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString() : 'Not issued';
}
function human(value: string) { return value.replaceAll('_', ' '); }

/** The browser observes a finite server grant. It never schedules capture requests. */
export default function CrawlerAutomationPanel({ session, canWrite, busy, run, control, manual, refresh }: Props) {
  const [slices, setSlices] = useState('8');
  const [minutes, setMinutes] = useState('10');
  const [approved, setApproved] = useState(false);
  const [error, setError] = useState('');
  const grant = session.automation;
  const worker = session.worker;
  const caps = session.capabilities;
  const terminal = ['completed', 'cancelled', 'budget_exhausted', 'failed'].includes(session.status);
  const draining = worker?.active === true && (session.status === 'paused' || session.status === 'cancelled' || grant?.enabled === false);
  const controlsObserved = !!grant && !!worker && !!caps;
  const authorize = (enabled: boolean) => {
    const count = Number(slices), duration = Number(minutes);
    if (!/^\d+$/.test(slices) || count < 1 || count > 64 || !/^\d+$/.test(minutes) || duration < 1 || duration > 60) {
      setError('Choose 1–64 bounded slices and 1–60 minutes.'); return;
    }
    if (enabled && !approved) { setError('Confirm the finite automatic capture authorization first.'); return; }
    setError('');
    const key = crawlRequestKey(enabled ? 'automate' : 'stop-automation');
    let body: { expected_version: number; idempotency_key: string; enabled: boolean; max_slices: number; max_seconds: number } | null = null;
    run(enabled ? 'Authorizing finite automatic capture' : 'Stopping automatic continuation', async signal => {
      // The exact issued command survives an uncertain transport result. A state
      // conflict requires a fresh explicit action instead of overriding a stop.
      if (!body) {
        const current = await getCrawl(session.session_id, signal);
        body = { expected_version: current.version, idempotency_key: key, enabled, max_slices: count, max_seconds: duration * 60 };
      }
      return authorizeCrawlAutomation(session.session_id, body, signal);
    });
  };
  return <View style={s.card}>
    <View style={s.row}>
      <View style={[s.grow, { minWidth: 180 }]}><Text style={s.heading}>Capture controls</Text>
        <Text style={s.small}>Run on the server within your existing source and request limits.</Text></View>
      <View style={s.badge}><Text style={s.badgeText}>{human(session.status)}</Text></View>
    </View>
    <View style={a.metrics}>
      {[
        ['Requests', `${session.counters.requests} / ${session.limits.max_requests}`],
        ['Captured sources', `${session.counters.documents} / ${session.limits.max_documents}`],
        ['Pending URLs', String(session.frontier_count)],
        ['Failed requests', String(session.counters.failures)],
      ].map(([label, value]) => <View key={label} style={a.metric}><Text style={s.small}>{label}</Text><Text style={a.value}>{value}</Text></View>)}
    </View>
    <View style={a.stateBox} accessibilityLiveRegion="polite">
      <Ionicons name={draining ? 'pause-circle-outline' : worker?.active ? 'sync-outline' : 'information-circle-outline'} size={21} color={C.accent} />
      <View style={s.grow}><Text style={s.label}>{draining ? 'Stop requested; waiting for the worker to drain' : worker?.active ? 'A real capture worker is active' : grant?.enabled ? 'Automatic capture is authorized' : 'No automatic capture is authorized'}</Text>
        <Text style={s.small}>{worker?.active ? worker.local ? 'The current server owns its live lease.' : 'Another server owns its live lease.' : worker?.quiescent ? 'The worker is quiescent.' : controlsObserved ? 'The server has not confirmed a quiescent worker yet.' : 'Automatic worker state has not been observed from this server.'}</Text></View>
    </View>
    {worker?.confirmation === 'lease_fenced_physical_unconfirmed' && <Text style={s.small}>The previous lease is fenced. Physical worker exit has not been observed; recovery eligibility is determined by the server, not by this page.</Text>}
    {grant && <View style={a.grant}>
      <Text style={s.message}>Authorization: {human(grant.state)} · {grant.slices_started} / {grant.max_slices} slices started</Text>
      {grant.enabled && <Text style={s.small}>Expires {when(grant.expires_at)}{grant.next_run_at ? ` · next eligible run ${when(grant.next_run_at)}` : ''}</Text>}
      {!!grant.stop_reason && <Text style={s.small}>Stopped because: {human(grant.stop_reason)}</Text>}
    </View>}
    {!!session.stop_reason && <Text style={s.small}>Session: {human(session.stop_reason)}</Text>}
    <View style={s.row}>
      {caps?.can_pause && <Action label={draining ? 'Pause requested' : 'Pause capture'} disabled={busy || draining} press={() => control('pause')} />}
      {caps?.can_resume && <Action label="Resume capture" disabled={!canWrite || busy} press={() => control('resume')} />}
      {caps?.can_cancel && <Action label="Cancel remaining capture" disabled={busy} press={() => control('cancel')} />}
      <Action label="Refresh actual state" disabled={busy} press={refresh} />
    </View>
    {!controlsObserved ? <Text style={s.small}>This server has not exposed automatic capture controls. You can still use a supported manual slice.</Text> :
      !terminal && <View style={a.authorization}>
        <Text style={s.label}>Finite automatic run</Text>
        <View style={s.row}>
          <View style={a.field}><Text style={s.small}>Maximum slices (1–64)</Text><TextInput accessibilityLabel="Maximum automatic capture slices" value={slices} onChangeText={setSlices} keyboardType="number-pad" maxLength={2} style={a.input} editable={!busy} /></View>
          <View style={a.field}><Text style={s.small}>Time window (1–60 minutes)</Text><TextInput accessibilityLabel="Automatic capture authorization minutes" value={minutes} onChangeText={setMinutes} keyboardType="number-pad" maxLength={2} style={a.input} editable={!busy} /></View>
        </View>
        <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: approved, disabled: busy }} disabled={busy}
          onPress={() => setApproved(value => !value)} style={a.consent}>
          <Ionicons name={approved ? 'checkbox-outline' : 'square-outline'} size={23} color={C.accent} />
          <Text style={[s.message, s.grow]}>Continue automatically only within this time, slice and existing capture budget. Closing this page does not cancel the server grant.</Text>
        </TouchableOpacity>
        {!session.consent_current && <Text style={s.error}>Capture consent has expired. This session cannot receive a new run authorization.</Text>}
        <View style={s.row}>
          <Action label={grant?.enabled ? 'Replace finite authorization' : 'Run automatically within limits'} primary
            disabled={!canWrite || busy || !approved || !session.consent_current || caps?.can_automate !== true} press={() => authorize(true)} />
          {grant?.enabled && <Action label="Stop automatic continuation" disabled={busy} press={() => authorize(false)} />}
        </View>
      </View>}
    <View style={s.row}><Action label="Run one manual slice" disabled={!canWrite || busy || terminal || (caps ? !caps.can_run : !session.consent_current || session.status === 'running')} press={manual} /></View>
    <Text style={s.small}>Pause and cancel fence future requests and publication. A running network request may still need to drain. Captures remain unreviewed external material.</Text>
    {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
  </View>;
}
const a = StyleSheet.create({
  primary: { backgroundColor: '#29203e', borderColor: C.accent },
  metrics: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  metric: { minWidth: 120, flexGrow: 1, flexBasis: 140, borderWidth: 1, borderColor: C.edge, borderRadius: 12, padding: 14, gap: 5 },
  value: { color: C.text, fontSize: 24, fontWeight: '700' },
  stateBox: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, backgroundColor: C.bg, borderRadius: 10, padding: 14 },
  grant: { gap: 5 }, authorization: { borderTopWidth: 1, borderColor: C.edge, paddingTop: 16, gap: 12 },
  field: { flexGrow: 1, flexBasis: 180, minWidth: 0, gap: 7 },
  input: { minHeight: 44, borderWidth: 1, borderColor: C.edge, borderRadius: 9, color: C.text, backgroundColor: C.bg, padding: 12 },
  consent: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, minHeight: 44, paddingVertical: 8 },
});
