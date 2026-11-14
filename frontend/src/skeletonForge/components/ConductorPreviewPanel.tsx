/** Archival conductor: a read-only, explicit preview of the seven-stage planner. */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { errorText, previewHistoricalConductor, type ConductorPreviewResult } from '../client';
import { Button, Chip } from './primitives';
import { C } from './theme';

const FAMILIES = ['platformer', 'puzzle', 'rpg', 'shooter', 'strategy', 'racing', 'adventure', 'sandbox'] as const;

export default function ConductorPreviewPanel({ vision }: { vision: string }) {
  const [open, setOpen] = React.useState(false);
  const [genre, setGenre] = React.useState<string>('platformer');
  const [result, setResult] = React.useState<ConductorPreviewResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [working, setWorking] = React.useState(false);
  const active = React.useRef<AbortController | null>(null);

  React.useEffect(() => () => active.current?.abort(), []);
  const preview = React.useCallback(async () => {
    active.current?.abort();
    const ctrl = new AbortController();
    active.current = ctrl;
    setResult(null);
    setError(null);
    const pitch = vision.trim();
    if (!pitch) {
      setError('Add a game vision before previewing the conductor.');
      return;
    }
    setWorking(true);
    try {
      const r = await previewHistoricalConductor({
        title: pitch.split(/[.!?\n]/)[0].trim().slice(0, 120) || 'Original game',
        pitch: pitch.slice(0, 4000),
        genre, pillars: ['gameplay', 'progression'],
      }, ctrl.signal);
      if (ctrl.signal.aborted) return;
      if (!r.ok || !r.data?.ok || !Array.isArray(r.data.completed) ||
          !Array.isArray(r.data.artifacts) || r.data.artifacts.length > 1000) {
        setError(r.ok ? 'Historical conductor rejected the design.' : errorText(r));
      } else {
        setResult(r.data);
      }
    } catch {
      if (!ctrl.signal.aborted) setError('Conductor preview is unavailable.');
    } finally {
      if (!ctrl.signal.aborted) setWorking(false);
    }
  }, [vision, genre]);

  return (
    <View style={styles.section} testID="q-conductor-preview">
      <Button
        label={open ? 'Hide historical seven-stage conductor' : 'Advanced: historical seven-stage conductor preview'}
        tone="secondary" compact testID="q-conductor-preview-toggle"
        onPress={() => {
          if (open) active.current?.abort();
          setOpen(!open);
          setResult(null);
          setError(null);
          setWorking(false);
        }}
      />
      {open ? (
        <View testID="q-conductor-preview-content">
          <Text style={styles.caption}>
            Preview only: vision → snowball → prototype → mass forge → world → cockpit → export.
            The output is a deterministic planning receipt, not a built or tested game.
          </Text>
          <Text style={styles.caption}>Choose one of eight original conductor families. Other creator genres remain available in the full questionnaire.</Text>
          <View style={styles.choices}>
            {FAMILIES.map((name) => (
              <Chip key={name} label={name} selected={genre === name}
                onPress={() => { active.current?.abort(); setGenre(name); setResult(null); setError(null); setWorking(false); }}
                testID={'q-conductor-genre-' + name} />
            ))}
          </View>
          <Button label="Run read-only seven-stage preview" onPress={() => { void preview(); }}
            busy={working} testID="q-conductor-preview-run" />
          {error ? <Text style={styles.caption} accessibilityLiveRegion="polite">{error}</Text> : null}
          {result ? (
            <View testID="q-conductor-preview-result">
              <Text style={styles.title}>Completed {result.completed.length}/7 stages · {result.artifact_count} artifacts · {result.byte_total} bytes</Text>
              <Text style={styles.caption}>{result.completed.join(' → ')}</Text>
              <Text style={styles.caption}>Read-only preview. Exported receipts require separate build, native playtest and release qualification.</Text>
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}
const styles = StyleSheet.create({
  section: { paddingVertical: 10, gap: 10 },
  title: { color: C.textStrong, fontWeight: '600', marginTop: 8 },
  caption: { color: C.dim, marginTop: 8, marginBottom: 4, fontSize: 12 },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginVertical: 6 },
});
