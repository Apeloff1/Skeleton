/**
 * /discourse — Discourse & Discord (multi-AI debate for the creative process).
 *
 * A panel of provider-diverse models drafts candidates (discourse), each is
 * red-teamed by another model (discord), then a judge scores every candidate on
 * QUALITY + FIDELITY and the winner is selected. Shows the full transcript.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator, TextInput,
  StyleSheet, SafeAreaView, Platform, KeyboardAvoidingView, Switch,
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';

interface Candidate {
  model: string; provider?: string; content: string; critique?: string;
  quality?: number; fidelity?: number; score?: number; rationale?: string;
}
interface Result {
  winner_index: number; winner_model: string; winner_content: string; winner_score?: number;
  judge_model: string; judge_why?: string; panel: string[]; candidates: Candidate[]; error?: string;
}

export default function DiscourseScreen() {
  const router = useRouter();
  const haptics = useHaptics();
  const [prompt, setPrompt] = React.useState('Design one original core mechanic for a calm puzzle game about light.');
  const [discord, setDiscord] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [res, setRes] = React.useState<Result | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const run = React.useCallback(async () => {
    if (prompt.trim().length < 4 || busy) return;
    haptics.selection();
    setBusy(true); setError(null); setRes(null);
    // Deliberation makes 4-6 sequential LLM calls and legitimately runs 30-90s;
    // override the default 15s apiClient timeout so the panel can actually return.
    const r = await api.post<Result>('/api/discourse/deliberate',
      { task: 'creative', prompt, discord },
      { timeoutMs: 180_000, retries: 0 });
    if (r.ok && r.data && !r.data.error) setRes(r.data);
    else setError((r.data && r.data.error) || r.error || `HTTP ${r.status}`);
    setBusy(false);
  }, [prompt, discord, busy, haptics]);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity testID="dc-back" onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backTxt}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Discourse & Discord</Text>
        <View style={styles.backBtn} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView style={styles.scroll} contentContainerStyle={{ paddingBottom: 40 }} keyboardShouldPersistTaps="handled">
          <Text style={styles.label}>Creative prompt</Text>
          <TextInput
            testID="dc-prompt"
            style={styles.input}
            value={prompt}
            onChangeText={setPrompt}
            placeholder="What should the AI panel deliberate?"
            placeholderTextColor="#475569"
            multiline
          />
          <View style={styles.row}>
            <Text style={styles.discordLbl}>⚔️ Discord (cross red-team critique)</Text>
            <Switch value={discord} onValueChange={(v) => { haptics.selection(); setDiscord(v); }} />
          </View>
          <TouchableOpacity testID="dc-run" style={[styles.cta, busy && { opacity: 0.5 }]} onPress={run} disabled={busy}>
            {busy ? (
              <View style={styles.busyRow}><ActivityIndicator color="#fff" /><Text style={styles.ctaTxt}>  Panel deliberating…</Text></View>
            ) : <Text style={styles.ctaTxt}>Deliberate →</Text>}
          </TouchableOpacity>
          {busy ? <Text style={styles.hint}>Multiple AIs draft, critique, then a judge picks the highest quality & fidelity (can take ~30-60s).</Text> : null}
          {error ? <Text style={styles.err}>{error}</Text> : null}

          {res ? (
            <View testID="dc-result">
              <View style={styles.winner}>
                <Text style={styles.winnerTag}>🏆 WINNER · {res.winner_model} · {res.winner_score ?? '—'}/100</Text>
                <Text style={styles.winnerTxt}>{res.winner_content}</Text>
                {res.judge_why ? <Text style={styles.judgeWhy}>Judge ({res.judge_model}): {res.judge_why}</Text> : null}
              </View>

              <Text style={styles.sectionTitle}>The panel ({res.candidates.length})</Text>
              {res.candidates.map((c, i) => (
                <View key={i} style={[styles.cand, i === res.winner_index && styles.candWin]} testID={`dc-cand-${i}`}>
                  <View style={styles.candHead}>
                    <Text style={styles.candModel}>{c.model}</Text>
                    <Text style={styles.candScore}>Q {c.quality ?? '–'} · F {c.fidelity ?? '–'} → {c.score ?? '–'}</Text>
                  </View>
                  <Text style={styles.candTxt} numberOfLines={6}>{c.content}</Text>
                  {c.critique ? (
                    <View style={styles.critBox}>
                      <Text style={styles.critLbl}>⚔️ Critique</Text>
                      <Text style={styles.critTxt} numberOfLines={5}>{c.critique}</Text>
                    </View>
                  ) : null}
                </View>
              ))}
            </View>
          ) : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
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
    minHeight: 80, fontSize: 14, textAlignVertical: 'top', borderWidth: 1, borderColor: '#1F1F1F',
  },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 12 },
  discordLbl: { color: '#cbd5e1', fontSize: 13, fontWeight: '600' },
  cta: { backgroundColor: '#8B5CF6', borderRadius: 10, paddingVertical: 13, alignItems: 'center', marginTop: 14 },
  busyRow: { flexDirection: 'row', alignItems: 'center' },
  ctaTxt: { color: '#fff', fontWeight: '800', fontSize: 14 },
  hint: { color: '#64748b', fontSize: 12, marginTop: 8, textAlign: 'center' },
  err: { color: '#fca5a5', fontSize: 13, marginTop: 12 },
  winner: { backgroundColor: '#0f2417', borderColor: '#22c55e', borderWidth: 1, borderRadius: 12, padding: 14, marginTop: 18 },
  winnerTag: { color: '#4ade80', fontSize: 13, fontWeight: '800' },
  winnerTxt: { color: '#e2e8f0', fontSize: 15, lineHeight: 22, marginTop: 8 },
  judgeWhy: { color: '#86efac', fontSize: 12, marginTop: 10, fontStyle: 'italic' },
  sectionTitle: { color: '#cbd5e1', fontSize: 13, fontWeight: '700', marginTop: 20, marginBottom: 8 },
  cand: { backgroundColor: '#0A0A0A', borderRadius: 10, padding: 12, marginBottom: 10, borderWidth: 1, borderColor: '#1F1F1F' },
  candWin: { borderColor: '#22c55e' },
  candHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  candModel: { color: '#fff', fontSize: 13, fontWeight: '700' },
  candScore: { color: '#fbbf24', fontSize: 12, fontWeight: '700' },
  candTxt: { color: '#cbd5e1', fontSize: 13, lineHeight: 19 },
  critBox: { backgroundColor: '#1a0f12', borderRadius: 8, padding: 10, marginTop: 8 },
  critLbl: { color: '#f87171', fontSize: 11, fontWeight: '800' },
  critTxt: { color: '#fca5a5', fontSize: 12, marginTop: 4, lineHeight: 17 },
});
