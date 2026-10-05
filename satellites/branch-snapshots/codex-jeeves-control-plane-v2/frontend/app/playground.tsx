/**
 * /playground — Full Code Playground IDE.
 *
 * Multi-language code editor + run + output panel.
 * Wired to POST /api/playground/run.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TextInput, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, StatusBar, SafeAreaView, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useRouteHistory } from '../utils/routeHistory';
import { shareResult, copyToClipboard } from '../utils/shareResult';
import { jeevesSpeak } from '../features/Academy/jeevesTts';
import { useAutosave } from '../utils/useAutosave';
import { withScreenGuard } from '../components/withScreenGuard';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const USER_ID = 'default_user';

type Lang = { id: string; name?: string; runtime?: string };

const STARTERS: Record<string, string> = {
  python:     "print('Hello, Jeeves!')\n\nfor i in range(5):\n    print(i, i*i)\n",
  javascript: "console.log('Hello, Jeeves!');\nfor (let i = 0; i < 5; i++) console.log(i, i*i);\n",
  typescript: "const greet = (name: string) => `Hello, ${name}!`;\nconsole.log(greet('Jeeves'));\n",
  go:         "package main\nimport \"fmt\"\nfunc main() {\n  fmt.Println(\"Hello, Jeeves!\")\n}\n",
  rust:       "fn main() {\n    println!(\"Hello, Jeeves!\");\n}\n",
  c:          "#include <stdio.h>\nint main() {\n  printf(\"Hello, Jeeves!\\n\");\n  return 0;\n}\n",
  cpp:        "#include <iostream>\nint main(){ std::cout << \"Hello, Jeeves!\\n\"; }\n",
  bash:       "echo 'Hello, Jeeves!'\nfor i in 1 2 3; do echo $i; done\n",
};

function PlaygroundScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ lang?: string; code?: string }>();
  const [langs, setLangs] = useState<Lang[]>([]);
  const [lang, setLang] = useState<string>(typeof params?.lang === 'string' ? params.lang : 'python');
  // 2026-02 — useAutosave preserves the user's last draft across app restarts.
  // If they're routed through /safe-mode and back, or accidentally background
  // the app, their code survives. Key is per-language so switching langs
  // restores the last code FOR THAT LANG.
  const [code, setCode] = useAutosave<string>(
    `playground:code:${lang}`,
    typeof params?.code === 'string' ? params.code : (STARTERS[lang] || ''),
  );
  const [running, setRunning] = useState(false);
  const [output, setOutput] = useState<string>('');
  const [stderr, setStderr] = useState<string>('');
  const [exitCode, setExitCode] = useState<number | null>(null);
  const [xp, setXp] = useState<number>(0);
  const [err, setErr] = useState<string>('');
  const history = useRouteHistory<{ lang: string; code: string; exit?: number }>('playground');

  // Fetch languages once
  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${BACKEND}/api/playground/languages`);
        const j = await r.json();
        const arr: Lang[] = (j?.languages || j || []).map((l: any) =>
          typeof l === 'string' ? { id: l } : { id: l?.id || l?.name, name: l?.name, runtime: l?.runtime }
        );
        setLangs(arr);
      } catch (e: any) {
        setErr(String(e?.message || e).slice(0, 120));
      }
    })();
  }, []);

  // Switch language → swap starter code (only if code is unchanged from previous starter)
  const switchLang = useCallback((newLang: string) => {
    setLang(newLang);
    const oldStarter = STARTERS[lang];
    if (!code || code === oldStarter) {
      setCode(STARTERS[newLang] || '');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang, code]);

  const run = useCallback(async () => {
    setRunning(true); setErr(''); setOutput(''); setStderr(''); setExitCode(null);
    try {
      const r = await fetch(`${BACKEND}/api/playground/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: lang, code, user_id: USER_ID }),
      });
      const j = await r.json();
      setOutput(j?.output || '');
      setStderr(j?.error || '');
      setExitCode(j?.exit_code ?? null);
      if (j?.xp_awarded) setXp(v => v + j.xp_awarded);
      // Persist + Jeeves chime — flips by exit code
      const ec = j?.exit_code ?? null;
      await history.push({
        label: `${lang} · exit ${ec ?? '?'}`,
        preview: code.split('\n')[0]?.slice(0, 60),
        payload: { lang, code, exit: ec ?? undefined },
      });
      jeevesSpeak(
        ec === 0 ? 'Program ran cleanly.' :
        ec == null ? 'Execution complete.' :
        `Exited with code ${ec}. Inspect stderr.`,
        { context: ec === 0 ? 'celebration' : ec == null ? 'transition' : 'gentle_correction', prependCatchphrase: false },
      );
    } catch (e: any) {
      setErr(String(e?.message || e).slice(0, 200));
    } finally {
      setRunning(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang, code]);

  const reset = () => setCode(STARTERS[lang] || '');
  const clear = () => { setOutput(''); setStderr(''); setExitCode(null); };

  return (
    <SafeAreaView style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor="#0A0A0A" />

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        {/* Header */}
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="chevron-back" size={22} color="#F59E0B" />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={s.title}>🧪 Code Playground</Text>
            <Text style={s.subtitle}>{langs.length} languages · +{xp} XP this session</Text>
          </View>
          <TouchableOpacity onPress={reset} style={s.iconBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="refresh" size={18} color="#94a3b8" />
          </TouchableOpacity>
        </View>

        {/* Language chips */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chipRow}>
          {langs.length === 0 ? (
            <ActivityIndicator size="small" color="#F59E0B" style={{ marginLeft: 12 }} />
          ) : langs.map(l => {
            const active = l.id === lang;
            return (
              <TouchableOpacity
                key={l.id}
                style={[s.chip, active && s.chipActive]}
                onPress={() => switchLang(l.id)}
              >
                <Text style={[s.chipText, active && s.chipTextActive]} numberOfLines={1}>{l.name || l.id}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        {/* Editor */}
        <View style={s.editorBox}>
          <View style={s.editorHeader}>
            <Ionicons name="code-slash" size={14} color="#F59E0B" />
            <Text style={s.editorTitle}>{lang}.{lang === 'python' ? 'py' : lang === 'javascript' ? 'js' : lang === 'typescript' ? 'ts' : lang}</Text>
            <View style={{ flex: 1 }} />
            <Text style={s.charCount}>{code.length} chars · {code.split('\n').length} lines</Text>
          </View>
          <TextInput
            value={code}
            onChangeText={setCode}
            multiline
            style={s.editor}
            placeholder="Write your code here…"
            placeholderTextColor="#475569"
            autoCapitalize="none"
            autoCorrect={false}
            spellCheck={false}
            textAlignVertical="top"
          />
        </View>

        {/* Run controls */}
        <View style={s.controlRow}>
          <TouchableOpacity
            onPress={run}
            disabled={running || !code.trim()}
            style={[s.runBtn, (running || !code.trim()) && s.runBtnDisabled]}
          >
            {running ? (
              <ActivityIndicator size="small" color="#0A0A0A" />
            ) : (
              <>
                <Ionicons name="play" size={16} color="#0A0A0A" />
                <Text style={s.runBtnText}>Run</Text>
              </>
            )}
          </TouchableOpacity>
          <TouchableOpacity onPress={clear} style={s.clearBtn}>
            <Ionicons name="trash-outline" size={14} color="#94a3b8" />
            <Text style={s.clearText}>Clear output</Text>
          </TouchableOpacity>
          {exitCode != null && (
            <View style={[s.exitBadge, { backgroundColor: exitCode === 0 ? '#10B98122' : '#f8717122', borderColor: exitCode === 0 ? '#10B981' : '#f87171' }]}>
              <Text style={[s.exitText, { color: exitCode === 0 ? '#10B981' : '#f87171' }]}>exit {exitCode}</Text>
            </View>
          )}
        </View>

        {/* Recent runs — tap to reload */}
        {history.items.length > 0 && (
          <View style={s.histStrip}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, paddingHorizontal: 12 }}>
              <View style={s.histLabelBox}>
                <Ionicons name="time-outline" size={11} color="#94a3b8" />
                <Text style={s.histLabel}>recent</Text>
              </View>
              {history.items.slice(0, 10).map(h => (
                <TouchableOpacity
                  key={h.id}
                  onPress={() => { setLang(h.payload.lang); setCode(h.payload.code); }}
                  style={[
                    s.histChip,
                    { borderColor: h.payload.exit === 0 ? '#10B98155' : h.payload.exit == null ? '#1F1F1F' : '#f8717155' },
                  ]}
                >
                  <Text style={s.histLabelVal} numberOfLines={1}>{h.label}</Text>
                </TouchableOpacity>
              ))}
              <TouchableOpacity onPress={history.clear} style={s.histChip}>
                <Text style={[s.histLabelVal, { color: '#94a3b8' }]}>clear</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>
        )}

        {/* Bridge row — forward code to other power routes */}
        <View style={s.bridgeRow}>
          <TouchableOpacity
            style={[s.bridgeBtn, { backgroundColor: '#EF444422', borderColor: '#EF4444' }]}
            onPress={() => router.push({ pathname: '/debugger', params: { lang, code } } as any)}
          >
            <Ionicons name="bug" size={13} color="#EF4444" />
            <Text style={[s.bridgeText, { color: '#EF4444' }]}>Debug</Text>
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
            onPress={() => copyToClipboard(output || code, output ? 'Output copied' : 'Code copied')}
          >
            <Ionicons name="copy" size={13} color="#10B981" />
            <Text style={[s.bridgeText, { color: '#10B981' }]}>Copy</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.bridgeBtn, { backgroundColor: '#A78BFA22', borderColor: '#A78BFA' }]}
            onPress={() => shareResult(`Language: ${lang}\n\n--- CODE ---\n${code}\n\n--- OUTPUT ---\n${output || '(none)'}\n${stderr ? '\n--- STDERR ---\n' + stderr : ''}`, 'Playground run')}
          >
            <Ionicons name="share-social" size={13} color="#A78BFA" />
            <Text style={[s.bridgeText, { color: '#A78BFA' }]}>Share</Text>
          </TouchableOpacity>
        </View>

        {/* Output */}
        <View style={s.outputBox}>
          <View style={s.outputHeader}>
            <Ionicons name="terminal" size={13} color="#94a3b8" />
            <Text style={s.outputHeaderText}>Output</Text>
          </View>
          <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 10 }}>
            {err ? <Text style={s.outputErr}>⚠️ {err}</Text> : null}
            {output ? <Text style={s.outputText}>{output}</Text> : null}
            {stderr ? <Text style={s.outputErr}>{stderr}</Text> : null}
            {!output && !stderr && !err && !running ? <Text style={s.outputPlaceholder}>(no output yet — hit Run)</Text> : null}
          </ScrollView>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0A0A0A' },
  header: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingHorizontal: 14, paddingVertical: 10,
    borderBottomColor: '#1F1F1F', borderBottomWidth: 1,
  },
  backBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  iconBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  title: { color: '#f1f5f9', fontSize: 16, fontWeight: '900' },
  subtitle: { color: '#94a3b8', fontSize: 11, marginTop: 2 },
  chipRow: { paddingHorizontal: 12, paddingTop: 10, paddingBottom: 4, gap: 6, maxHeight: 50 },
  chip: {
    paddingHorizontal: 12, paddingVertical: 8, minHeight: 34, borderRadius: 14,
    backgroundColor: '#141414', borderWidth: 1, borderColor: '#1F1F1F',
    marginRight: 6,
  },
  chipActive: { backgroundColor: '#F59E0B33', borderColor: '#F59E0B' },
  chipText: { color: '#94a3b8', fontSize: 11, fontWeight: '600' },
  chipTextActive: { color: '#F59E0B', fontWeight: '700' },
  editorBox: {
    margin: 12,
    backgroundColor: '#141414', borderRadius: 12,
    borderWidth: 1, borderColor: '#1F1F1F',
    overflow: 'hidden',
  },
  editorHeader: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 12, paddingVertical: 8,
    backgroundColor: '#0a1020',
    borderBottomColor: '#1F1F1F', borderBottomWidth: 1,
  },
  editorTitle: { color: '#cbd5e1', fontSize: 12, fontWeight: '700', fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  charCount: { color: '#64748b', fontSize: 10 },
  editor: {
    minHeight: 180, maxHeight: 240,
    color: '#f1f5f9', fontSize: 13, lineHeight: 18,
    padding: 14,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  controlRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: 12, paddingBottom: 8,
  },
  runBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: 18, paddingVertical: 10,
    backgroundColor: '#F59E0B', borderRadius: 10,
  },
  runBtnDisabled: { opacity: 0.4 },
  runBtnText: { color: '#0A0A0A', fontSize: 14, fontWeight: '900', letterSpacing: 0.5 },
  clearBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 8 },
  clearText: { color: '#94a3b8', fontSize: 11 },
  exitBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8, borderWidth: 1 },
  exitText: { fontSize: 10, fontWeight: '800' },
  outputBox: {
    flex: 1, marginHorizontal: 12, marginBottom: 12,
    backgroundColor: '#000', borderRadius: 12,
    borderWidth: 1, borderColor: '#1F1F1F',
    overflow: 'hidden',
  },
  outputHeader: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 12, paddingVertical: 8,
    backgroundColor: '#0A0A0A',
    borderBottomColor: '#1F1F1F', borderBottomWidth: 1,
  },
  outputHeaderText: { color: '#94a3b8', fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1 },
  outputText: { color: '#a3e635', fontSize: 12, lineHeight: 16, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  outputErr: { color: '#f87171', fontSize: 12, lineHeight: 16, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  outputPlaceholder: { color: '#475569', fontSize: 11, fontStyle: 'italic' },
  histStrip: { paddingVertical: 10, borderBottomColor: '#1F1F1F', borderBottomWidth: 1 },
  histLabelBox: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 6 },
  histLabel: { color: '#94a3b8', fontSize: 9, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1 },
  histChip: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, borderWidth: 1, backgroundColor: '#141414', maxWidth: 160 },
  histLabelVal: { color: '#cbd5e1', fontSize: 10, fontWeight: '700' },
  bridgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, paddingHorizontal: 12, paddingTop: 8 },
  bridgeBtn: { flex: 1, minWidth: 80, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 10, paddingHorizontal: 8, borderRadius: 8, borderWidth: 1 },
  bridgeText: { fontSize: 10, fontWeight: '800' },
});


// 2026-02 — Wrap the playground in a per-screen ErrorBoundary so a runtime
// crash inside the runner/code editor only takes down this route, not the
// whole app. Also auto-traces mount latency via useRenderTrace.
export default withScreenGuard(PlaygroundScreen, 'PlaygroundRoute');
