import React, { useState } from 'react';
import { ActivityIndicator, Text, TextInput, TouchableOpacity, useWindowDimensions, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SKELETON_API_BASE } from '../../utils/apiBase';
import { OfficeController, officeHeadline, type OfficeSnapshot } from './studioOfficeClient';
import styles, { colors } from './StudioOfficePanel.styles';

const controller = new OfficeController({ base: SKELETON_API_BASE });

function useOffice(): OfficeSnapshot {
  return React.useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
}

export default function StudioOfficePanel({ variant = 'full' }: { variant?: 'full' | 'compact' }) {
  const snapshot = useOffice();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const narrow = width < 760;
  const [watching, setWatching] = useState('');
  const headline = officeHeadline(snapshot);
  const headlineStyle = headline.tone === 'ok' ? styles.ok : headline.tone === 'degraded' ? styles.degraded : headline.tone === 'failed' || headline.tone === 'error' ? styles.failed : styles.body;

  const button = (label: string, onPress: () => void, disabled = false) => (
    <TouchableOpacity accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={styles.button}>
      <Text style={styles.buttonText}>{label}</Text>
    </TouchableOpacity>
  );

  return (
    <View style={styles.card}>
      <Text style={styles.eyebrow}>SKELETON · OFFICE</Text>
      <Text style={styles.title}>{variant === 'compact' ? 'Golden brief' : 'Cloud agent office'}</Text>
      <Text style={styles.muted}>
        Loopback forge charter. The ash-tunnels brief is the catalog entry: clear packs, spend salvage, playtest auto.
      </Text>
      <View style={[styles.row, narrow && styles.stack]}>
        <TextInput
          accessibilityLabel="Forge seal"
          autoCapitalize="none"
          autoCorrect={false}
          onChangeText={(value) => controller.setSeal(value)}
          placeholder="x-gf-seal"
          placeholderTextColor={colors.muted}
          secureTextEntry
          style={[styles.input, { flexGrow: 1 }]}
          value={snapshot.seal}
        />
        <TextInput
          accessibilityLabel="Tenant"
          autoCapitalize="none"
          onChangeText={(value) => controller.setTenant(value)}
          placeholder="tenant"
          placeholderTextColor={colors.muted}
          style={[styles.input, narrow ? { width: '100%' } : { width: 140 }]}
          value={snapshot.tenant}
        />
      </View>
      <View style={styles.row}>
        {button(snapshot.phase === 'loading' ? 'Running…' : 'Run ash-tunnels golden brief', () => void controller.startGolden(), snapshot.phase === 'loading')}
        {variant === 'full' ? button('Load charters', () => void controller.loadCharters()) : button('Open office', () => router.push('/office' as never))}
        {snapshot.run && snapshot.run.status === 'running' ? button('Cancel run', () => void controller.cancel()) : null}
        {snapshot.phase === 'loading' ? <ActivityIndicator color={colors.accent} /> : null}
      </View>
      <Text accessibilityRole={headline.tone === 'error' || headline.tone === 'failed' ? 'alert' : 'text'} accessibilityLiveRegion="polite" style={headlineStyle}>{headline.title}</Text>
      <Text style={styles.body}>{headline.detail}</Text>
      {snapshot.error && headline.tone !== 'error' ? <Text accessibilityRole="alert" style={styles.error}>{snapshot.error}</Text> : null}
      {variant === 'full' ? (
        <View style={[styles.columns, narrow && styles.stack]}>
          <View style={styles.column}>
            <Text style={styles.body}>Charters</Text>
            {snapshot.chartersPhase === 'loading' ? <Text style={styles.muted}>Loading charters…</Text> : null}
            {snapshot.chartersPhase === 'error' ? <Text style={styles.error}>Charters could not be loaded.</Text> : null}
            {snapshot.chartersPhase === 'ready' && snapshot.charters.length === 0 ? <Text style={styles.muted}>No charters returned.</Text> : null}
            {snapshot.chartersPhase === 'idle' ? <Text style={styles.muted}>Charters have not been loaded.</Text> : null}
            {snapshot.charters.map((charter) => (
              <View key={charter.charter_id} style={styles.charter}>
                <View style={styles.row}>
                  <Text style={[styles.body, { fontWeight: '700', flex: 1 }]}>{charter.charter_id}</Text>
                  <View style={styles.badge}><Text style={styles.badgeText}>{charter.autonomy}</Text></View>
                </View>
                <Text style={styles.muted}>{charter.mandate}</Text>
                <Text style={styles.muted}>Tools: {charter.tools.join(', ')} · {charter.budget.max_tool_calls} calls · {charter.budget.deadline_s}s</Text>
                {charter.charter_id === 'doctor' ? button('Run doctor', () => void controller.startCharter('doctor', { live: false })) : null}
              </View>
            ))}
          </View>
          <View style={styles.column}>
            <Text style={styles.body}>Live trace</Text>
            {snapshot.trace.length === 0 ? <Text style={styles.muted}>No tool steps yet.</Text> : snapshot.trace.map((line, index) => <Text key={`${index}-${line}`} style={styles.trace}>{line}</Text>)}
            <Text style={styles.body}>Job status</Text>
            <View style={[styles.row, narrow && styles.stack]}>
              <TextInput
                accessibilityLabel="Forge execution id"
                autoCapitalize="none"
                onChangeText={setWatching}
                placeholder="execution id"
                placeholderTextColor={colors.muted}
                style={[styles.input, { flexGrow: 1 }]}
                value={watching}
              />
              {button('Watch job', () => void controller.startCharter('job_watcher', { execution_id: watching.trim() }), !watching.trim())}
            </View>
            <Text style={styles.muted}>
              {snapshot.run?.result && typeof snapshot.run.result === 'object'
                ? `Heartbeat ${snapshot.run.heartbeat_seq ?? 0}. ${JSON.stringify({
                  status: snapshot.run.status,
                  code: snapshot.run.error?.code || snapshot.run.result.code || null,
                  godot_ran: snapshot.run.result.godot_ran,
                  core_loop_ok: snapshot.run.result.core_loop_ok,
                  degraded: snapshot.run.result.degraded,
                })}`
                : `Heartbeat ${snapshot.run?.heartbeat_seq ?? 0}.`}
            </Text>
          </View>
        </View>
      ) : (
        snapshot.trace.slice(-3).map((line, index) => <Text key={`${index}-${line}`} style={styles.trace}>{line}</Text>)
      )}
    </View>
  );
}
