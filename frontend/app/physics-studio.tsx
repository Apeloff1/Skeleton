/**
 * /physics-studio — 🧲 Physics System.
 * Forge a complete physics system (world/gravity, materials, bodies, colliders,
 * forces, constraints, tuning) by parsing the game's files + mechanics, then
 * export engine config or a unified engine bundle. Wired to Snowball `physics`.
 * Launch with params { pid, title } from My Builds.
 */
import React from 'react';
import {
  View, Text, StyleSheet, ScrollView, SafeAreaView, TouchableOpacity,
  ActivityIndicator, Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Body = { entity?: string; body_type?: string; material?: string; collider?: string; notes?: string };
type Mat = { id?: string; friction?: number; restitution?: number; density?: number; notes?: string };

export default function PhysicsStudio() {
  const router = useRouter();
  const params = useLocalSearchParams<{ pid?: string; title?: string }>();
  const pid = typeof params.pid === 'string' ? params.pid : '';
  const title = typeof params.title === 'string' ? params.title : 'Your Game';

  const [system, setSystem] = React.useState<any>(null);
  const [stats, setStats] = React.useState<any>(null);
  const [composing, setComposing] = React.useState(false);
  const pollRef = React.useRef<any>(null);

  const loadSystem = React.useCallback(async () => {
    if (!pid) return;
    try {
      const r = await fetch(`${BACKEND}/api/physics/system/${pid}`);
      const j = await r.json();
      setSystem(j?.present ? j.system : null);
      setStats(j?.stats || null);
    } catch { /* keep */ }
  }, [pid]);

  React.useEffect(() => {
    loadSystem();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [loadSystem]);

  const compose = React.useCallback(async () => {
    if (!pid) { Alert.alert('No game', 'Open this from a build in My Builds.'); return; }
    setComposing(true);
    try {
      const r = await fetch(`${BACKEND}/api/physics/compose/${pid}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}),
      });
      const j = await r.json();
      if (!j?.job_id) { setComposing(false); Alert.alert('Failed', j?.error || 'Could not start.'); return; }
      pollRef.current = setInterval(async () => {
        try {
          const pr = await fetch(`${BACKEND}/api/playable/job/${j.job_id}`);
          const pj = await pr.json();
          const st = pj?.job_status || pj?.status;
          if (st && st !== 'running') {
            clearInterval(pollRef.current); pollRef.current = null;
            await loadSystem();
            setComposing(false);
          }
        } catch { /* keep polling */ }
      }, 3000);
    } catch (e: any) {
      setComposing(false);
      Alert.alert('Network error', String(e?.message || e));
    }
  }, [pid, loadSystem]);

  const exportConfig = React.useCallback(async () => {
    if (!pid) return;
    try {
      const r = await fetch(`${BACKEND}/api/physics/export/${pid}`);
      const j = await r.json();
      if (j?.ok) {
        const c = j.config || {};
        Alert.alert('Physics config ready',
          `${j.filename}\n\nschema: ${c.schema}\nbodies: ${(c.bodies || []).length} · materials: ${(c.materials || []).length} · forces: ${(c.forces || []).length}\n\nDrops into your build's engine config.`);
      } else { Alert.alert('Nothing to export', j?.error || 'Compose first.'); }
    } catch (e: any) { Alert.alert('Export error', String(e?.message || e)); }
  }, [pid]);

  const bundle = React.useCallback(async () => {
    if (!pid) return;
    try {
      const r = await fetch(`${BACKEND}/api/physics/bundle/${pid}`);
      const j = await r.json();
      if (j?.ok) {
        const inc = j.bundle?.includes || {};
        Alert.alert('Engine bundle ready',
          `${j.filename}\n\nMerges: ${Object.entries(inc).filter(([, v]) => v).map(([k]) => k).join(' + ')}\n\nOne drop-in file for your whole runtime.`);
      } else { Alert.alert('Nothing to bundle', j?.error || 'Forge physics/camera/mechanics first.'); }
    } catch (e: any) { Alert.alert('Bundle error', String(e?.message || e)); }
  }, [pid]);

  const bodies: Body[] = (system?.bodies as Body[]) || [];
  const mats: Mat[] = (system?.materials as Mat[]) || [];
  const world = system?.world || {};
  const g = world?.gravity || {};
  const tuning = system?.tuning || {};

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity testID="phys-back" onPress={() => router.back()} style={s.hBtn}>
          <Ionicons name="arrow-back" size={24} color="#F8FAFC" />
        </TouchableOpacity>
        <Text style={s.hTitle} numberOfLines={1}>🧲 Physics System</Text>
        <View style={s.hBtn} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 56 }}>
        <Text style={s.sub}>{title}</Text>

        {stats ? (
          <View style={s.statRow}>
            <Stat n={stats.bodies} l="bodies" />
            <Stat n={stats.materials} l="materials" />
            <Stat n={stats.forces} l="forces" />
            <Stat n={stats.constraints} l="constraints" />
          </View>
        ) : null}

        {system ? (
          <View style={s.worldCard}>
            <Text style={s.cardTitle}>🌍 World</Text>
            <Text style={s.muted}>Gravity ({g.x ?? 0}, {g.y ?? '—'}, {g.z ?? 0}) · {world.units || 'm'} · {world.solver_iterations ?? '—'} iters</Text>
            {tuning?.feel ? <Text style={s.muted}>Feel: {tuning.feel} · gravity_scale {tuning.gravity_scale ?? '—'} · max_v {tuning.max_velocity ?? '—'}</Text> : null}
          </View>
        ) : null}

        <TouchableOpacity testID="phys-compose" onPress={compose} disabled={composing}
          style={[s.btn, s.btnPrimary, composing && { opacity: 0.6 }]}>
          {composing ? <ActivityIndicator color="#0b0b12" /> : <Ionicons name="planet-outline" size={16} color="#0b0b12" />}
          <Text style={s.btnPrimaryTxt}>{composing ? 'Parsing & simulating…' : system ? 'Re-tune physics' : 'Build physics system'}</Text>
        </TouchableOpacity>

        {system ? (
          <View style={s.actionsRow}>
            <TouchableOpacity testID="phys-export" onPress={exportConfig} style={[s.btn, s.btnGhost, s.flex1]}>
              <Ionicons name="download-outline" size={15} color="#a78bfa" />
              <Text style={s.btnGhostTxt}>Export config</Text>
            </TouchableOpacity>
            <TouchableOpacity testID="phys-bundle" onPress={bundle} style={[s.btn, s.btnGhost, s.flex1]}>
              <Ionicons name="cube-outline" size={15} color="#a78bfa" />
              <Text style={s.btnGhostTxt}>Engine bundle</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {mats.length ? (
          <>
            <Text style={s.section}>Materials</Text>
            {mats.map((m, i) => (
              <View key={`${m.id}-${i}`} style={s.card}>
                <Text style={s.cardTitle}>{m.id} <Text style={s.tag}>μ{m.friction} · e{m.restitution} · ρ{m.density}</Text></Text>
                {m.notes ? <Text style={s.muted}>{m.notes}</Text> : null}
              </View>
            ))}
          </>
        ) : null}

        {bodies.length ? (
          <>
            <Text style={s.section}>Rigid bodies</Text>
            {bodies.slice(0, 20).map((b, i) => (
              <View key={`${b.entity}-${i}`} style={s.card}>
                <Text style={s.cardTitle}>{b.entity} <Text style={s.tag}>{b.body_type}</Text></Text>
                <Text style={s.muted}>{b.collider} collider · {b.material}{b.notes ? ` — ${b.notes}` : ''}</Text>
              </View>
            ))}
          </>
        ) : null}

        {!system && !pid ? <Text style={s.hint}>Open this from a build in My Builds to forge its physics.</Text> : null}
        {!system && pid ? <Text style={s.hint}>No physics yet — tap “Build physics system” to parse this game and simulate it.</Text> : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function Stat({ n, l }: { n: number; l: string }) {
  return (
    <View style={s.stat}><Text style={s.statN}>{n ?? 0}</Text><Text style={s.statL}>{l}</Text></View>
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
  worldCard: { backgroundColor: '#15131f', borderRadius: 12, borderWidth: 1, borderColor: '#2a2640', padding: 12, marginBottom: 8 },
  card: { backgroundColor: '#15131f', borderRadius: 12, borderWidth: 1, borderColor: '#2a2640', padding: 12, marginBottom: 8 },
  cardTitle: { color: '#F8FAFC', fontSize: 14, fontWeight: '700' },
  tag: { color: '#a78bfa', fontSize: 11, fontWeight: '700' },
  muted: { color: '#9ca3af', fontSize: 12, marginTop: 3, lineHeight: 17 },
  btn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 12, paddingVertical: 14, marginTop: 6 },
  btnPrimary: { backgroundColor: '#a78bfa' },
  btnPrimaryTxt: { color: '#0b0b12', fontSize: 15, fontWeight: '800' },
  actionsRow: { flexDirection: 'row', gap: 10, marginTop: 10 },
  flex1: { flex: 1 },
  btnGhost: { backgroundColor: 'transparent', borderWidth: 1, borderColor: '#a78bfa55' },
  btnGhostTxt: { color: '#a78bfa', fontSize: 13, fontWeight: '700' },
  hint: { color: '#6b7280', fontSize: 12, textAlign: 'center', marginTop: 16, lineHeight: 18 },
});
