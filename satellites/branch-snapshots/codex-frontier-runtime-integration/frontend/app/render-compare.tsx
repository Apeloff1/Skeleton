/**
 * /render-compare — 🖼️ Side-by-side Worldforge render compare (big-win e).
 * Pick a mode/layer for each pane and compare the two extreme-pixel renders side by side.
 */
import React from 'react';
import {
  View, Text, Image, ScrollView, TouchableOpacity, StyleSheet, SafeAreaView, useWindowDimensions, ActivityIndicator, Linking,
} from 'react-native';
import { useRouter } from 'expo-router';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const MODES = ['cartographic', 'globe', 'nasa', 'bloom', 'thematic'];

function renderUrl(mode: string, seed: number, master: boolean) {
  return `${BACKEND}/api/worldforge/render?mode=${mode}&seed=${seed}&size=64&master=${master ? 'true' : 'false'}`;
}

function Pane({ label, testID, defaultMode, seed, master }: { label: string; testID: string; defaultMode: string; seed: number; master: boolean }) {
  const { width } = useWindowDimensions();
  const [mode, setMode] = React.useState(defaultMode);
  const [nonce, setNonce] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const size = Math.min((width - 42) / 2, 220);
  return (
    <View testID={testID} style={[styles.pane, { width: size + 16 }]}>
      <Text style={styles.paneLabel}>Pane {label} {master ? '· 4K master' : '· preview'}</Text>
      <View style={{ width: size, height: size }}>
        <Image source={{ uri: renderUrl(mode, seed, master) + `&n=${nonce}` }}
          onLoadStart={() => setLoading(true)} onLoadEnd={() => setLoading(false)}
          style={{ width: size, height: size, borderRadius: 10, backgroundColor: '#0b1220' }} resizeMode="cover" />
        {loading && (
          <View testID={`${testID}-loader`} style={styles.loader}>
            <ActivityIndicator size="large" color="#93C5FD" />
            {master && <Text style={styles.loaderTxt}>Loading 4096px master…</Text>}
          </View>
        )}
      </View>
      <View style={styles.modeRow}>
        {MODES.map((m) => (
          <TouchableOpacity key={m} testID={`${testID}-mode-${m}`} onPress={() => { setMode(m); setNonce((n) => n + 1); }}
            style={[styles.modeChip, mode === m && styles.modeOn]}>
            <Text style={[styles.modeTxt, mode === m && styles.modeTxtOn]}>{m}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <TouchableOpacity testID={`${testID}-download`} onPress={() => Linking.openURL(renderUrl(mode, seed, true))} style={styles.dlBtn}>
        <Text style={styles.dlTxt}>⬇️ Download 4K master</Text>
      </TouchableOpacity>
    </View>
  );
}

export default function RenderCompare() {
  const router = useRouter();
  return (
    <SafeAreaView style={styles.root}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.back}><Text style={styles.backTxt}>‹ Back</Text></TouchableOpacity>
        <Text style={styles.title}>🖼️ Compare Renders</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: 14 }}>
        <Text style={styles.hint}>All renders are upscaled to 4096px masters. Tap a mode to swap each pane.</Text>
        <View style={styles.panes}>
          <Pane label="A" testID="pane-a" defaultMode="cartographic" seed={7} />
          <Pane label="B" testID="pane-b" defaultMode="globe" seed={7} />
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#05070d' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#141c2e', gap: 8 },
  back: { paddingVertical: 6, paddingHorizontal: 8 },
  backTxt: { color: '#60a5fa', fontSize: 15, fontWeight: '700' },
  title: { color: '#F8FAFC', fontSize: 18, fontWeight: '800' },
  hint: { color: '#64748b', fontSize: 12, marginBottom: 12 },
  panes: { flexDirection: 'row', justifyContent: 'space-between', gap: 10 },
  pane: { backgroundColor: '#0b1220', borderRadius: 12, borderWidth: 1, borderColor: '#1e293b', padding: 8, alignItems: 'center' },
  paneLabel: { color: '#94a3b8', fontSize: 12, fontWeight: '800', marginBottom: 6 },
  modeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 5, marginTop: 8, justifyContent: 'center' },
  modeChip: { backgroundColor: '#1e293b', borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4 },
  modeOn: { backgroundColor: '#7c3aed' },
  modeTxt: { color: '#94a3b8', fontSize: 11, fontWeight: '600' },
  modeTxtOn: { color: '#fff' },
  loader: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(5,7,13,0.55)', borderRadius: 10 },
  loaderTxt: { color: '#93C5FD', fontSize: 10, marginTop: 6, fontWeight: '700' },
  dlBtn: { marginTop: 8, backgroundColor: '#1e293b', borderRadius: 8, paddingVertical: 7, paddingHorizontal: 8, alignSelf: 'stretch', alignItems: 'center' },
  dlTxt: { color: '#93C5FD', fontSize: 10, fontWeight: '700' },
});
