/**
 * /ecosystem — Full-stack studio surface.
 * Create a brief, run the IntegratedStudio pipeline, and inspect the sealed result.
 */
import React from 'react';
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity, ScrollView, ActivityIndicator, SafeAreaView,
} from 'react-native';
import { useRouter } from 'expo-router';
import { buildGame, ecosystemHealth, listSessions, type EcosystemSession } from '../src/services/ecosystemClient';

export default function EcosystemScreen() {
  const router = useRouter();
  const [brief, setBrief] = React.useState('A compact era-bound platformer with a final boss');
  const [era, setEra] = React.useState('ash');
  const [loading, setLoading] = React.useState(false);
  const [result, setResult] = React.useState<EcosystemSession | null>(null);
  const [health, setHealth] = React.useState<Record<string, unknown> | null>(null);
  const [sessions, setSessions] = React.useState<EcosystemSession[]>([]);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    try {
      const [h, list] = await Promise.all([ecosystemHealth(), listSessions(10)]);
      setHealth(h);
      setSessions(list.sessions || []);
    } catch {
      setError('health unavailable');
    }
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const onBuild = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await buildGame(brief, era);
      setResult(r);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'build failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.root}>
      <ScrollView contentContainerStyle={styles.body}>
        <Text style={styles.title}>Ecosystem Studio</Text>
        <Text style={styles.sub}>Full-stack pipeline: brief → session → sealed Godot emit</Text>

        <TextInput
          style={styles.input}
          value={brief}
          onChangeText={setBrief}
          placeholder="Game brief"
          placeholderTextColor="#666"
          multiline
        />
        <TextInput
          style={styles.inputSmall}
          value={era}
          onChangeText={setEra}
          placeholder="era"
          placeholderTextColor="#666"
        />

        <TouchableOpacity style={styles.btn} onPress={onBuild} disabled={loading}>
          {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnText}>Build</Text>}
        </TouchableOpacity>

        {error ? <Text style={styles.err}>{error}</Text> : null}

        {result ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{result.sealed ? 'Sealed' : 'Incomplete'}</Text>
            <Text style={styles.cardLine}>session {result.session_id}</Text>
            <Text style={styles.cardLine}>era {result.era} · rooms {result.rooms ?? '-'} · tier {result.tier ?? '-'}</Text>
            <Text style={styles.cardLine}>godot files {result.godot_count ?? 0}</Text>
          </View>
        ) : null}

        <Text style={styles.section}>Health</Text>
        <Text style={styles.mono}>{health ? JSON.stringify(health, null, 2) : '...'}</Text>

        <Text style={styles.section}>Recent sessions</Text>
        {sessions.map((s) => (
          <Text key={s.session_id} style={styles.cardLine}>
            {s.session_id} · {s.status} · {s.era}
          </Text>
        ))}

        <TouchableOpacity onPress={() => router.back()}>
          <Text style={styles.back}>Back</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0A0A0A' },
  body: { padding: 20 },
  title: { color: '#E5E5E5', fontSize: 24, fontWeight: '700' },
  sub: { color: '#A3A3A3', marginBottom: 16 },
  input: { backgroundColor: '#171717', color: '#E5E5E5', borderRadius: 12, padding: 12, minHeight: 80, marginBottom: 8 },
  inputSmall: { backgroundColor: '#171717', color: '#E5E5E5', borderRadius: 12, padding: 12, marginBottom: 12 },
  btn: { backgroundColor: '#8B5CF6', borderRadius: 12, padding: 14, alignItems: 'center' },
  btnText: { color: '#fff', fontWeight: '700' },
  err: { color: '#F87171', marginTop: 12 },
  card: { marginTop: 16, padding: 14, backgroundColor: '#171717', borderRadius: 12 },
  cardTitle: { color: '#A78BFA', fontWeight: '700', marginBottom: 6 },
  cardLine: { color: '#D4D4D4', marginTop: 2 },
  section: { color: '#A3A3A3', marginTop: 20, marginBottom: 6, fontWeight: '600' },
  mono: { color: '#A3A3A3', fontSize: 12 },
  back: { color: '#8B5CF6', marginTop: 24 },
});
