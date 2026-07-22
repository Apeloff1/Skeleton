/**
 * /tools-arena — Power-user surface for the 8 complex backend tools.
 *
 * Single native route that exposes every tool registered in
 * /api/tools/describe so users (and developers/debuggers) can drive them
 * directly instead of waiting for an agent loop. Each tool is its own
 * tab with a tailored input form and live results panel.
 *
 * Tools wired:
 *   • web_search     — DuckDuckGo (live, no key)
 *   • vault_query    — query 448+ knowledge collections
 *   • jeeves_consult — pull a persona-flavoured guidance entry
 *   • run_code       — Python REPL with persistent session
 *   • compile_code   — compile C / C++ / Go / Rust
 *   • llm_chat       — direct gpt-4o pass-through
 *   • mongo_query    — read any Mongo collection
 *   • package_build  — ZIP/APK an existing Galaxy build
 */
import React, { useCallback, useMemo, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator,
  StyleSheet, SafeAreaView, KeyboardAvoidingView, Platform, Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import theme from '../theme/tokens';
import { useModalLogger } from '../utils/modalLogger';
import RetryBanner from '../components/ui/RetryBanner';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const { breathing, palette, radii } = theme;

type ToolId =
  | 'web_search'
  | 'vault_query'
  | 'jeeves_consult'
  | 'run_code'
  | 'compile_code'
  | 'llm_chat'
  | 'mongo_query'
  | 'package_build';

type ToolMeta = {
  id: ToolId;
  title: string;
  icon: keyof typeof Ionicons.glyphMap;
  accent: string;
  blurb: string;
};

const TOOLS: ToolMeta[] = [
  { id: 'web_search',     title: 'Web Search',    icon: 'globe-outline',         accent: '#3B82F6', blurb: 'Live DuckDuckGo — text, news, images' },
  { id: 'vault_query',    title: 'Vault Query',   icon: 'library-outline',       accent: '#a78bfa', blurb: '448+ knowledge collections' },
  { id: 'jeeves_consult', title: 'Ask Jeeves',    icon: 'sparkles-outline',      accent: '#f59e0b', blurb: 'Persona catchphrase + guidance' },
  { id: 'run_code',       title: 'Python REPL',   icon: 'terminal-outline',      accent: '#10b981', blurb: 'Sandboxed interpreter' },
  { id: 'compile_code',   title: 'Compile',       icon: 'construct-outline',     accent: '#f97316', blurb: 'C / C++ / Go / Rust' },
  { id: 'llm_chat',       title: 'LLM Chat',      icon: 'chatbubbles-outline',   accent: '#8B5CF6', blurb: 'gpt-4o via Emergent key' },
  { id: 'mongo_query',    title: 'Mongo Query',   icon: 'server-outline',        accent: '#3B82F6', blurb: 'Read knowledge collections' },
  { id: 'package_build',  title: 'Package Build', icon: 'archive-outline',       accent: '#facc15', blurb: 'ZIP + APK from a build_id' },
];

const JEEVES_CONTEXTS = [
  'greeting', 'celebration', 'debug', 'lesson_intro', 'gentle_correction',
  'encouragement', 'alert', 'sign_off', 'code_walkthrough', 'story_time',
  'thinking', 'warning_clarification', 'transition', 'definition',
] as const;

const COMPILE_LANGS = ['c', 'cpp', 'go', 'rust'] as const;
const SEARCH_KINDS = ['text', 'news', 'images'] as const;

// ─────────────────────────────────────────────────────────────────────
//  HELPERS
// ─────────────────────────────────────────────────────────────────────
async function invokeTool(tool: ToolId, params: Record<string, any>) {
  const res = await fetch(`${BACKEND}/api/tools/invoke`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool, params }),
  });
  return res.json();
}

// ─────────────────────────────────────────────────────────────────────
//  COMPONENT
// ─────────────────────────────────────────────────────────────────────
export default function ToolsArena() {
  const router = useRouter();
  const log = useModalLogger('ToolsArena');
  const [active, setActive] = useState<ToolId>('web_search');
  const [busy, setBusy]     = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError]   = useState<string>('');

  // Per-tool form state
  const [webQuery, setWebQuery]       = useState('expo router 2026 best practices');
  const [webKind, setWebKind]         = useState<typeof SEARCH_KINDS[number]>('text');
  const [vaultTopic, setVaultTopic]   = useState('pathfinding');
  const [vaultColl, setVaultColl]     = useState('');
  const [jeevesCtx, setJeevesCtx]     = useState<typeof JEEVES_CONTEXTS[number]>('lesson_intro');
  const [jeevesTopic, setJeevesTopic] = useState('compiler');
  const [pyCode, setPyCode]           = useState('import math\nprint("hello", math.pi)');
  const [pySession]                   = useState(`arena_${Math.random().toString(36).slice(2, 8)}`);
  const [compLang, setCompLang]       = useState<typeof COMPILE_LANGS[number]>('c');
  const [compCode, setCompCode]       = useState('#include <stdio.h>\nint main(){printf("hi\\n");return 0;}');
  const [llmPrompt, setLlmPrompt]     = useState('Explain quantum entanglement in 2 sentences.');
  const [mongoColl, setMongoColl]     = useState('jeeves_persona');
  const [mongoFilter, setMongoFilter] = useState('{}');
  const [pkgBuildId, setPkgBuildId]   = useState('demo_apk_001');

  const resetResult = () => { setResult(null); setError(''); };

  const run = useCallback(async () => {
    setBusy(true); resetResult();
    const _t0 = Date.now();
    try {
      let params: Record<string, any> = {};
      switch (active) {
        case 'web_search':
          params = { query: webQuery.trim(), kind: webKind, max_results: 8 };
          break;
        case 'vault_query':
          params = vaultColl.trim()
            ? { collection: vaultColl.trim(), limit: 6 }
            : { topic: vaultTopic.trim(), limit: 6 };
          break;
        case 'jeeves_consult':
          params = { context: jeevesCtx, topic: jeevesTopic.trim() };
          break;
        case 'run_code':
          // Python REPL goes through /api/interpreter/run (persistent state)
          const r = await fetch(`${BACKEND}/api/interpreter/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: pyCode, language: 'python', session_id: pySession }),
          });
          setResult(await r.json()); setBusy(false); return;
        case 'compile_code':
          params = { language: compLang, code: compCode };
          break;
        case 'llm_chat':
          params = { prompt: llmPrompt, model: 'gpt-4o' };
          break;
        case 'mongo_query':
          try {
            const f = mongoFilter.trim() ? JSON.parse(mongoFilter) : {};
            params = { collection: mongoColl.trim(), filter: f, limit: 5 };
          } catch (e: any) {
            setError(`Invalid filter JSON: ${e.message}`); setBusy(false); return;
          }
          break;
        case 'package_build':
          params = { build_id: pkgBuildId.trim(), kinds: ['zip', 'apk'] };
          break;
      }
      const r = await invokeTool(active, params);
      setResult(r);
      log.metric(`run_${active}`, Date.now() - _t0, 'ms');
      if (r?.ok === false) log.warn(`tool_${active}_failed`, { error: r.error });
    } catch (e: any) {
      setError(`Network error: ${e?.message || e}`);
      log.error(e, { tool: active });
    } finally {
      setBusy(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    active, webQuery, webKind, vaultTopic, vaultColl, jeevesCtx, jeevesTopic,
    pyCode, pySession, compLang, compCode, llmPrompt, mongoColl, mongoFilter, pkgBuildId,
  ]);

  // ───────── tool-specific form render ─────────
  const renderForm = () => {
    switch (active) {
      case 'web_search':
        return (
          <>
            <Field label="Query">
              <TextInput style={styles.input} value={webQuery} onChangeText={setWebQuery} placeholder="Search the live web…" placeholderTextColor={palette.ink[400]} />
            </Field>
            <SegRow value={webKind} options={[...SEARCH_KINDS]} onChange={v => setWebKind(v as any)} />
          </>
        );
      case 'vault_query':
        return (
          <>
            <Field label="Topic (fuzzy)">
              <TextInput style={styles.input} value={vaultTopic} onChangeText={setVaultTopic} placeholder="e.g. pathfinding" placeholderTextColor={palette.ink[400]} />
            </Field>
            <Field label="OR specific collection">
              <TextInput style={styles.input} value={vaultColl} onChangeText={setVaultColl} placeholder="(blank to search by topic)" placeholderTextColor={palette.ink[400]} autoCapitalize="none" />
            </Field>
          </>
        );
      case 'jeeves_consult':
        return (
          <>
            <Field label="Context">
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                {JEEVES_CONTEXTS.map(c => (
                  <Pill key={c} label={c} active={c === jeevesCtx} onPress={() => setJeevesCtx(c)} />
                ))}
              </ScrollView>
            </Field>
            <Field label="Topic">
              <TextInput style={styles.input} value={jeevesTopic} onChangeText={setJeevesTopic} placeholder="e.g. pathfinding" placeholderTextColor={palette.ink[400]} />
            </Field>
          </>
        );
      case 'run_code':
        return (
          <>
            <Text style={styles.help}>Persistent Python REPL · session: {pySession}</Text>
            <Field label="Python code">
              <TextInput
                style={[styles.input, styles.codeArea]} value={pyCode} onChangeText={setPyCode}
                multiline placeholderTextColor={palette.ink[400]} autoCapitalize="none" autoCorrect={false}
              />
            </Field>
          </>
        );
      case 'compile_code':
        return (
          <>
            <SegRow value={compLang} options={[...COMPILE_LANGS]} onChange={v => setCompLang(v as any)} />
            <Field label="Source code">
              <TextInput
                style={[styles.input, styles.codeArea]} value={compCode} onChangeText={setCompCode}
                multiline placeholderTextColor={palette.ink[400]} autoCapitalize="none" autoCorrect={false}
              />
            </Field>
          </>
        );
      case 'llm_chat':
        return (
          <Field label="Prompt">
            <TextInput
              style={[styles.input, styles.codeArea]} value={llmPrompt} onChangeText={setLlmPrompt}
              multiline placeholderTextColor={palette.ink[400]}
            />
          </Field>
        );
      case 'mongo_query':
        return (
          <>
            <Field label="Collection">
              <TextInput style={styles.input} value={mongoColl} onChangeText={setMongoColl} placeholder="e.g. jeeves_persona" placeholderTextColor={palette.ink[400]} autoCapitalize="none" />
            </Field>
            <Field label="Filter (JSON)">
              <TextInput style={styles.input} value={mongoFilter} onChangeText={setMongoFilter} placeholder='{}' placeholderTextColor={palette.ink[400]} autoCapitalize="none" autoCorrect={false} />
            </Field>
          </>
        );
      case 'package_build':
        return (
          <Field label="build_id">
            <TextInput style={styles.input} value={pkgBuildId} onChangeText={setPkgBuildId} placeholder="from /api/galaxy-builds" placeholderTextColor={palette.ink[400]} autoCapitalize="none" />
          </Field>
        );
    }
  };

  const activeMeta = useMemo(() => TOOLS.find(t => t.id === active)!, [active]);

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} hitSlop={theme.hitSlop.md} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={24} color={palette.ink[100]} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={styles.h1}>Tools Arena</Text>
            <Text style={styles.sub}>8 complex tools · same surface that agents use</Text>
          </View>
        </View>

        {/* Tool picker (horizontal scroll) */}
        <View style={styles.pickerWrap}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.picker}>
            {TOOLS.map(t => {
              const isActive = t.id === active;
              return (
                <TouchableOpacity
                  key={t.id}
                  onPress={() => { setActive(t.id); resetResult(); }}
                  style={[styles.toolChip, isActive && { borderColor: t.accent, backgroundColor: `${t.accent}22` }]}
                >
                  <Ionicons name={t.icon} size={16} color={isActive ? t.accent : palette.ink[300]} />
                  <Text style={[styles.toolChipText, isActive && { color: t.accent }]}>{t.title}</Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>

        {/* Body */}
        <ScrollView
          contentContainerStyle={styles.body}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={[styles.accentBar, { backgroundColor: activeMeta.accent }]} />
          <Text style={styles.blurb}>{activeMeta.blurb}</Text>

          <View style={styles.card}>
            {renderForm()}
            <TouchableOpacity
              style={[styles.runBtn, { backgroundColor: activeMeta.accent }]}
              onPress={run}
              disabled={busy}
              accessibilityLabel="Run tool"
            >
              {busy
                ? <ActivityIndicator color={palette.ink[1000]} />
                : <Text style={styles.runBtnText}>Run {activeMeta.title}</Text>}
            </TouchableOpacity>
          </View>

          {/* Result */}
          {error ? (
            <RetryBanner
              error={error}
              onRetry={run}
              retryLabel="Retry"
            />
          ) : null}

          {result ? <ResultView tool={active} data={result} /> : null}

          <View style={{ height: 40 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// ─────────────────────────────────────────────────────────────────────
//  Result renderer — per-tool friendly formatting
// ─────────────────────────────────────────────────────────────────────
function ResultView({ tool, data }: { tool: ToolId; data: any }) {
  const ok = data?.ok !== false;

  if (tool === 'web_search' && Array.isArray(data?.results)) {
    return (
      <View style={styles.card}>
        <Text style={styles.cardTitle}>{data.results.length} result{data.results.length === 1 ? '' : 's'}</Text>
        {data.results.map((r: any, i: number) => (
          <TouchableOpacity key={i} style={styles.searchRow} onPress={() => r.url && Linking.openURL(r.url)}>
            <Text style={styles.searchTitle}>{r.title || '(untitled)'}</Text>
            {!!r.snippet && <Text style={styles.searchSnip}>{r.snippet}</Text>}
            {!!r.url && <Text style={styles.searchUrl}>{r.url}</Text>}
          </TouchableOpacity>
        ))}
      </View>
    );
  }

  if (tool === 'vault_query') {
    if (data?.rows) {
      return (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>{data.collection} · {data.count} rows</Text>
          {data.rows.slice(0, 6).map((row: any, i: number) => (
            <Text key={i} style={styles.codeBlock} numberOfLines={6}>{JSON.stringify(row, null, 2).slice(0, 600)}</Text>
          ))}
        </View>
      );
    }
    if (data?.matches) {
      const entries = Object.entries(data.matches);
      return (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>{entries.length} collections matched topic &quot;{data.topic}&quot;</Text>
          {entries.slice(0, 5).map(([coll, rows]: any, i: number) => (
            <View key={i} style={{ marginVertical: 8 }}>
              <Text style={styles.searchTitle}>{coll} · {rows.length} hits</Text>
              <Text style={styles.codeBlock} numberOfLines={4}>{JSON.stringify(rows[0], null, 2).slice(0, 400)}</Text>
            </View>
          ))}
        </View>
      );
    }
  }

  if (tool === 'jeeves_consult') {
    return (
      <View style={styles.card}>
        {data.catchphrase ? (
          <Text style={styles.bigQuote}>&quot;{data.catchphrase}&quot;</Text>
        ) : <Text style={styles.help}>(no catchphrase for this context)</Text>}
        {data.knowledge ? (
          <Text style={styles.bodyText}>{data.knowledge}</Text>
        ) : null}
        {data.citation ? <Text style={styles.help}>— {data.citation}</Text> : null}
        {data.mannerism && Object.keys(data.mannerism).length ? (
          <Text style={styles.help}>Voice: {JSON.stringify(data.mannerism)}</Text>
        ) : null}
      </View>
    );
  }

  if (tool === 'run_code' || tool === 'compile_code') {
    return (
      <View style={styles.card}>
        <Text style={[styles.cardTitle, { color: ok ? '#10B981' : '#A78BFA' }]}>
          {ok ? '✓ Success' : '✗ Failed'} {data.exit_code !== undefined ? `(exit ${data.exit_code})` : ''}
        </Text>
        {data.stdout ? (<><Text style={styles.help}>stdout</Text><Text style={styles.codeBlock}>{data.stdout}</Text></>) : null}
        {data.stderr ? (<><Text style={styles.help}>stderr</Text><Text style={[styles.codeBlock, { color: '#A78BFA' }]}>{data.stderr}</Text></>) : null}
        {data.error ? <Text style={[styles.codeBlock, { color: '#A78BFA' }]}>{data.error}</Text> : null}
      </View>
    );
  }

  if (tool === 'llm_chat') {
    return (
      <View style={styles.card}>
        <Text style={styles.help}>model: {data.model || 'gpt-4o'}</Text>
        <Text style={styles.bodyText}>{data.response || data.error || '(empty)'}</Text>
      </View>
    );
  }

  if (tool === 'mongo_query') {
    return (
      <View style={styles.card}>
        <Text style={styles.cardTitle}>{data.collection} · {data.count ?? 0} rows</Text>
        {(data.rows || []).slice(0, 5).map((row: any, i: number) => (
          <Text key={i} style={styles.codeBlock} numberOfLines={8}>{JSON.stringify(row, null, 2).slice(0, 800)}</Text>
        ))}
      </View>
    );
  }

  if (tool === 'package_build') {
    return (
      <View style={styles.card}>
        <Text style={[styles.cardTitle, { color: ok ? '#10B981' : '#A78BFA' }]}>
          {ok ? '✓ Packaged' : '✗ Failed'}
        </Text>
        {(data.artifacts || []).map((a: any, i: number) => (
          <View key={i} style={{ marginVertical: 6 }}>
            <Text style={styles.searchTitle}>{a.kind?.toUpperCase()} · {a.size_bytes} bytes</Text>
            <Text style={styles.help}>{a.is_real_apk === false ? '⚠ placeholder (no toolchain)' : 'signed'} · sha256 {String(a.sha256 || '').slice(0, 16)}…</Text>
            <TouchableOpacity onPress={() => Linking.openURL(`${BACKEND}${a.download_url}`)}>
              <Text style={[styles.searchUrl, { marginTop: 4 }]}>Download →</Text>
            </TouchableOpacity>
          </View>
        ))}
        {data.error ? <Text style={[styles.codeBlock, { color: '#A78BFA' }]}>{data.error}</Text> : null}
      </View>
    );
  }

  // generic fallback
  return (
    <View style={styles.card}>
      <Text style={styles.codeBlock}>{JSON.stringify(data, null, 2)}</Text>
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────
//  Small UI helpers
// ─────────────────────────────────────────────────────────────────────
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={{ marginBottom: breathing.rowGap }}>
      <Text style={styles.fieldLabel}>{label}</Text>
      {children}
    </View>
  );
}

function Pill({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <TouchableOpacity onPress={onPress} style={[styles.pill, active && styles.pillActive]}>
      <Text style={[styles.pillText, active && styles.pillTextActive]}>{label}</Text>
    </TouchableOpacity>
  );
}

function SegRow({ value, options, onChange }: { value: string; options: string[]; onChange: (v: string) => void }) {
  return (
    <View style={styles.segRow}>
      {options.map(o => (
        <TouchableOpacity
          key={o}
          onPress={() => onChange(o)}
          style={[styles.segCell, value === o && styles.segCellActive]}
        >
          <Text style={[styles.segText, value === o && styles.segTextActive]}>{o}</Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────
//  Styles
// ─────────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: palette.ink[1000] },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: breathing.gutter, paddingVertical: 12,
    gap: 12,
    borderBottomWidth: 1, borderBottomColor: palette.ink[800],
  },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  h1: { fontSize: 22, fontWeight: '700', color: palette.ink[50] },
  sub: { fontSize: 12, color: palette.ink[400], marginTop: 2 },

  picker: { paddingHorizontal: breathing.gutter, paddingVertical: 10, alignItems: 'center' },
  pickerWrap: { height: 58, borderBottomWidth: 1, borderBottomColor: palette.ink[800] },
  toolChip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 12, paddingVertical: 0,
    borderRadius: radii.pill, borderWidth: 1.5,
    borderColor: palette.ink[700],
    marginRight: 8, height: 38,
  },
  toolChipText: { fontSize: 13, fontWeight: '600', color: palette.ink[300] },

  body: { paddingHorizontal: breathing.gutter, paddingTop: 8 },
  accentBar: { height: 3, borderRadius: 2, marginBottom: 10 },
  blurb: { fontSize: 14, color: palette.ink[300], marginBottom: breathing.sectionGap },

  card: {
    backgroundColor: palette.ink[900], borderRadius: radii.lg,
    padding: breathing.cardPadding, borderWidth: 1, borderColor: palette.ink[800],
    marginBottom: breathing.cardGap,
  },
  cardTitle: { fontSize: 15, fontWeight: '700', color: palette.ink[50], marginBottom: 6 },
  fieldLabel: { fontSize: 12, fontWeight: '600', color: palette.ink[300], marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.4 },
  input: {
    backgroundColor: palette.ink[800], color: palette.ink[50],
    borderRadius: radii.md, paddingHorizontal: 12, paddingVertical: 10,
    fontSize: 14, borderWidth: 1, borderColor: palette.ink[700], minHeight: 44,
  },
  codeArea: { minHeight: 110, textAlignVertical: 'top', fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }) },
  runBtn: {
    marginTop: 4, paddingVertical: 14, borderRadius: radii.md, alignItems: 'center',
    minHeight: breathing.minTouch,
  },
  runBtnText: { color: palette.ink[1000], fontWeight: '800', fontSize: 15 },

  errorCard: { flexDirection: 'row', alignItems: 'center', gap: 10, borderColor: '#7f1d1d', backgroundColor: '#1f0a0a' },
  errorText: { color: '#fda4af', fontSize: 13, flex: 1 },

  searchRow: { paddingVertical: 8, borderTopWidth: 1, borderTopColor: palette.ink[800] },
  searchTitle: { fontSize: 14, fontWeight: '600', color: palette.ink[50] },
  searchSnip: { fontSize: 13, color: palette.ink[300], marginTop: 3, lineHeight: 18 },
  searchUrl: { fontSize: 11, color: '#3B82F6', marginTop: 3 },

  codeBlock: {
    backgroundColor: palette.ink[1000], color: palette.ink[100],
    fontSize: 12, padding: 10, borderRadius: radii.sm, marginTop: 6,
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }),
  },
  bigQuote: { fontSize: 18, fontStyle: 'italic', color: palette.ink[50], lineHeight: 26, marginBottom: 8 },
  bodyText: { fontSize: 14, color: palette.ink[100], lineHeight: 20 },
  help: { fontSize: 11, color: palette.ink[400], marginVertical: 4 },

  pill: {
    paddingHorizontal: 12, paddingVertical: 8, borderRadius: radii.pill,
    backgroundColor: palette.ink[800], marginRight: 8, minHeight: 36,
    justifyContent: 'center',
  },
  pillActive: { backgroundColor: '#f59e0b' },
  pillText: { fontSize: 12, fontWeight: '600', color: palette.ink[200] },
  pillTextActive: { color: palette.ink[1000] },

  segRow: { flexDirection: 'row', gap: 6, marginBottom: breathing.rowGap },
  segCell: {
    flex: 1, paddingVertical: 10, borderRadius: radii.md,
    backgroundColor: palette.ink[800], alignItems: 'center', minHeight: 38,
  },
  segCellActive: { backgroundColor: palette.brand[600] },
  segText: { color: palette.ink[300], fontSize: 13, fontWeight: '600' },
  segTextActive: { color: '#fff' },
});
