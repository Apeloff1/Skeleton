/**
 * Cockpit tab — live SNAPSHOT readout, command line (commands.ts validate),
 * and history rows with diffSnapshots change labels.
 */
import React from 'react';
import { ActivityIndicator, StyleSheet, Text, TextInput, View } from 'react-native';
import { Banner, Button, Card, Chip, SectionTitle, StatusPill } from '../../skeletonForge/components/primitives';
import { C } from '../../skeletonForge/components/theme';
import {
  COCKPIT_QUICK_COMMANDS,
  historyA11yLabel,
  summarizeSnapshot,
  validationMessage,
  type HistoryEntry,
} from '../cockpitSummary';
import type { CockpitSnapshot } from '../types';

export interface CockpitPanelProps {
  snapshot: CockpitSnapshot | null;
  entries: HistoryEntry[];
  loading: boolean;
  busy: boolean;
  error: string | null;
  eraIds?: string[];
  onRefresh: () => void;
  onSubmit: (command: string) => void;
  onClearHistory?: () => void;
  testID?: string;
}

export default function CockpitPanel({
  snapshot,
  entries,
  loading,
  busy,
  error,
  eraIds,
  onRefresh,
  onSubmit,
  onClearHistory,
  testID,
}: CockpitPanelProps) {
  const [command, setCommand] = React.useState('');
  const [touched, setTouched] = React.useState(false);
  const summary = React.useMemo(() => summarizeSnapshot(snapshot), [snapshot]);
  const localError = touched && command.trim() ? validationMessage(command, eraIds) : null;
  const canSend = !!command.trim() && !localError && !busy;

  const submit = React.useCallback(() => {
    setTouched(true);
    const line = command.trim();
    if (!line || validationMessage(line, eraIds) || busy) return;
    onSubmit(line);
    setCommand('');
    setTouched(false);
  }, [command, eraIds, busy, onSubmit]);

  return (
    <View testID={testID ?? 'operator-cockpit'}>
      <SectionTitle hint="POST /api/skeleton/cockpit · SNAPSHOT">🎛 Cockpit</SectionTitle>

      <Card testID="operator-cockpit-snapshot" label="Live snapshot">
        <View style={st.head}>
          <Text style={st.lead}>Live operator context from the engine cockpit.</Text>
          <Button
            label="Refresh"
            tone="secondary"
            compact
            onPress={onRefresh}
            busy={loading && !busy}
            disabled={busy}
            testID="operator-cockpit-refresh"
            a11yHint="Send SNAPSHOT to refresh the live readout"
          />
        </View>
        {loading && !summary ? (
          <ActivityIndicator color={C.accent} style={{ marginVertical: 12 }} accessibilityLabel="Loading snapshot" />
        ) : null}
        {error ? <Banner tone="bad" testID="operator-cockpit-error">{error}</Banner> : null}
        {!loading && !error && !summary ? (
          <Text style={st.empty} testID="operator-cockpit-empty">
            No snapshot yet. Tap Refresh or send SNAPSHOT.
          </Text>
        ) : null}
        {summary ? (
          <View accessibilityLabel={`Snapshot era ${summary.era}`}>
            <Fact k="Era" v={summary.era} />
            <Fact k="Fingerprint" v={summary.fingerprint} />
            <Fact k="Dominant" v={summary.dominant} />
            <Fact k="Axes" v={summary.axesPreview} />
            <Fact k="Blend" v={summary.blend} />
            <Fact k="Generation" v={summary.generation} />
            <Fact k="Archetype" v={summary.archetype} />
            <Fact k="Oracle" v={summary.oracle} />
            <Fact k="Helix" v={summary.helix} />
            <Fact k="Ledger" v={summary.ledger} />
            <Fact k="Composition" v={summary.composition} />
            <Fact k="Engine history" v={String(summary.historyCount)} />
          </View>
        ) : null}
      </Card>

      <Card testID="operator-cockpit-command" label="Command line">
        <View style={st.row}>
          <Text style={st.prompt} importantForAccessibility="no">
            ›
          </Text>
          <TextInput
            testID="operator-cockpit-input"
            value={command}
            onChangeText={setCommand}
            onSubmitEditing={submit}
            onBlur={() => setTouched(true)}
            placeholder="SNAPSHOT · BIND ERA soulslike · ROLL ORACLE"
            placeholderTextColor={C.dim}
            autoCapitalize="none"
            autoCorrect={false}
            accessibilityLabel="Cockpit command"
            accessibilityHint="Validated locally, then sent via POST /api/skeleton/cockpit"
            style={st.input}
            editable={!busy}
          />
          <Button
            label="Send"
            onPress={submit}
            busy={busy}
            disabled={!canSend}
            compact
            testID="operator-cockpit-send"
          />
        </View>
        {localError ? <Banner tone="bad" testID="operator-cockpit-validation">{localError}</Banner> : null}
        <View style={st.chips} accessibilityRole="list" accessibilityLabel="Suggested cockpit commands">
          {COCKPIT_QUICK_COMMANDS.map((sug) => (
            <Chip
              key={sug.label}
              label={sug.label}
              role="button"
              a11yLabel={`${sug.label}: ${sug.hint}`}
              onPress={() => {
                setCommand(sug.command);
                setTouched(false);
              }}
              testID={`operator-cockpit-suggest-${sug.label.toLowerCase().replace(/\s+/g, '-')}`}
            />
          ))}
        </View>
      </Card>

      <Card testID="operator-cockpit-history" label="Command history">
        <View style={st.head}>
          <SectionTitle hint={entries.length ? `${entries.length} command${entries.length === 1 ? '' : 's'}` : undefined}>
            History
          </SectionTitle>
          {entries.length && onClearHistory ? (
            <Button label="Clear" tone="ghost" compact onPress={onClearHistory} testID="operator-cockpit-clear" />
          ) : null}
        </View>
        {entries.length === 0 ? (
          <Text style={st.empty} testID="operator-cockpit-history-empty">
            No commands yet. Try SNAPSHOT to load the tensor, ledger and archetype.
          </Text>
        ) : (
          <View accessibilityRole="list" accessibilityLiveRegion="polite">
            {entries.map((e) => (
              <View
                key={e.id}
                style={st.entry}
                accessibilityLabel={historyA11yLabel(e)}
                testID={`operator-cockpit-entry-${e.id}`}
              >
                <View style={st.entryHead}>
                  <Text style={st.cmd} selectable>
                    › {e.command}
                  </Text>
                  <StatusPill tone={e.ok ? 'ok' : 'bad'} label={e.ok ? 'ok' : 'failed'} />
                </View>
                <Text style={[st.summary, !e.ok && { color: C.red }]} selectable>
                  {e.summary}
                </Text>
                {e.changes.length ? (
                  <Text style={st.changes} testID={`operator-cockpit-changes-${e.id}`}>
                    {e.changes.map((c) => `· ${c}`).join('\n')}
                  </Text>
                ) : null}
              </View>
            ))}
          </View>
        )}
      </Card>
    </View>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <View style={st.fact}>
      <Text style={st.k}>{k}</Text>
      <Text style={st.v}>{v}</Text>
    </View>
  );
}

const st = StyleSheet.create({
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 8 },
  lead: { color: C.mute, fontSize: 13, flex: 1 },
  empty: { color: C.mute, fontSize: 13, marginVertical: 8 },
  fact: { marginBottom: 8 },
  k: { color: C.dim, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  v: { color: C.text, fontSize: 14 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 },
  prompt: { color: C.green, fontSize: 18, fontWeight: '800' },
  input: {
    flex: 1,
    minHeight: 44,
    borderWidth: 1,
    borderColor: C.borderStrong,
    borderRadius: 10,
    paddingHorizontal: 12,
    color: C.textStrong,
    backgroundColor: C.cardAlt,
    fontFamily: 'monospace',
    fontSize: 14,
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap' },
  entry: { borderTopWidth: 1, borderTopColor: C.border, paddingVertical: 10 },
  entryHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  cmd: { color: C.textStrong, fontFamily: 'monospace', fontSize: 13, flexShrink: 1 },
  summary: { color: C.text, fontSize: 13, marginTop: 4 },
  changes: { color: C.mute, fontSize: 12, marginTop: 6, lineHeight: 18, fontFamily: 'monospace' },
});
