/**
 * 🏛️ Faction & Social Simulation (Segment III.4)
 *
 * Deterministic, seedable social sim: configure faction count / turns / seed, run
 * /api/factions/simulate, and explore the resulting power ranking, alliances/wars,
 * and a chronological world-event timeline.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet, ActivityIndicator, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';

const C = {
  bg: '#0B1120', surface: '#111A2E', surface2: '#1E293B', border: '#243049',
  text: '#E2E8F0', dim: '#94A3B8', brand: '#8B5CF6', amber: '#D97706',
  green: '#22C55E', red: '#EF4444', cyan: '#3B82F6', gold: '#EAB308',
};

type Faction = {
  id: number; name: string; icon: string; ethos: string; power: number;
  resources: number; territory: number; aggression: number; wealth: number;
  allies: number[]; wars: number[]; alive: boolean;
};
type SimEvent = { turn: number; kind: string; text: string };
type SimResult = {
  seed: number; factions: Faction[]; turns: number; events: SimEvent[];
  summary: {
    dominant: string; dominant_icon: string; dominant_power: number;
    survivors: number; total_wars: number; total_alliances: number; collapses: number;
  };
};

const EVENT_COLOR: Record<string, string> = {
  war: C.red, alliance: C.green, conquest: C.amber, collapse: '#64748B',
};

function Stepper({ label, value, min, max, step, onChange }: {
  label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void;
}) {
  return (
    <View style={styles.stepper}>
      <Text style={styles.stepperLabel}>{label}</Text>
      <View style={styles.stepperRow}>
        <TouchableOpacity testID={`fac-${label}-dec`} style={styles.stepBtn} onPress={() => onChange(Math.max(min, value - step))}>
          <Text style={styles.stepBtnTxt}>−</Text>
        </TouchableOpacity>
        <Text style={styles.stepperVal}>{value}</Text>
        <TouchableOpacity testID={`fac-${label}-inc`} style={styles.stepBtn} onPress={() => onChange(Math.min(max, value + step))}>
          <Text style={styles.stepBtnTxt}>+</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

export default function FactionsScreen() {
  const router = useRouter();
  const haptics = useHaptics();
  const [factions, setFactions] = React.useState(6);
  const [turns, setTurns] = React.useState(40);
  const [seed, setSeed] = React.useState(1337);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<SimResult | null>(null);

  const run = React.useCallback(async () => {
    haptics.selection();
    setBusy(true); setError(null);
    const r = await api.post<SimResult>('/api/factions/simulate', { seed, factions, turns }, { timeoutMs: 15000, retries: 1 });
    if (r.ok && r.data?.summary) {
      setResult(r.data); haptics.notify('success');
    } else {
      setError(r.error || `HTTP ${r.status}`); haptics.notify('error');
    }
    setBusy(false);
  }, [seed, factions, turns, haptics]);

  const reroll = React.useCallback(() => {
    haptics.selection();
    setSeed(Math.floor(Math.random() * 1_000_000));
  }, [haptics]);

  const ranking = React.useMemo(
    () => (result ? [...result.factions].sort((a, b) => Number(b.alive) - Number(a.alive) || b.power - a.power) : []),
    [result],
  );

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity testID="fac-back" style={styles.iconBtn} onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={24} color={C.text} />
        </TouchableOpacity>
        <Text style={styles.title}>🏛️ Faction Simulation</Text>
        <View style={styles.iconBtn} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Text style={styles.subtitle}>
          A deterministic social sim — factions form alliances, wage wars, seize territory and rise or collapse over time. Same seed → identical history.
        </Text>

        <View style={styles.card}>
          <Stepper label="Factions" value={factions} min={3} max={12} step={1} onChange={setFactions} />
          <Stepper label="Turns" value={turns} min={5} max={120} step={5} onChange={setTurns} />
          <View style={styles.seedRow}>
            <Text style={styles.stepperLabel}>Seed</Text>
            <Text style={styles.seedVal}>{seed}</Text>
            <TouchableOpacity testID="fac-reroll" style={styles.rerollBtn} onPress={reroll}>
              <Ionicons name="dice" size={16} color={C.text} />
              <Text style={styles.rerollTxt}>Reroll</Text>
            </TouchableOpacity>
          </View>
          <TouchableOpacity testID="fac-simulate" style={[styles.simBtn, busy && { opacity: 0.6 }]} disabled={busy} onPress={run}>
            {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.simBtnTxt}>⚔️  Run Simulation</Text>}
          </TouchableOpacity>
          {error ? <Text style={styles.error}>{error}</Text> : null}
        </View>

        {result ? (
          <>
            <View testID="fac-summary" style={[styles.card, styles.summaryCard]}>
              <Text style={styles.summaryDom}>{result.summary.dominant_icon} {result.summary.dominant}</Text>
              <Text style={styles.summaryLabel}>Dominant power · {result.summary.dominant_power}</Text>
              <View style={styles.summaryStats}>
                <View style={styles.stat}><Text style={[styles.statN, { color: C.green }]}>{result.summary.survivors}</Text><Text style={styles.statL}>survivors</Text></View>
                <View style={styles.stat}><Text style={[styles.statN, { color: C.red }]}>{result.summary.total_wars}</Text><Text style={styles.statL}>wars</Text></View>
                <View style={styles.stat}><Text style={[styles.statN, { color: C.cyan }]}>{result.summary.total_alliances}</Text><Text style={styles.statL}>alliances</Text></View>
                <View style={styles.stat}><Text style={[styles.statN, { color: C.dim }]}>{result.summary.collapses}</Text><Text style={styles.statL}>collapses</Text></View>
              </View>
            </View>

            <Text style={styles.sectionTitle}>Power Ranking</Text>
            {ranking.map((f, i) => (
              <View key={f.id} testID={`fac-card-${f.id}`} style={[styles.facCard, !f.alive && { opacity: 0.45 }]}>
                <Text style={styles.facRank}>{i + 1}</Text>
                <Text style={styles.facIcon}>{f.icon}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.facName}>{f.name}{!f.alive ? '  💀' : ''}</Text>
                  <Text style={styles.facEthos}>{f.ethos} · ⚔︎{f.allies.length ? ` ${f.allies.length} allies` : ''}{f.wars.length ? ` · ${f.wars.length} wars` : ''}</Text>
                </View>
                <View style={styles.facMetrics}>
                  <Text style={styles.facPower}>⚡ {f.power}</Text>
                  <Text style={styles.facTerr}>🗺️ {f.territory}</Text>
                </View>
              </View>
            ))}

            <Text style={styles.sectionTitle}>World Events</Text>
            <View style={styles.card}>
              {result.events.length === 0 ? (
                <Text style={styles.dim}>A peaceful age — no major events.</Text>
              ) : (
                result.events.slice().reverse().map((e, idx) => (
                  <View key={idx} style={styles.eventRow}>
                    <View style={[styles.eventDot, { backgroundColor: EVENT_COLOR[e.kind] || C.dim }]} />
                    <Text style={styles.eventTurn}>T{e.turn}</Text>
                    <Text style={styles.eventTxt}>{e.text}</Text>
                  </View>
                ))
              )}
            </View>
          </>
        ) : (
          !busy && (
            <View style={styles.empty}>
              <Text style={styles.emptyIcon}>🗺️</Text>
              <Text style={styles.dim}>{"Configure and run a simulation to watch a world's politics unfold."}</Text>
            </View>
          )
        )}
        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border },
  iconBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center', borderRadius: 20 },
  title: { color: C.text, fontSize: 18, fontWeight: '700' },
  scroll: { padding: 16 },
  subtitle: { color: C.dim, fontSize: 13, lineHeight: 19, marginBottom: 16 },
  card: { backgroundColor: C.surface, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 16 },
  stepper: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 },
  stepperLabel: { color: C.text, fontSize: 15, fontWeight: '600' },
  stepperRow: { flexDirection: 'row', alignItems: 'center' },
  stepBtn: { width: 40, height: 40, borderRadius: 10, backgroundColor: C.surface2, alignItems: 'center', justifyContent: 'center' },
  stepBtnTxt: { color: C.text, fontSize: 22, fontWeight: '700' },
  stepperVal: { color: C.text, fontSize: 18, fontWeight: '700', minWidth: 48, textAlign: 'center' },
  seedRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 },
  seedVal: { color: C.dim, fontSize: 15, fontWeight: '600', flex: 1, textAlign: 'center', fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  rerollBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.surface2, paddingHorizontal: 12, paddingVertical: 9, borderRadius: 10 },
  rerollTxt: { color: C.text, fontWeight: '600', fontSize: 13 },
  simBtn: { backgroundColor: C.amber, borderRadius: 12, paddingVertical: 14, alignItems: 'center', justifyContent: 'center' },
  simBtnTxt: { color: '#fff', fontWeight: '800', fontSize: 16 },
  error: { color: C.red, marginTop: 10, fontSize: 13 },
  summaryCard: { backgroundColor: '#1b1430', borderColor: C.brand },
  summaryDom: { color: '#fff', fontSize: 22, fontWeight: '800' },
  summaryLabel: { color: C.dim, fontSize: 13, marginTop: 2, marginBottom: 14 },
  summaryStats: { flexDirection: 'row', justifyContent: 'space-between' },
  stat: { alignItems: 'center', flex: 1 },
  statN: { fontSize: 20, fontWeight: '800' },
  statL: { color: C.dim, fontSize: 11, marginTop: 2 },
  sectionTitle: { color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 10 },
  facCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: C.surface, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: C.border, marginBottom: 8 },
  facRank: { color: C.dim, fontSize: 14, fontWeight: '800', width: 22 },
  facIcon: { fontSize: 26, marginRight: 10 },
  facName: { color: C.text, fontSize: 15, fontWeight: '700' },
  facEthos: { color: C.dim, fontSize: 12, marginTop: 2 },
  facMetrics: { alignItems: 'flex-end' },
  facPower: { color: C.gold, fontSize: 14, fontWeight: '700' },
  facTerr: { color: C.dim, fontSize: 12, marginTop: 2 },
  eventRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 6 },
  eventDot: { width: 8, height: 8, borderRadius: 4, marginRight: 10 },
  eventTurn: { color: C.dim, fontSize: 12, fontWeight: '700', width: 34 },
  eventTxt: { color: C.text, fontSize: 13, flex: 1 },
  empty: { alignItems: 'center', paddingVertical: 40 },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  dim: { color: C.dim, fontSize: 13, textAlign: 'center', lineHeight: 19 },
});
