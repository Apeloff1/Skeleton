/**
 * /camera-director — 🎥 Cinematic Camera Director.
 * Forge a complete camera system (rigs, per-scene shot lists, cutscenes) that
 * parses the game's files + design artifacts, then export engine config or hear
 * a voiced walkthrough. Wired to the Snowball `cinematics` stage.
 * Launch with params { pid, title } from My Builds.
 */
import React from 'react';
import {
  View, Text, StyleSheet, ScrollView, SafeAreaView, TouchableOpacity,
  ActivityIndicator, Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { playClipsSequential, stopCinematic } from '../src/utils/cinematicVoice';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Rig = { id: string; type: string; label?: string; fov?: number; use?: string; notes?: string };
type Shot = { shot_id?: string; rig?: string; movement?: string; target?: string; fov?: number; duration_s?: number; easing?: string; trigger?: string };
type Scene = { scene?: string; description?: string; shots?: Shot[] };

export default function CameraDirector() {
  const router = useRouter();
  const params = useLocalSearchParams<{ pid?: string; title?: string }>();
  const pid = typeof params.pid === 'string' ? params.pid : '';
  const title = typeof params.title === 'string' ? params.title : 'Your Game';

  const [catalog, setCatalog] = React.useState<Rig[]>([]);
  const [director, setDirector] = React.useState<any>(null);
  const [stats, setStats] = React.useState<any>(null);
  const [composing, setComposing] = React.useState(false);
  const [narrating, setNarrating] = React.useState(false);
  const pollRef = React.useRef<any>(null);

  const loadDirector = React.useCallback(async () => {
    if (!pid) return;
    try {
      const r = await fetch(`${BACKEND}/api/camera/director/${pid}`);
      const j = await r.json();
      setDirector(j?.present ? j.director : null);
      setStats(j?.stats || null);
    } catch { /* keep */ }
  }, [pid]);

  React.useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${BACKEND}/api/camera/rigs`);
        const j = await r.json();
        if (Array.isArray(j?.rigs)) setCatalog(j.rigs);
      } catch { /* non-fatal */ }
    })();
    loadDirector();
    return () => { stopCinematic(); if (pollRef.current) clearInterval(pollRef.current); };
  }, [loadDirector]);

  const compose = React.useCallback(async () => {
    if (!pid) { Alert.alert('No game', 'Open this from a build in My Builds.'); return; }
    setComposing(true);
    try {
      const r = await fetch(`${BACKEND}/api/camera/compose/${pid}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}),
      });
      const j = await r.json();
      if (!j?.job_id) { setComposing(false); Alert.alert('Failed', j?.error || 'Could not start.'); return; }
      // poll the forge job
      pollRef.current = setInterval(async () => {
        try {
          const pr = await fetch(`${BACKEND}/api/playable/job/${j.job_id}`);
          const pj = await pr.json();
          const st = pj?.job_status || pj?.status;
          if (st && st !== 'running') {
            clearInterval(pollRef.current); pollRef.current = null;
            await loadDirector();
            setComposing(false);
          }
        } catch { /* keep polling */ }
      }, 3000);
    } catch (e: any) {
      setComposing(false);
      Alert.alert('Network error', String(e?.message || e));
    }
  }, [pid, loadDirector]);

  const narrate = React.useCallback(async () => {
    if (!pid) return;
    setNarrating(true);
    try {
      const r = await fetch(`${BACKEND}/api/camera/narrate/${pid}`, { method: 'POST' });
      const j = await r.json();
      if (j?.audio_base64) await playClipsSequential([j.audio_base64]);
      else Alert.alert('No audio', j?.error || 'Compose the director first.');
    } catch (e: any) {
      Alert.alert('Narration error', String(e?.message || e));
    }
    setNarrating(false);
  }, [pid]);

  const exportConfig = React.useCallback(async () => {
    if (!pid) return;
    try {
      const r = await fetch(`${BACKEND}/api/camera/export/${pid}`);
      const j = await r.json();
      if (j?.ok) {
        Alert.alert('Engine config ready',
          `${j.filename}\n\nschema: ${j.config?.schema}\nrigs: ${(j.config?.rigs || []).length} · scenes: ${(j.config?.scenes || []).length} · fps: ${j.config?.fps}\n\nThis JSON drops into your build's engine config.`);
      } else {
        Alert.alert('Nothing to export', j?.error || 'Compose the director first.');
      }
    } catch (e: any) {
      Alert.alert('Export error', String(e?.message || e));
    }
  }, [pid]);

  const scenes: Scene[] = (director?.scenes as Scene[]) || [];
  const rigs: Rig[] = (director?.rigs as Rig[]) || [];

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity testID="cam-back" onPress={() => router.back()} style={s.hBtn}>
          <Ionicons name="arrow-back" size={24} color="#F8FAFC" />
        </TouchableOpacity>
        <Text style={s.hTitle} numberOfLines={1}>🎥 Camera Director</Text>
        <View style={s.hBtn} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 56 }}>
        <Text style={s.sub}>{title}</Text>

        {/* Stats */}
        {stats ? (
          <View style={s.statRow}>
            <Stat n={stats.rigs} l="rigs" />
            <Stat n={stats.scenes} l="scenes" />
            <Stat n={stats.shots} l="shots" />
            <Stat n={stats.cutscenes} l="cutscenes" />
          </View>
        ) : null}

        {/* Compose */}
        <TouchableOpacity
          testID="cam-compose"
          onPress={compose}
          disabled={composing}
          style={[s.btn, s.btnPrimary, composing && { opacity: 0.6 }]}
        >
          {composing ? <ActivityIndicator color="#0b0b12" /> : <Ionicons name="film-outline" size={16} color="#0b0b12" />}
          <Text style={s.btnPrimaryTxt}>
            {composing ? 'Parsing game files & directing…' : director ? 'Re-direct cameras' : 'Direct the cameras'}
          </Text>
        </TouchableOpacity>

        {director ? (
          <View style={s.actionsRow}>
            <TouchableOpacity testID="cam-narrate" onPress={narrate} disabled={narrating} style={[s.btn, s.btnGhost, s.flex1]}>
              <Ionicons name={narrating ? 'volume-high' : 'mic-outline'} size={15} color="#a78bfa" />
              <Text style={s.btnGhostTxt}>Hear plan</Text>
            </TouchableOpacity>
            <TouchableOpacity testID="cam-export" onPress={exportConfig} style={[s.btn, s.btnGhost, s.flex1]}>
              <Ionicons name="download-outline" size={15} color="#a78bfa" />
              <Text style={s.btnGhostTxt}>Export config</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {/* Rigs in the director */}
        {rigs.length ? (
          <>
            <Text style={s.section}>Camera rigs</Text>
            {rigs.map((r, i) => (
              <View key={`${r.id}-${i}`} style={s.card}>
                <Text style={s.cardTitle}>🎬 {r.id} <Text style={s.tag}>{r.type}</Text></Text>
                {r.fov != null ? <Text style={s.muted}>FOV {r.fov}{r.easing ? ` · ${r.easing}` : ''}</Text> : null}
                {r.notes ? <Text style={s.muted}>{r.notes}</Text> : null}
              </View>
            ))}
          </>
        ) : null}

        {/* Scenes & shots */}
        {scenes.length ? (
          <>
            <Text style={s.section}>Scene shot lists</Text>
            {scenes.map((sc, i) => (
              <View key={`${sc.scene}-${i}`} style={s.card}>
                <Text style={s.cardTitle}>{sc.scene || `Scene ${i + 1}`}
                  <Text style={s.tag}>  {(sc.shots || []).length} shots</Text>
                </Text>
                {sc.description ? <Text style={s.muted}>{sc.description}</Text> : null}
                {(sc.shots || []).slice(0, 6).map((sh, j) => (
                  <Text key={j} style={s.shot}>
                    • {sh.movement || 'move'} on <Text style={s.shotRig}>{sh.rig || 'cam'}</Text>
                    {sh.target ? ` → ${sh.target}` : ''}{sh.duration_s ? ` (${sh.duration_s}s)` : ''}
                  </Text>
                ))}
              </View>
            ))}
          </>
        ) : null}

        {/* Reference catalog when nothing composed yet */}
        {!director ? (
          <>
            <Text style={s.section}>Rig presets</Text>
            <Text style={s.muted}>The director composes shots from these cinematic rigs:</Text>
            {catalog.map((r) => (
              <View key={r.id} style={s.card}>
                <Text style={s.cardTitle}>{r.label || r.id} <Text style={s.tag}>{r.type}</Text></Text>
                <Text style={s.muted}>{r.use}</Text>
              </View>
            ))}
            {!pid ? <Text style={s.hint}>Open this from a build in My Builds to direct its cameras.</Text> : null}
          </>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function Stat({ n, l }: { n: number; l: string }) {
  return (
    <View style={s.stat}>
      <Text style={s.statN}>{n ?? 0}</Text>
      <Text style={s.statL}>{l}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0b0b12' },
  header: { flexDirection: 'row', alignItems: 'center', padding: 12, backgroundColor: '#15131f', borderBottomWidth: 1, borderBottomColor: '#2a2640' },
  hBtn: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  hTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '800', color: '#F8FAFC' },
  sub: { color: '#c4b5fd', fontSize: 14, fontWeight: '700', marginBottom: 14 },
  statRow: { flexDirection: 'row', gap: 8, marginBottom: 14 },
  stat: { flex: 1, backgroundColor: '#15131f', borderRadius: 12, borderWidth: 1, borderColor: '#2a2640', paddingVertical: 12, alignItems: 'center' },
  statN: { color: '#fbbf24', fontSize: 20, fontWeight: '800' },
  statL: { color: '#9ca3af', fontSize: 10, fontWeight: '600', marginTop: 2 },
  section: { color: '#c4b5fd', fontSize: 13, fontWeight: '800', marginTop: 22, marginBottom: 8 },
  card: { backgroundColor: '#15131f', borderRadius: 12, borderWidth: 1, borderColor: '#2a2640', padding: 12, marginBottom: 8 },
  cardTitle: { color: '#F8FAFC', fontSize: 14, fontWeight: '700' },
  tag: { color: '#a78bfa', fontSize: 11, fontWeight: '700' },
  muted: { color: '#9ca3af', fontSize: 12, marginTop: 3, lineHeight: 17 },
  shot: { color: '#cbd5e1', fontSize: 12, marginTop: 4 },
  shotRig: { color: '#a78bfa', fontWeight: '700' },
  btn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 12, paddingVertical: 14, marginTop: 6 },
  btnPrimary: { backgroundColor: '#a78bfa' },
  btnPrimaryTxt: { color: '#0b0b12', fontSize: 15, fontWeight: '800' },
  actionsRow: { flexDirection: 'row', gap: 10, marginTop: 10 },
  flex1: { flex: 1 },
  btnGhost: { backgroundColor: 'transparent', borderWidth: 1, borderColor: '#a78bfa55' },
  btnGhostTxt: { color: '#a78bfa', fontSize: 13, fontWeight: '700' },
  hint: { color: '#6b7280', fontSize: 12, textAlign: 'center', marginTop: 16, lineHeight: 18 },
});
