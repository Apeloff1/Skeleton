/**
 * src/components/ChurnPanel.tsx — PROOD Churn / quality-iteration panel.
 *
 * A real, self-contained upgrade of the shipped stub. Runs the autonomous
 * quality-iteration workflow (Prompt → … → Deploy) and surfaces the climbing
 * quality trend. No cyan palette (per project constraint).
 */
import React from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../utils/apiClient';

const GREEN = '#22c55e';
const BLUE = '#3b82f6';
const AMBER = '#f59e0b';
const CARD = '#111827';
const MUTE = '#94a3b8';

export default function ChurnPanel({ projectName = 'ChurnQuick' }: { projectName?: string }) {
  const [prompt, setPrompt] = React.useState('A tight roguelike with emergent combat and meaningful upgrades');
  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<any>(null);
  const [err, setErr] = React.useState('');

  const runChurn = async () => {
    const p = prompt.trim();
    if (!p || busy) return;
    setBusy(true); setErr(''); setResult(null);
    const r = await api.post<any>('/api/gameforge/workflow/run',
      { prompt: p, project_name: projectName, max_iterations: 4 }, { timeoutMs: 118000 });
    if (r.ok && r.data?.ok) setResult(r.data);
    else setErr(r.data?.detail || 'Churn failed — please retry.');
    setBusy(false);
  };

  const q = Math.round((result?.final_quality ?? 0) * 100);
  const col = q >= 85 ? GREEN : q > 0 ? AMBER : MUTE;

  return (
    <View style={s.wrap}>
      <View style={s.head}>
        <Ionicons name="git-compare" size={16} color={GREEN} />
        <Text style={s.title}>Churn Pipeline</Text>
      </View>
      <TextInput
        testID="churn-prompt" style={s.input} value={prompt} onChangeText={setPrompt}
        placeholder="Describe the game to iterate…" placeholderTextColor={MUTE}
        editable={!busy} multiline
      />
      <TouchableOpacity testID="churn-run" style={[s.btn, { backgroundColor: GREEN }]} onPress={runChurn} disabled={busy}>
        {busy ? <ActivityIndicator color="#04120a" size="small" />
          : <Text style={s.btnTxt}>▶ Run Churn</Text>}
      </TouchableOpacity>
      {!!err && <Text style={[s.trend, { color: '#ef4444' }]}>{err}</Text>}
      {result && (
        <View style={s.resultBox}>
          <Text style={[s.qBig, { color: col }]}>{q}%</Text>
          <Text style={s.qLbl}>final quality · {result.iterations_run} iters · {result.deploy_ready ? 'deploy-ready' : 'iterating'}</Text>
          <Text style={s.trend}>{(result.quality_history || []).map((x: number) => `${Math.round(x * 100)}%`).join('  →  ')}</Text>
        </View>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { backgroundColor: CARD, borderRadius: 14, padding: 12 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  title: { color: '#e2e8f0', fontSize: 13, fontWeight: '800' },
  input: {
    backgroundColor: '#0b1220', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10,
    color: '#f1f5f9', fontSize: 13, borderWidth: StyleSheet.hairlineWidth, borderColor: '#243043',
    minHeight: 54, textAlignVertical: 'top',
  },
  btn: { borderRadius: 10, paddingVertical: 12, alignItems: 'center', marginTop: 10 },
  btnTxt: { color: '#04120a', fontSize: 13, fontWeight: '800' },
  resultBox: { alignItems: 'center', marginTop: 12 },
  qBig: { fontSize: 34, fontWeight: '900' },
  qLbl: { color: MUTE, fontSize: 11, marginTop: 2 },
  trend: { color: BLUE, fontSize: 12, marginTop: 8, textAlign: 'center', lineHeight: 18 },
});
