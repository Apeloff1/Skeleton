/**
 * app/boot-log.tsx — full boot diagnostic log viewer.
 *
 * Surfaces everything recorded during boot so issues can be diagnosed
 * directly on-device (esp. on a deployed build where there is no console):
 *   • crash count + last clean boot
 *   • persisted boot trace (across launches) + in-memory trace (this launch)
 *   • breadcrumb trail (nav / api / boot events, incl. errors)
 *
 * Reachable from the Safe-Mode screen and the BootLauncher failure sheet,
 * and directly at /boot-log. Includes Refresh, Copy and Clear actions.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import * as Clipboard from 'expo-clipboard';
import {
  getLastTrace, getMemoryTrace, getCrashCount, getLastCleanBoot,
  resetBootState, getSessionArchive, TraceStep, ArchivedSession,
} from '../utils/bootTracer';
import { trail } from '../src/utils/breadcrumbs';

type Crumb = { ts: number; category: string; message: string; level?: string; data?: any };

const LEVEL_COLOR: Record<string, string> = {
  error: '#f87171', warn: '#fbbf24', info: '#93C5FD',
};

function fmt(ts: number): string {
  try {
    const d = new Date(ts);
    return `${d.toLocaleTimeString()}.${String(d.getMilliseconds()).padStart(3, '0')}`;
  } catch { return String(ts); }
}

export default function BootLogScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [persisted, setPersisted] = useState<TraceStep[]>([]);
  const [memory, setMemory] = useState<TraceStep[]>([]);
  const [crumbs, setCrumbs] = useState<Crumb[]>([]);
  const [crash, setCrash] = useState<number>(0);
  const [lastClean, setLastClean] = useState<number | null>(null);
  const [sessions, setSessions] = useState<ArchivedSession[]>([]);
  const [openSession, setOpenSession] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
  const [conn, setConn] = useState<{ name: string; url: string; ok: boolean; status: number; ms: number; err?: string }[]>([]);
  const [testing, setTesting] = useState(false);

  const testConnection = useCallback(async () => {
    setTesting(true);
    const endpoints = [
      { name: 'health', path: '/api/health' },
      { name: 'tunnel heartbeat', path: '/api/health/tunnel' },
      { name: 'forge catalog', path: '/api/galaxy-studio/forge/catalog' },
    ];
    const out: any[] = [];
    for (const e of endpoints) {
      const url = `${BACKEND}${e.path}`;
      const t0 = Date.now();
      try {
        const ctrl = new AbortController();
        const to = setTimeout(() => ctrl.abort(), 12000);
        const r = await fetch(url, { signal: ctrl.signal });
        clearTimeout(to);
        out.push({ name: e.name, url, ok: r.ok, status: r.status, ms: Date.now() - t0 });
      } catch (err: any) {
        out.push({ name: e.name, url, ok: false, status: 0, ms: Date.now() - t0, err: String(err?.message || err).slice(0, 140) });
      }
      setConn([...out]);
    }
    setTesting(false);
  }, [BACKEND]);

  const refresh = useCallback(async () => {
    setPersisted(await getLastTrace());
    setMemory(getMemoryTrace());
    setCrumbs(trail.snapshot() as Crumb[]);
    setCrash(await getCrashCount());
    setLastClean(await getLastCleanBoot());
    setSessions(await getSessionArchive());
    setCopied(false);
  }, []);

  useEffect(() => { refresh(); testConnection(); }, [refresh, testConnection]);

  const buildText = useCallback(() => {
    const lines: string[] = [];
    lines.push('=== BOOT LOG ===');
    lines.push(`platform: ${Platform.OS}`);
    lines.push(`backend: ${process.env.EXPO_PUBLIC_BACKEND_URL || '(unset)'}`);
    lines.push(`crash_count: ${crash}`);
    lines.push(`last_clean_boot: ${lastClean ? fmt(lastClean) : 'never'}`);
    lines.push('');
    lines.push('--- connectivity ---');
    conn.forEach((c) => lines.push(`${c.ok ? 'OK ' : 'FAIL'} ${c.name} (${c.status || '-'}, ${c.ms}ms) ${c.url}${c.err ? ' ERR: ' + c.err : ''}`));
    lines.push('');
    lines.push('--- persisted trace (across launches) ---');
    persisted.forEach((t) => lines.push(`${fmt(t.ts)}  ${t.step}`));
    lines.push('');
    lines.push('--- this-launch trace ---');
    memory.forEach((t) => lines.push(`${fmt(t.ts)}  ${t.step}`));
    lines.push('');
    lines.push('--- breadcrumbs ---');
    crumbs.forEach((c) => lines.push(`${fmt(c.ts)}  [${c.level || 'info'}] ${c.category}: ${c.message}${c.data ? ' ' + JSON.stringify(c.data) : ''}`));
    lines.push('');
    lines.push(`--- crash session archive (${sessions.length}) ---`);
    sessions.forEach((s, i) => {
      lines.push(`[session ${i + 1} @ ${fmt(s.at)} · ${s.steps.length} steps]`);
      s.steps.forEach((t) => lines.push(`  ${fmt(t.ts)}  ${t.step}`));
    });
    return lines.join('\n');
  }, [persisted, memory, crumbs, crash, lastClean, conn, sessions]);

  const copy = useCallback(async () => {
    try { await Clipboard.setStringAsync(buildText()); setCopied(true); } catch { /* ignore */ }
  }, [buildText]);

  const clear = useCallback(async () => {
    await resetBootState();
    trail.clear();
    await refresh();
  }, [refresh]);

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.hbtn} testID="bl-back">
          <Text style={styles.hbtnTxt}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Boot Log</Text>
        <TouchableOpacity onPress={refresh} style={styles.hbtn} testID="bl-refresh">
          <Text style={styles.hbtnTxt}>↻ Refresh</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.metaRow}>
        <View style={[styles.pill, crash >= 3 && { borderColor: '#f87171' }]}>
          <Text style={styles.pillTxt}>crashes: <Text style={{ color: crash >= 3 ? '#f87171' : '#93C5FD' }}>{crash}</Text></Text>
        </View>
        <View style={styles.pill}>
          <Text style={styles.pillTxt}>last clean: {lastClean ? fmt(lastClean) : 'never'}</Text>
        </View>
      </View>
      <Text style={styles.backend} numberOfLines={1}>backend: {process.env.EXPO_PUBLIC_BACKEND_URL || '(unset)'}</Text>

      <ScrollView style={styles.scroll} contentContainerStyle={{ paddingBottom: insets.bottom + 120 }}>
        <Text style={styles.section}>Connectivity {testing ? '· testing…' : `· ${conn.filter(c => c.ok).length}/${conn.length} ok`}</Text>
        {conn.length === 0 && <Text style={styles.empty}>— not tested —</Text>}
        {conn.map((c, i) => (
          <Text key={`conn${i}`} style={styles.line}>
            <Text style={{ color: c.ok ? '#34d399' : '#f87171' }}>{c.ok ? '● ' : '○ '}</Text>
            {c.name} → {c.ok ? `${c.status} · ${c.ms}ms` : `FAIL ${c.status || ''} ${c.err || 'unreachable'} · ${c.ms}ms`}
          </Text>
        ))}
        <TouchableOpacity onPress={testConnection} disabled={testing} style={styles.inlineTestBtn} testID="bl-conn-test">
          <Text style={styles.hbtnTxt}>{testing ? 'Testing…' : '↻ Re-run connectivity test'}</Text>
        </TouchableOpacity>

        <Text style={styles.section}>Persisted trace · {persisted.length}</Text>
        {persisted.length === 0 && <Text style={styles.empty}>— none —</Text>}
        {persisted.map((t, i) => (
          <Text key={`p${i}`} style={styles.line}><Text style={styles.ts}>{fmt(t.ts)}</Text>  {t.step}</Text>
        ))}

        <Text style={styles.section}>🗂 Crash session archive · {sessions.length}</Text>
        {sessions.length === 0 && <Text style={styles.empty}>— no prior sessions —</Text>}
        {sessions.map((s, i) => (
          <View key={`sess${i}`}>
            <TouchableOpacity
              onPress={() => setOpenSession(openSession === i ? null : i)}
              style={styles.sessRow}
              testID={`bl-session-${i}`}>
              <Text style={styles.sessTitle}>
                {openSession === i ? '▾' : '▸'} session {i + 1} · {fmt(s.at)}
              </Text>
              <Text style={styles.sessCount}>{s.steps.length} steps</Text>
            </TouchableOpacity>
            {openSession === i && s.steps.map((t, j) => (
              <Text key={`sess${i}-${j}`} style={[styles.line, { paddingLeft: 8 }]}>
                <Text style={styles.ts}>{fmt(t.ts)}</Text>  {t.step}
              </Text>
            ))}
          </View>
        ))}

        <Text style={styles.section}>This launch · {memory.length}</Text>
        {memory.length === 0 && <Text style={styles.empty}>— none —</Text>}
        {memory.map((t, i) => (
          <Text key={`m${i}`} style={styles.line}><Text style={styles.ts}>{fmt(t.ts)}</Text>  {t.step}</Text>
        ))}

        <Text style={styles.section}>Breadcrumbs · {crumbs.length}</Text>
        {crumbs.length === 0 && <Text style={styles.empty}>— none —</Text>}
        {crumbs.map((c, i) => (
          <Text key={`c${i}`} style={styles.line}>
            <Text style={styles.ts}>{fmt(c.ts)}</Text>{'  '}
            <Text style={{ color: LEVEL_COLOR[c.level || 'info'] || '#93C5FD' }}>[{c.category}]</Text>{' '}
            {c.message}{c.data ? ` ${JSON.stringify(c.data)}` : ''}
          </Text>
        ))}
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + 10 }]}>
        <TouchableOpacity onPress={copy} style={[styles.fbtn, styles.fprimary]} testID="bl-copy">
          <Text style={styles.fprimaryTxt}>{copied ? '✓ Copied' : 'Copy all'}</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={clear} style={styles.fbtn} testID="bl-clear">
          <Text style={styles.fbtnTxt}>Clear log</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0b0f1a', paddingHorizontal: 14 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
  title: { color: '#e6ebf2', fontSize: 17, fontWeight: '900' },
  hbtn: { paddingVertical: 6, paddingHorizontal: 10, borderRadius: 8, backgroundColor: '#1b2438', borderWidth: 1, borderColor: '#27324a' },
  hbtnTxt: { color: '#9cc4e8', fontSize: 12, fontWeight: '800' },
  metaRow: { flexDirection: 'row', gap: 8, marginBottom: 6 },
  pill: { borderWidth: 1, borderColor: '#27324a', borderRadius: 20, paddingHorizontal: 10, paddingVertical: 5, backgroundColor: '#141b2e' },
  pillTxt: { color: '#cbd5e1', fontSize: 11, fontWeight: '700' },
  backend: { color: '#6b7a99', fontSize: 10, marginBottom: 8 },
  scroll: { flex: 1, backgroundColor: '#070b14', borderRadius: 10, borderWidth: 1, borderColor: '#1b2438', paddingHorizontal: 10, paddingTop: 8 },
  section: { color: '#A78BFA', fontSize: 11, fontWeight: '900', marginTop: 12, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 },
  empty: { color: '#475569', fontSize: 11, fontStyle: 'italic' },
  line: { color: '#cbd5e1', fontSize: 11, fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' }), marginBottom: 3, lineHeight: 16 },
  ts: { color: '#5b6b88' },
  sessRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 8, paddingHorizontal: 10, marginTop: 6, borderRadius: 8, backgroundColor: '#101728', borderWidth: 1, borderColor: '#1b2438' },
  sessTitle: { color: '#9cc4e8', fontSize: 12, fontWeight: '800' },
  sessCount: { color: '#6b7a99', fontSize: 11, fontWeight: '700' },
  inlineTestBtn: { alignSelf: 'flex-start', marginTop: 8, paddingVertical: 7, paddingHorizontal: 12, borderRadius: 8, backgroundColor: '#1b2438', borderWidth: 1, borderColor: '#27324a' },
  footer: { flexDirection: 'row', gap: 10, paddingTop: 10 },
  fbtn: { flex: 1, alignItems: 'center', paddingVertical: 12, borderRadius: 10, backgroundColor: '#1b2438', borderWidth: 1, borderColor: '#27324a' },
  fbtnTxt: { color: '#cbd5e1', fontSize: 13, fontWeight: '800' },
  fprimary: { backgroundColor: '#A78BFA22', borderColor: '#A78BFA66' },
  fprimaryTxt: { color: '#A78BFA', fontSize: 13, fontWeight: '900' },
});
