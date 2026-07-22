/**
 * /debugger — AI Debugger
 * Analyse code at quick / standard / deep levels via /api/debugger/analyze
 */
import { useState, useCallback } from 'react';
import {
  View, Text, TextInput, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, StatusBar, SafeAreaView, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useRouteHistory } from '../utils/routeHistory';
import { shareResult, copyToClipboard } from '../utils/shareResult';
import { jeevesSpeak } from '../features/Academy/jeevesTts';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const LEVELS: { id: 'quick'|'standard'|'deep'; label: string; desc: string }[] = [
  { id: 'quick',    label: 'Quick',    desc: '< 5s · obvious errors' },
  { id: 'standard', label: 'Standard', desc: '< 15s · with fixes' },
  { id: 'deep',     label: 'Deep',     desc: '< 30s · sec + perf audit' },
];
const LANGS = ['python','javascript','typescript','java','cpp','c','rust','go','swift','kotlin','ruby','php'];

// Classic bug presets — tap to load straight into the editor.
const PRESETS: { label: string; lang: string; code: string }[] = [
  { label: 'Divide by zero (py)', lang: 'python',
    code: 'def divide(a, b):\n    return a / b\n\nprint(divide(1, 0))\n' },
  { label: 'Off-by-one (js)', lang: 'javascript',
    code: 'function lastItem(arr) {\n  return arr[arr.length];\n}\nconsole.log(lastItem([1,2,3]));\n' },
  { label: 'Race condition (go)', lang: 'go',
    code: 'package main\n\nvar counter int\nfunc main() {\n  for i := 0; i < 100; i++ {\n    go func() { counter++ }()\n  }\n  println(counter)\n}\n' },
  { label: 'Mutable default (py)', lang: 'python',
    code: 'def append_item(item, target=[]):\n    target.append(item)\n    return target\n\nprint(append_item(1))\nprint(append_item(2))\n' },
  { label: 'SQL injection (py)', lang: 'python',
    code: 'def get_user(uid):\n    return db.exec(f"SELECT * FROM users WHERE id={uid}")\n' },
];

export default function DebuggerScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ code?: string; language?: string }>();
  const [lang, setLang] = useState<string>(typeof params?.language === 'string' ? params.language : 'python');
  const [code, setCode] = useState<string>(typeof params?.code === 'string' ? params.code : "def divide(a, b):\n    return a / b\n\nprint(divide(1, 0))\n");
  const [level, setLevel] = useState<'quick'|'standard'|'deep'>('standard');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState('');
  const history = useRouteHistory<{ code: string; lang: string; level: string; severity?: string; issues_found?: number }>('debugger');

  const run = useCallback(async () => {
    setBusy(true); setErr(''); setResult(null);
    try {
      const r = await fetch(`${BACKEND}/api/debugger/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, language: lang, level }),
      });
      const j = await r.json();
      setResult(j);
      // Persist + Jeeves chime — context flips by severity
      const sev = String(j?.severity || '').toLowerCase();
      const issues = j?.issues_found ?? 0;
      await history.push({
        label: `${lang} · ${level} · ${issues} issue${issues === 1 ? '' : 's'}`,
        preview: code.split('\n')[0]?.slice(0, 60),
        payload: { code, lang, level, severity: sev, issues_found: issues },
      });
      const ctx = sev.startsWith('crit') || sev.startsWith('high') ? 'alert' :
                  issues === 0 ? 'celebration' : 'debug';
      jeevesSpeak(
        issues === 0 ? 'Splendid. No issues detected.' :
        `Found ${issues} ${sev || 'standard'}-severity ${issues === 1 ? 'issue' : 'issues'}. Inspect the analysis below.`,
        { context: ctx, prependCatchphrase: false },
      );
    } catch (e: any) {
      setErr(String(e?.message || e).slice(0, 200));
    } finally { setBusy(false); }
  }, [code, lang, level, history]);

  const sevColor = (s?: string) => {
    const k = (s || '').toLowerCase();
    if (k.startsWith('crit')) return '#ef4444';
    if (k.startsWith('high')) return '#f97316';
    if (k.startsWith('med')) return '#fbbf24';
    if (k.startsWith('low')) return '#10B981';
    return '#94a3b8';
  };

  return (
    <SafeAreaView style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor="#0A0A0A" />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="chevron-back" size={22} color="#EF4444" />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={s.title}>🐛 AI Debugger</Text>
            <Text style={s.subtitle}>12 languages · 3 depths · actionable fixes</Text>
          </View>
        </View>

        <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 80 }}>
          {/* Language chips */}
          <Text style={s.sectionLabel}>Language</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
            {LANGS.map(l => (
              <TouchableOpacity key={l} style={[s.chip, lang === l && s.chipActive]} onPress={() => setLang(l)}>
                <Text style={[s.chipText, lang === l && s.chipTextActive]}>{l}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          {/* Level */}
          <Text style={[s.sectionLabel, { marginTop: 12 }]}>Analysis depth</Text>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            {LEVELS.map(L => {
              const active = level === L.id;
              return (
                <TouchableOpacity
                  key={L.id}
                  style={[s.levelCard, active && s.levelCardActive]}
                  onPress={() => setLevel(L.id)}
                  activeOpacity={0.8}
                >
                  <Text style={[s.levelLabel, active && { color: '#EF4444' }]}>{L.label}</Text>
                  <Text style={s.levelDesc}>{L.desc}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {/* Presets row — load classic bug examples */}
          <Text style={[s.sectionLabel, { marginTop: 12 }]}>Quick examples</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
            {PRESETS.map(p => (
              <TouchableOpacity
                key={p.label}
                style={s.presetChip}
                onPress={() => { setCode(p.code); setLang(p.lang); }}
              >
                <Ionicons name="flash-outline" size={11} color="#EF4444" />
                <Text style={s.presetText}>{p.label}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          {/* Recent history — tap to reload */}
          {history.items.length > 0 && (
            <>
              <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 12, marginBottom: 6 }}>
                <Text style={[s.sectionLabel, { flex: 1, marginBottom: 0 }]}>Recent ({history.items.length})</Text>
                <TouchableOpacity onPress={history.clear}>
                  <Text style={{ color: '#94a3b8', fontSize: 10, fontWeight: '700' }}>CLEAR</Text>
                </TouchableOpacity>
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
                {history.items.slice(0, 8).map(h => (
                  <TouchableOpacity
                    key={h.id}
                    style={s.histChip}
                    onPress={() => {
                      setCode(h.payload.code);
                      setLang(h.payload.lang);
                      setLevel(h.payload.level as any);
                    }}
                  >
                    <Text style={s.histLabel} numberOfLines={1}>{h.label}</Text>
                    <Text style={s.histPrev} numberOfLines={1}>{h.preview}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </>
          )}

          {/* Code editor */}
          <Text style={[s.sectionLabel, { marginTop: 12 }]}>Code</Text>
          <TextInput
            value={code}
            onChangeText={setCode}
            multiline
            style={s.editor}
            placeholder={`Paste ${lang} code here…`}
            placeholderTextColor="#475569"
            autoCapitalize="none"
            autoCorrect={false}
            spellCheck={false}
            textAlignVertical="top"
          />

          {/* Run */}
          <TouchableOpacity
            onPress={run}
            disabled={busy || !code.trim()}
            style={[s.runBtn, (busy || !code.trim()) && { opacity: 0.4 }]}
          >
            {busy ? <ActivityIndicator color="#0A0A0A" /> : (
              <>
                <Ionicons name="flash" size={16} color="#0A0A0A" />
                <Text style={s.runText}>Analyse</Text>
              </>
            )}
          </TouchableOpacity>

          {/* Result */}
          {err ? (
            <View style={s.errBox}><Text style={s.errText}>⚠ {err}</Text></View>
          ) : null}
          {result && (
            <View style={s.resultBox}>
              <View style={s.resultHead}>
                <Ionicons name="shield-checkmark" size={16} color={sevColor(result.severity)} />
                <Text style={[s.resultTitle, { color: sevColor(result.severity) }]}>
                  {result.issues_found ?? 0} issue{result.issues_found === 1 ? '' : 's'}
                </Text>
                {!!result.severity && (
                  <View style={[s.sevBadge, { borderColor: sevColor(result.severity), backgroundColor: sevColor(result.severity) + '22' }]}>
                    <Text style={[s.sevText, { color: sevColor(result.severity) }]}>{String(result.severity).toUpperCase()}</Text>
                  </View>
                )}
              </View>
              {!!result?.analysis?.raw_analysis && (
                <Text style={s.analysis}>{result.analysis.raw_analysis}</Text>
              )}
              <View style={s.bridgeRow}>
                <TouchableOpacity
                  style={[s.bridgeBtn, { backgroundColor: '#F59E0B22', borderColor: '#F59E0B' }]}
                  onPress={() => router.push({ pathname: '/playground', params: { lang, code } } as any)}
                >
                  <Ionicons name="flask" size={13} color="#F59E0B" />
                  <Text style={[s.bridgeText, { color: '#F59E0B' }]}>Playground</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.bridgeBtn, { backgroundColor: '#F5C45122', borderColor: '#F5C451' }]}
                  onPress={() => router.push({ pathname: '/intelligence', params: { lang, code } } as any)}
                >
                  <Ionicons name="bulb" size={13} color="#F5C451" />
                  <Text style={[s.bridgeText, { color: '#F5C451' }]}>Intelligence</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.bridgeBtn, { backgroundColor: '#10B98122', borderColor: '#10B981' }]}
                  onPress={() => copyToClipboard(result?.analysis?.raw_analysis || JSON.stringify(result, null, 2), 'Analysis copied')}
                >
                  <Ionicons name="copy" size={13} color="#10B981" />
                  <Text style={[s.bridgeText, { color: '#10B981' }]}>Copy</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.bridgeBtn, { backgroundColor: '#A78BFA22', borderColor: '#A78BFA' }]}
                  onPress={() => shareResult(result?.analysis?.raw_analysis || JSON.stringify(result, null, 2), 'Debug analysis')}
                >
                  <Ionicons name="share-social" size={13} color="#A78BFA" />
                  <Text style={[s.bridgeText, { color: '#A78BFA' }]}>Share</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0A0A0A' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 14, paddingVertical: 10, borderBottomColor: '#1F1F1F', borderBottomWidth: 1 },
  backBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  title: { color: '#f1f5f9', fontSize: 16, fontWeight: '900' },
  subtitle: { color: '#94a3b8', fontSize: 11, marginTop: 2 },
  sectionLabel: { color: '#94a3b8', fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 },
  chip: { paddingHorizontal: 12, paddingVertical: 8, minHeight: 34, borderRadius: 14, backgroundColor: '#141414', borderWidth: 1, borderColor: '#1F1F1F' },
  chipActive: { backgroundColor: '#EF444433', borderColor: '#EF4444' },
  chipText: { color: '#94a3b8', fontSize: 11, fontWeight: '600' },
  chipTextActive: { color: '#EF4444', fontWeight: '700' },
  levelCard: { flex: 1, padding: 10, borderRadius: 10, backgroundColor: '#141414', borderWidth: 1, borderColor: '#1F1F1F' },
  levelCardActive: { backgroundColor: '#EF444422', borderColor: '#EF4444' },
  levelLabel: { color: '#f1f5f9', fontSize: 12, fontWeight: '800', marginBottom: 2 },
  levelDesc: { color: '#94a3b8', fontSize: 9 },
  editor: { minHeight: 160, maxHeight: 280, color: '#f1f5f9', fontSize: 13, lineHeight: 18, padding: 14, backgroundColor: '#141414', borderRadius: 10, borderWidth: 1, borderColor: '#1F1F1F', fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  runBtn: { marginTop: 12, paddingVertical: 12, borderRadius: 10, backgroundColor: '#EF4444', alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8 },
  runText: { color: '#0A0A0A', fontSize: 14, fontWeight: '900' },
  errBox: { marginTop: 10, padding: 10, borderRadius: 8, backgroundColor: '#f8717122', borderColor: '#f87171', borderWidth: 1 },
  errText: { color: '#fecaca', fontSize: 11 },
  resultBox: { marginTop: 12, padding: 14, backgroundColor: '#141414', borderRadius: 12, borderWidth: 1, borderColor: '#EF444455' },
  resultHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  resultTitle: { fontSize: 14, fontWeight: '900', flex: 1 },
  sevBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8, borderWidth: 1 },
  sevText: { fontSize: 9, fontWeight: '800' },
  analysis: { color: '#cbd5e1', fontSize: 12, lineHeight: 18, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  fixBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 10, padding: 10, borderRadius: 8, backgroundColor: '#F59E0B22', borderColor: '#F59E0B', borderWidth: 1 },
  fixText: { color: '#F59E0B', fontSize: 12, fontWeight: '700' },
  presetChip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 8, minHeight: 32, borderRadius: 8, backgroundColor: '#EF444422', borderWidth: 1, borderColor: '#EF444455' },
  presetText: { color: '#FCA5A5', fontSize: 10, fontWeight: '700' },
  histChip: { padding: 8, borderRadius: 8, backgroundColor: '#141414', borderWidth: 1, borderColor: '#1F1F1F', minWidth: 130, maxWidth: 180 },
  histLabel: { color: '#cbd5e1', fontSize: 11, fontWeight: '700' },
  histPrev: { color: '#64748b', fontSize: 9, marginTop: 2, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  bridgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  bridgeBtn: { flex: 1, minWidth: 80, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 10, paddingHorizontal: 8, borderRadius: 8, borderWidth: 1 },
  bridgeText: { fontSize: 10, fontWeight: '800' },
});
