/**
 * Cockpit console: command line + suggestion chips + newest-first transcript.
 * Presentational — the parent owns the transcript and the network call.
 */
import React from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';
import { checkCommand, COCKPIT_SUGGESTIONS, type ConsoleEntry } from '../cockpit';
import { recallCommand } from '../cockpitScreen';
import { Banner, Button, Card, Chip, SectionTitle, StatusPill } from './primitives';
import { C } from './theme';

export interface CockpitConsoleProps {
  entries: ConsoleEntry[];
  busy?: boolean;
  onSubmit: (command: string) => void;
  onClear?: () => void;
  initialCommand?: string;
  /** Clock for relative timestamps (injected for pure rendering). */
  now?: number;
  testID?: string;
}

export function ago(at: number, now: number): string {
  const s = Math.max(0, Math.round((now - at) / 1000));
  if (s < 5) return 'just now';
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.round(m / 60)}h ago`;
}

export default function CockpitConsole({ entries, busy = false, onSubmit, onClear, initialCommand = '', now = Date.now(), testID }: CockpitConsoleProps) {
  const [command, setCommand] = React.useState(initialCommand);
  const [touched, setTouched] = React.useState(false);
  const [cursor, setCursor] = React.useState(-1);
  const check = checkCommand(command);
  const showError = touched && !!command.trim() && !check.ok;
  const history = React.useMemo(() => entries.map((e) => e.command), [entries]);

  const submit = () => {
    setTouched(true);
    if (!check.ok || busy) return;
    onSubmit(check.command);
    setCommand('');
    setTouched(false);
    setCursor(-1);
  };

  const onKey = (e: any) => {
    const key = e?.nativeEvent?.key;
    if (key !== 'ArrowUp' && key !== 'ArrowDown') return;
    const r = recallCommand(history, cursor, key === 'ArrowUp' ? 1 : -1);
    setCursor(r.cursor);
    setCommand(r.command);
  };

  return (
    <View testID={testID}>
      <Card label="Cockpit console">
        <SectionTitle hint="Server is authoritative; obvious mistakes are caught here first.">Cockpit console</SectionTitle>
        <View style={st.row}>
          <Text style={st.prompt} importantForAccessibility="no">›</Text>
          <TextInput
            testID="console-input"
            value={command}
            onChangeText={(v) => { setCommand(v); setCursor(-1); }}
            onSubmitEditing={submit}
            onKeyPress={onKey}
            onBlur={() => setTouched(true)}
            placeholder="STATUS · COMPOSE <vision> · BIND ERA soulslike"
            placeholderTextColor={C.dim}
            autoCapitalize="none"
            autoCorrect={false}
            accessibilityLabel="Cockpit command"
            accessibilityHint="Press enter to send; arrow up recalls earlier commands"
            style={st.input}
            editable={!busy}
          />
          <Button label="Send" onPress={submit} busy={busy} disabled={!check.ok} compact testID="console-send" />
        </View>
        {showError ? <Banner tone="bad" testID="console-error">{check.error}</Banner> : null}
        <View style={st.chips} accessibilityRole="list" accessibilityLabel="Suggested commands">
          {COCKPIT_SUGGESTIONS.map((sug) => (
            <Chip
              key={sug.label}
              label={sug.label}
              role="button"
              a11yLabel={`${sug.label}: ${sug.hint}`}
              onPress={() => { setCommand(sug.command); setTouched(false); }}
              testID={`console-suggest-${sug.label.toLowerCase().replace(/\s+/g, '-')}`}
            />
          ))}
        </View>
      </Card>
      <Card label="Console transcript">
        <View style={st.head}>
          <SectionTitle hint={entries.length ? `${entries.length} command${entries.length === 1 ? '' : 's'}` : undefined}>Transcript</SectionTitle>
          {entries.length && onClear ? <Button label="Clear" tone="ghost" compact onPress={onClear} testID="console-clear" /> : null}
        </View>
        {entries.length === 0 ? (
          <Text style={st.empty}>No commands yet. Try STATUS to see the current tensor, ledger and archetype.</Text>
        ) : (
          <View accessibilityRole="list" accessibilityLiveRegion="polite">
            {entries.map((e) => (
              <View
                key={e.id}
                style={st.entry}
                accessibilityLabel={`${e.command}: ${e.ok ? 'ok' : 'failed'}, ${e.summary}`}
                testID={`console-entry-${e.id}`}
              >
                <View style={st.entryHead}>
                  <Text style={st.cmd} selectable>› {e.command}</Text>
                  <StatusPill tone={e.ok ? 'ok' : 'bad'} label={e.ok ? 'ok' : 'failed'} />
                </View>
                <Text style={[st.summary, !e.ok && { color: C.red }]} selectable>{e.summary}</Text>
                <Text style={st.when}>{ago(e.at, now)}</Text>
              </View>
            ))}
          </View>
        )}
      </Card>
    </View>
  );
}

const st = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 },
  prompt: { color: C.green, fontSize: 18, fontWeight: '800' },
  input: {
    flex: 1, minHeight: 44, borderWidth: 1, borderColor: C.borderStrong, borderRadius: 10, paddingHorizontal: 12,
    color: C.textStrong, backgroundColor: C.cardAlt, fontFamily: 'monospace', fontSize: 14,
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap' },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  empty: { color: C.mute, fontSize: 13 },
  entry: { borderTopWidth: 1, borderTopColor: C.border, paddingVertical: 10 },
  entryHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  cmd: { color: C.textStrong, fontFamily: 'monospace', fontSize: 13, flexShrink: 1 },
  summary: { color: C.text, fontSize: 13, marginTop: 4 },
  when: { color: C.dim, fontSize: 11, marginTop: 2 },
});
