/**
 * /intelligence — Code Intelligence
 * Auto-document, generate-tests, predict-bugs, analyze-architecture, etc.
 */
import { useState, useCallback } from 'react';
import {
  View, Text, TextInput, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, StatusBar, SafeAreaView, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useRouteHistory } from '../utils/routeHistory';
import { shareResult, copyToClipboard } from '../utils/shareResult';
import { jeevesSpeak } from '../features/Academy/jeevesTts';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const LANGS = ['python','javascript','typescript','rust','go','java','cpp','c'];

type Action = {
  id: string;
  endpoint: string;
  label: string;
  icon: keyof typeof import('@expo/vector-icons').Ionicons.glyphMap;
  tint: string;
  desc: string;
  buildBody: (code: string, lang: string) => any;
  extractResult: (j: any) => string;
};

const ACTIONS: Action[] = [
  { id: 'auto-document', endpoint: '/api/intelligence/auto-document', label: 'Auto-document', icon: 'document-text', tint: '#a78bfa', desc: 'Generate full docstrings & comments',
    buildBody: (code, lang) => ({ code, language: lang, style: 'google' }),
    extractResult: j => j?.documentation || j?.documented_code || JSON.stringify(j).slice(0, 600) },
  { id: 'generate-tests', endpoint: '/api/intelligence/generate-tests', label: 'Generate tests', icon: 'flask', tint: '#10B981', desc: 'Full pytest / jest suite',
    buildBody: (code, lang) => ({ code, language: lang, framework: 'pytest' }),
    extractResult: j => j?.tests || j?.test_code || JSON.stringify(j).slice(0, 600) },
  { id: 'migrate', endpoint: '/api/intelligence/migrate', label: 'Migrate to another language', icon: 'swap-horizontal', tint: '#3B82F6', desc: 'Port to JavaScript / Rust / etc.',
    buildBody: (code, lang) => ({ source_code: code, source_language: lang, target_language: 'javascript' }),
    extractResult: j => j?.migrated_code || j?.code || JSON.stringify(j).slice(0, 600) },
  { id: 'analyze-architecture', endpoint: '/api/intelligence/analyze-architecture', label: 'Analyse architecture', icon: 'git-network', tint: '#fbbf24', desc: 'Modularity, coupling, smells',
    buildBody: (code, lang) => ({ code, language: lang }),
    extractResult: j => j?.analysis || j?.architecture || JSON.stringify(j).slice(0, 800) },
  { id: 'design-api', endpoint: '/api/intelligence/design-api', label: 'Design an API', icon: 'cloud', tint: '#8B5CF6', desc: 'REST / GraphQL schema',
    buildBody: (code, lang) => ({ requirements: code }),
    extractResult: j => j?.api_design || j?.design || JSON.stringify(j).slice(0, 800) },
];

export default function IntelligenceScreen() {
  const router = useRouter();
  const [lang, setLang] = useState('python');
  const [code, setCode] = useState("def fib(n):\n    if n < 2:\n        return n\n    return fib(n-1) + fib(n-2)\n");
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<{ action: string; text: string } | null>(null);
  const [err, setErr] = useState('');
  const history = useRouteHistory<{ actionId: string; actionLabel: string; lang: string; preview: string }>('intelligence');

  const run = useCallback(async (a: Action) => {
    setBusy(a.id); setErr(''); setResult(null);
    try {
      const r = await fetch(`${BACKEND}${a.endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(a.buildBody(code, lang)),
      });
      const j = await r.json();
      const text = a.extractResult(j);
      const cleaned = String(text).slice(0, 4000);
      setResult({ action: a.label, text: cleaned });
      await history.push({
        label: `${a.label} · ${lang}`,
        preview: cleaned.split('\n')[0]?.slice(0, 60),
        payload: { actionId: a.id, actionLabel: a.label, lang, preview: cleaned.slice(0, 200) },
      });
      jeevesSpeak(`${a.label} complete.`, { context: 'celebration', prependCatchphrase: false });
    } catch (e: any) {
      setErr(String(e?.message || e).slice(0, 200));
    } finally { setBusy(null); }
  }, [code, lang, history]);

  return (
    <SafeAreaView style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor="#0A0A0A" />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="chevron-back" size={22} color="#F5C451" />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={s.title}>💡 Code Intelligence</Text>
            <Text style={s.subtitle}>Auto-document · test-gen · migrate · architecture</Text>
          </View>
        </View>

        <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 80 }}>
          <Text style={s.sectionLabel}>Language</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
            {LANGS.map(l => (
              <TouchableOpacity key={l} style={[s.chip, lang === l && s.chipActive]} onPress={() => setLang(l)}>
                <Text style={[s.chipText, lang === l && s.chipTextActive]}>{l}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

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

          <Text style={[s.sectionLabel, { marginTop: 12 }]}>Actions</Text>
          {ACTIONS.map(a => (
            <TouchableOpacity
              key={a.id}
              style={[s.actionBtn, { borderColor: a.tint + '55' }]}
              onPress={() => run(a)}
              disabled={!!busy}
              activeOpacity={0.8}
            >
              <View style={[s.actionIcon, { backgroundColor: a.tint + '22', borderColor: a.tint }]}>
                <Ionicons name={a.icon} size={16} color={a.tint} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={s.actionLabel}>{a.label}</Text>
                <Text style={s.actionDesc}>{a.desc}</Text>
              </View>
              {busy === a.id ? <ActivityIndicator color={a.tint} /> : <Ionicons name="play-circle" size={18} color={a.tint} />}
            </TouchableOpacity>
          ))}

          {err ? <View style={s.errBox}><Text style={s.errText}>⚠ {err}</Text></View> : null}
          {result && (
            <View style={s.resultBox}>
              <View style={s.resultHead}>
                <Ionicons name="sparkles" size={14} color="#F5C451" />
                <Text style={s.resultHeadText}>{result.action}</Text>
              </View>
              <Text style={s.resultText}>{result.text}</Text>
              <View style={s.bridgeRow}>
                <TouchableOpacity
                  style={[s.bridgeBtn, { backgroundColor: '#F59E0B22', borderColor: '#F59E0B' }]}
                  onPress={() => router.push({ pathname: '/playground', params: { lang, code: result.text } } as any)}
                >
                  <Ionicons name="flask" size={13} color="#F59E0B" />
                  <Text style={[s.bridgeText, { color: '#F59E0B' }]}>Playground</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.bridgeBtn, { backgroundColor: '#EF444422', borderColor: '#EF4444' }]}
                  onPress={() => router.push({ pathname: '/debugger', params: { lang, code: result.text } } as any)}
                >
                  <Ionicons name="bug" size={13} color="#EF4444" />
                  <Text style={[s.bridgeText, { color: '#EF4444' }]}>Debug</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.bridgeBtn, { backgroundColor: '#10B98122', borderColor: '#10B981' }]}
                  onPress={() => copyToClipboard(result.text, 'Result copied')}
                >
                  <Ionicons name="copy" size={13} color="#10B981" />
                  <Text style={[s.bridgeText, { color: '#10B981' }]}>Copy</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.bridgeBtn, { backgroundColor: '#A78BFA22', borderColor: '#A78BFA' }]}
                  onPress={() => shareResult(result.text, result.action)}
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
  chipActive: { backgroundColor: '#F5C45133', borderColor: '#F5C451' },
  chipText: { color: '#94a3b8', fontSize: 11, fontWeight: '600' },
  chipTextActive: { color: '#F5C451', fontWeight: '700' },
  editor: { minHeight: 140, maxHeight: 240, color: '#f1f5f9', fontSize: 13, lineHeight: 18, padding: 14, backgroundColor: '#141414', borderRadius: 10, borderWidth: 1, borderColor: '#1F1F1F', fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  actionBtn: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#141414', borderRadius: 12, padding: 12, borderWidth: 1, marginBottom: 6 },
  actionIcon: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  actionLabel: { color: '#f1f5f9', fontSize: 13, fontWeight: '700' },
  actionDesc: { color: '#94a3b8', fontSize: 10, marginTop: 2 },
  errBox: { marginTop: 10, padding: 10, borderRadius: 8, backgroundColor: '#f8717122', borderColor: '#f87171', borderWidth: 1 },
  errText: { color: '#fecaca', fontSize: 11 },
  resultBox: { marginTop: 12, padding: 14, backgroundColor: '#141414', borderRadius: 12, borderWidth: 1, borderColor: '#F5C45155' },
  resultHead: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  resultHeadText: { color: '#F5C451', fontSize: 11, fontWeight: '900', textTransform: 'uppercase', letterSpacing: 1 },
  resultText: { color: '#cbd5e1', fontSize: 12, lineHeight: 18, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  openInPlayground: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 10, padding: 8, borderRadius: 8, backgroundColor: '#F59E0B22', borderColor: '#F59E0B', borderWidth: 1 },
  playText: { color: '#F59E0B', fontSize: 11, fontWeight: '700' },
  bridgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  bridgeBtn: { flex: 1, minWidth: 80, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 10, paddingHorizontal: 8, borderRadius: 8, borderWidth: 1 },
  bridgeText: { fontSize: 10, fontWeight: '800' },
});
