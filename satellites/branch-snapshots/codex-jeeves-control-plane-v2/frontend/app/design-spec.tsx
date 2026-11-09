/**
 * /design-spec — Design-Spec Compiler (Backlog Phase I.4).
 *
 * Type a free-text game brief → compile it into a typed Game Design Document
 * via the Model Router (task='reasoning'). Shows the coherence-gate verdict
 * (ready / needs-revision + gaps), the structured GDD, and the executable
 * build-plan handoff that downstream pipelines consume.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator, TextInput,
  StyleSheet, SafeAreaView, Platform, KeyboardAvoidingView,
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';

interface GDD {
  title: string; genre: string; subgenre: string; logline: string;
  pillars: string[]; core_loop: string;
  mechanics: { name: string; description: string }[];
  systems: { name: string; description: string }[];
  progression: string; art_direction: string; audio_direction: string;
  content_plan: { levels: number; enemies: number; items: number; npcs: number };
  target_platforms: string[]; scope_tier: string; risks: string[];
}
interface Spec {
  spec_id: string; gdd: GDD; coherence_score: number; gaps: string[];
  status: string; build_plan: { scope_tier: string; target_files_hint: number; systems: string[] };
  model?: string; cached?: boolean; llm_error?: string; error?: string;
}

const EXAMPLES = [
  'A cozy farming sim on a floating sky-island where weather is a puzzle mechanic.',
  'A roguelike deckbuilder where your cards are living NPCs that remember past runs.',
  'A competitive 1v1 mech-arena with destructible terrain and rollback netcode.',
];

export default function DesignSpecScreen() {
  const router = useRouter();
  const haptics = useHaptics();
  const [brief, setBrief] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [spec, setSpec] = React.useState<Spec | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const compile = React.useCallback(async () => {
    if (brief.trim().length < 8 || busy) return;
    haptics.selection();
    setBusy(true); setError(null); setSpec(null);
    const r = await api.post<Spec>('/api/design-spec/compile', { brief });
    if (r.ok && r.data && !r.data.error) setSpec(r.data);
    else setError((r.data && r.data.error) || r.error || `HTTP ${r.status}`);
    setBusy(false);
  }, [brief, busy, haptics]);

  const g = spec?.gdd;
  const ready = spec?.status === 'ready';

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity testID="ds-back" onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backTxt}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Design-Spec Compiler</Text>
        <View style={styles.backBtn} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView style={styles.scroll} contentContainerStyle={{ paddingBottom: 40 }} keyboardShouldPersistTaps="handled">
          <Text style={styles.label}>Game brief</Text>
          <TextInput
            testID="ds-brief"
            style={styles.input}
            value={brief}
            onChangeText={setBrief}
            placeholder="Describe the game you want to build…"
            placeholderTextColor="#475569"
            multiline
          />
          <View style={styles.exRow}>
            {EXAMPLES.map((e, i) => (
              <TouchableOpacity key={i} testID={`ds-example-${i}`} style={styles.exChip} onPress={() => setBrief(e)}>
                <Text style={styles.exTxt} numberOfLines={1}>{e.slice(0, 34)}…</Text>
              </TouchableOpacity>
            ))}
          </View>
          <TouchableOpacity testID="ds-compile" style={[styles.cta, busy && { opacity: 0.5 }]} onPress={compile} disabled={busy}>
            {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.ctaTxt}>Compile GDD →</Text>}
          </TouchableOpacity>

          {error ? <Text style={styles.err}>{error}</Text> : null}

          {spec && g ? (
            <View testID="ds-result">
              {/* Coherence gate verdict */}
              <View style={[styles.verdict, { borderColor: ready ? '#22c55e' : '#f59e0b' }]}>
                <Text style={[styles.verdictTitle, { color: ready ? '#4ade80' : '#fbbf24' }]}>
                  {ready ? '✓ READY' : '⚠ NEEDS REVISION'} · coherence {spec.coherence_score}/100
                </Text>
                {spec.gaps.length > 0 ? (
                  <Text style={styles.gaps}>Gaps: {spec.gaps.join(' · ')}</Text>
                ) : <Text style={styles.gaps}>No structural gaps detected.</Text>}
                <Text style={styles.modelLine}>
                  {spec.model || 'no-model'} {spec.cached ? '· cached' : ''} {spec.llm_error ? `· ${spec.llm_error}` : ''}
                </Text>
              </View>

              {/* GDD */}
              <Text style={styles.gTitle}>{g.title}</Text>
              <Text style={styles.gMeta}>{g.genre}{g.subgenre ? ` · ${g.subgenre}` : ''} · {g.scope_tier}</Text>
              {g.logline ? <Text style={styles.logline}>“{g.logline}”</Text> : null}

              <Block title="Pillars" items={g.pillars} />
              {g.core_loop ? <KV label="Core loop" value={g.core_loop} /> : null}
              <NDBlock title="Mechanics" items={g.mechanics} />
              <NDBlock title="Systems" items={g.systems} />
              {g.progression ? <KV label="Progression" value={g.progression} /> : null}
              {g.art_direction ? <KV label="Art direction" value={g.art_direction} /> : null}
              {g.audio_direction ? <KV label="Audio direction" value={g.audio_direction} /> : null}

              <Section title="Content plan">
                <View style={styles.cpRow}>
                  <CP label="Levels" v={g.content_plan.levels} />
                  <CP label="Enemies" v={g.content_plan.enemies} />
                  <CP label="Items" v={g.content_plan.items} />
                  <CP label="NPCs" v={g.content_plan.npcs} />
                </View>
              </Section>

              <Block title="Risks" items={g.risks} />

              <Section title="Build-plan handoff">
                <Text style={styles.bp}>scope: {spec.build_plan.scope_tier} · ~{spec.build_plan.target_files_hint.toLocaleString()} files</Text>
                <Text style={styles.bpSys}>{spec.build_plan.systems.filter(Boolean).join(', ') || '—'}</Text>
              </Section>
            </View>
          ) : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <View style={styles.section}><Text style={styles.sectionTitle}>{title}</Text>{children}</View>;
}
function Block({ title, items }: { title: string; items: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <Section title={title}>
      {items.map((it, i) => <Text key={i} style={styles.bullet}>•  {String(it)}</Text>)}
    </Section>
  );
}
function NDBlock({ title, items }: { title: string; items: { name: string; description: string }[] }) {
  if (!items || items.length === 0) return null;
  return (
    <Section title={title}>
      {items.map((it, i) => (
        <View key={i} style={styles.nd}>
          <Text style={styles.ndName}>{it.name || `#${i + 1}`}</Text>
          {it.description ? <Text style={styles.ndDesc}>{it.description}</Text> : null}
        </View>
      ))}
    </Section>
  );
}
function KV({ label, value }: { label: string; value: string }) {
  return <Section title={label}><Text style={styles.kv}>{value}</Text></Section>;
}
function CP({ label, v }: { label: string; v: number }) {
  return <View style={styles.cp}><Text style={styles.cpV}>{v}</Text><Text style={styles.cpL}>{label}</Text></View>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#0A0A0A' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingTop: Platform.OS === 'ios' ? 8 : 16, paddingBottom: 12,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1F1F1F',
  },
  backBtn: { paddingVertical: 6, paddingHorizontal: 10, width: 64 },
  backTxt: { color: '#93c5fd', fontSize: 16 },
  title: { color: '#fff', fontSize: 16, fontWeight: '700' },
  scroll: { flex: 1, paddingHorizontal: 14 },
  label: { color: '#cbd5e1', fontSize: 13, fontWeight: '700', marginTop: 14, marginBottom: 8 },
  input: {
    backgroundColor: '#0A0A0A', borderRadius: 10, color: '#e2e8f0', padding: 12,
    minHeight: 90, fontSize: 14, textAlignVertical: 'top', borderWidth: 1, borderColor: '#1F1F1F',
  },
  exRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
  exChip: { backgroundColor: '#161628', borderRadius: 16, paddingHorizontal: 10, paddingVertical: 6, maxWidth: '100%' },
  exTxt: { color: '#94a3b8', fontSize: 11 },
  cta: { backgroundColor: '#8B5CF6', borderRadius: 10, paddingVertical: 13, alignItems: 'center', marginTop: 12 },
  ctaTxt: { color: '#fff', fontWeight: '800', fontSize: 14 },
  err: { color: '#fca5a5', fontSize: 13, marginTop: 12 },
  verdict: { borderWidth: 1, borderRadius: 12, padding: 12, marginTop: 16, backgroundColor: '#0A0A0A' },
  verdictTitle: { fontSize: 14, fontWeight: '800' },
  gaps: { color: '#94a3b8', fontSize: 12, marginTop: 6 },
  modelLine: { color: '#64748b', fontSize: 11, marginTop: 6 },
  gTitle: { color: '#fff', fontSize: 22, fontWeight: '800', marginTop: 18 },
  gMeta: { color: '#8B5CF6', fontSize: 12, fontWeight: '700', marginTop: 4 },
  logline: { color: '#cbd5e1', fontSize: 14, fontStyle: 'italic', marginTop: 8 },
  section: { marginTop: 16 },
  sectionTitle: { color: '#cbd5e1', fontSize: 13, fontWeight: '700', marginBottom: 8 },
  bullet: { color: '#e2e8f0', fontSize: 13, lineHeight: 22 },
  kv: { color: '#cbd5e1', fontSize: 13, lineHeight: 20 },
  nd: { backgroundColor: '#0A0A0A', borderRadius: 8, padding: 10, marginBottom: 8 },
  ndName: { color: '#fff', fontSize: 13, fontWeight: '700' },
  ndDesc: { color: '#94a3b8', fontSize: 12, marginTop: 3, lineHeight: 18 },
  cpRow: { flexDirection: 'row', gap: 8 },
  cp: { flex: 1, backgroundColor: '#0A0A0A', borderRadius: 10, paddingVertical: 12, alignItems: 'center' },
  cpV: { color: '#3B82F6', fontSize: 18, fontWeight: '800' },
  cpL: { color: '#64748b', fontSize: 11, marginTop: 2 },
  bp: { color: '#fbbf24', fontSize: 13, fontWeight: '700' },
  bpSys: { color: '#94a3b8', fontSize: 12, marginTop: 4 },
});
