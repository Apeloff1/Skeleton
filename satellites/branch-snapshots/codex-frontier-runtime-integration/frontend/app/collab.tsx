/**
 * /collab — Live Collaboration session UI.
 *
 * Lists active sessions • join an existing one • create a new one
 * • quick actions wired to /api/collaboration/* (pair-program / live-suggest /
 *   collab-debug / explain-live / refactor-suggest).
 */
import { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TextInput, ScrollView, TouchableOpacity, ActivityIndicator,
  RefreshControl, StyleSheet, StatusBar, SafeAreaView,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useRouteHistory } from '../utils/routeHistory';
import { shareResult, copyToClipboard } from '../utils/shareResult';
import { jeevesSpeak } from '../features/Academy/jeevesTts';
import { toast } from '../components/Toast';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const USER_ID = 'default_user';

type Session = {
  session_id?: string;
  id?: string;
  name?: string;
  language?: string;
  participants?: any[];
  created_at?: string;
};

const QUICK_ACTIONS = [
  { id: 'pair-program',     label: 'Pair-program',     icon: 'people' as const,         tint: '#a78bfa', body: { code: '', language: 'python', goal: 'review code structure' } },
  { id: 'live-suggest',     label: 'Live suggest',     icon: 'bulb' as const,           tint: '#fbbf24', body: { code: 'print("hello")', language: 'python' } },
  { id: 'collab-debug',     label: 'Debug together',   icon: 'bug' as const,            tint: '#f87171', body: { code: 'print(x)', language: 'python', error: 'NameError: x' } },
  { id: 'explain-live',     label: 'Explain live',     icon: 'school' as const,         tint: '#10B981', body: { code: 'def f(): pass', language: 'python' } },
  { id: 'refactor-suggest', label: 'Refactor suggest', icon: 'git-pull-request' as const, tint: '#3B82F6', body: { code: 'def f():\n  x=1\n  return x', language: 'python' } },
];

export default function CollabScreen() {
  const router = useRouter();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState('');
  const [newName, setNewName] = useState('');
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [actionResult, setActionResult] = useState<{ id: string; text: string } | null>(null);
  const history = useRouteHistory<{ actionId: string; actionLabel: string }>('collab');

  const fetchSessions = useCallback(async () => {
    setErr('');
    try {
      const r = await fetch(`${BACKEND}/api/collaboration/sessions`);
      const j = await r.json();
      setSessions((j?.sessions || j || []) as Session[]);
    } catch (e: any) {
      setErr(String(e?.message || e).slice(0, 200));
    } finally {
      setLoading(false); setRefreshing(false);
    }
  }, []);

  useEffect(() => { fetchSessions(); }, [fetchSessions]);

  const runQuick = useCallback(async (a: typeof QUICK_ACTIONS[number]) => {
    setActionBusy(a.id); setActionResult(null);
    try {
      const r = await fetch(`${BACKEND}/api/collaboration/${a.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...a.body, user_id: USER_ID }),
      });
      const j = await r.json();
      const t = typeof j === 'string' ? j : (j?.response || j?.suggestion || j?.explanation || JSON.stringify(j).slice(0, 600));
      const cleaned = String(t).slice(0, 1200);
      setActionResult({ id: a.id, text: cleaned });
      await history.push({
        label: a.label,
        preview: cleaned.split('\n')[0]?.slice(0, 60),
        payload: { actionId: a.id, actionLabel: a.label },
      });
      jeevesSpeak(`${a.label} complete.`, { context: 'celebration', prependCatchphrase: false });
    } catch (e: any) {
      setActionResult({ id: a.id, text: `⚠️ ${String(e?.message || e).slice(0, 200)}` });
    } finally {
      setActionBusy(null);
    }
  }, [history]);

  const createSession = () => {
    toast.info(`Real-time WebSocket sessions are not yet exposed via the public REST API.\n\nTry one of the AI collab quick-actions below for now — they run synchronously with full backend power.`);
  };

  return (
    <SafeAreaView style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor="#0A0A0A" />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="chevron-back" size={22} color="#10B981" />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={s.title}>🧑‍🤝‍🧑 Live Collaboration</Text>
            <Text style={s.subtitle}>{sessions.length} session{sessions.length === 1 ? '' : 's'} · AI pair-programming</Text>
          </View>
          <TouchableOpacity onPress={fetchSessions} style={s.iconBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="refresh" size={18} color="#10B981" />
          </TouchableOpacity>
        </View>

        <ScrollView
          contentContainerStyle={{ padding: 12, paddingBottom: 60 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchSessions(); }} tintColor="#10B981" />}
        >
          {err ? <View style={s.errBox}><Text style={s.errText}>{err}</Text></View> : null}

          {/* Sessions list */}
          <Text style={s.sectionLabel}>Active sessions</Text>
          {loading ? (
            <ActivityIndicator color="#10B981" style={{ marginVertical: 14 }} />
          ) : sessions.length === 0 ? (
            <View style={s.emptyBox}>
              <Ionicons name="people-circle-outline" size={28} color="#64748b" />
              <Text style={s.emptyText}>No live sessions right now.</Text>
              <Text style={s.emptySub}>Use the quick AI actions below to collaborate with Jeeves.</Text>
            </View>
          ) : (
            sessions.map((sess, i) => {
              const id = sess.session_id || sess.id || `session-${i}`;
              return (
                <View key={id} style={s.sessionCard}>
                  <View style={s.sessionDot} />
                  <View style={{ flex: 1 }}>
                    <Text style={s.sessionName}>{sess.name || id}</Text>
                    <Text style={s.sessionMeta}>
                      {sess.language || 'any lang'} · {(sess.participants || []).length} participant{(sess.participants || []).length === 1 ? '' : 's'}
                    </Text>
                  </View>
                  <TouchableOpacity style={s.joinBtn} onPress={() => toast.info('WebSocket join not yet wired in this UI.')}>
                    <Text style={s.joinText}>Join</Text>
                  </TouchableOpacity>
                </View>
              );
            })
          )}

          {/* Create */}
          <View style={{ marginTop: 14, gap: 8 }}>
            <TextInput
              value={newName}
              onChangeText={setNewName}
              placeholder="New session name…"
              placeholderTextColor="#64748b"
              style={s.input}
            />
            <TouchableOpacity onPress={createSession} style={s.createBtn} disabled={!newName.trim()}>
              <Ionicons name="add-circle" size={16} color="#0A0A0A" />
              <Text style={s.createText}>Create session</Text>
            </TouchableOpacity>
          </View>

          {/* Quick AI actions */}
          <Text style={[s.sectionLabel, { marginTop: 22 }]}>Jeeves quick collab actions</Text>
          <Text style={s.helper}>One-shot AI helpers — results stream below.</Text>
          {QUICK_ACTIONS.map(a => (
            <TouchableOpacity
              key={a.id}
              style={[s.actionBtn, { borderColor: a.tint + '55' }]}
              onPress={() => runQuick(a)}
              disabled={!!actionBusy}
              activeOpacity={0.8}
            >
              <View style={[s.actionIcon, { backgroundColor: a.tint + '22', borderColor: a.tint }]}>
                <Ionicons name={a.icon} size={16} color={a.tint} />
              </View>
              <Text style={s.actionLabel}>{a.label}</Text>
              {actionBusy === a.id ? <ActivityIndicator size="small" color={a.tint} /> : <Ionicons name="play-circle" size={18} color={a.tint} />}
            </TouchableOpacity>
          ))}

          {actionResult && (
            <View style={s.resultBox}>
              <View style={s.resultHead}>
                <Ionicons name="sparkles" size={14} color="#10B981" />
                <Text style={s.resultHeadText}>Result · {actionResult.id}</Text>
              </View>
              <Text style={s.resultText}>{actionResult.text}</Text>
              <View style={s.bridgeRow}>
                <TouchableOpacity
                  style={[s.bridgeBtn, { backgroundColor: '#F59E0B22', borderColor: '#F59E0B' }]}
                  onPress={() => router.push({ pathname: '/playground', params: { lang: 'python', code: actionResult.text } } as any)}
                >
                  <Ionicons name="flask" size={13} color="#F59E0B" />
                  <Text style={[s.bridgeText, { color: '#F59E0B' }]}>Playground</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.bridgeBtn, { backgroundColor: '#EF444422', borderColor: '#EF4444' }]}
                  onPress={() => router.push({ pathname: '/debugger', params: { lang: 'python', code: actionResult.text } } as any)}
                >
                  <Ionicons name="bug" size={13} color="#EF4444" />
                  <Text style={[s.bridgeText, { color: '#EF4444' }]}>Debug</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.bridgeBtn, { backgroundColor: '#10B98122', borderColor: '#10B981' }]}
                  onPress={() => copyToClipboard(actionResult.text, 'Result copied')}
                >
                  <Ionicons name="copy" size={13} color="#10B981" />
                  <Text style={[s.bridgeText, { color: '#10B981' }]}>Copy</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.bridgeBtn, { backgroundColor: '#A78BFA22', borderColor: '#A78BFA' }]}
                  onPress={() => shareResult(actionResult.text, `Collab · ${actionResult.id}`)}
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
  header: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingHorizontal: 14, paddingVertical: 10,
    borderBottomColor: '#1F1F1F', borderBottomWidth: 1,
  },
  backBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  iconBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  title: { color: '#f1f5f9', fontSize: 16, fontWeight: '900' },
  subtitle: { color: '#94a3b8', fontSize: 11, marginTop: 2 },
  sectionLabel: { color: '#94a3b8', fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 },
  helper: { color: '#64748b', fontSize: 11, marginBottom: 8, fontStyle: 'italic' },
  errBox: { backgroundColor: '#f8717122', borderColor: '#f87171', borderWidth: 1, padding: 10, borderRadius: 8, marginBottom: 10 },
  errText: { color: '#fecaca', fontSize: 11 },
  emptyBox: { alignItems: 'center', padding: 22, backgroundColor: '#141414', borderRadius: 12, borderWidth: 1, borderColor: '#1F1F1F', gap: 6 },
  emptyText: { color: '#cbd5e1', fontSize: 12, fontWeight: '600' },
  emptySub: { color: '#64748b', fontSize: 11, textAlign: 'center' },
  sessionCard: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: '#141414', borderRadius: 12, padding: 12,
    borderWidth: 1, borderColor: '#1F1F1F', marginBottom: 6,
  },
  sessionDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#10B981' },
  sessionName: { color: '#f1f5f9', fontSize: 13, fontWeight: '700' },
  sessionMeta: { color: '#94a3b8', fontSize: 10, marginTop: 2 },
  joinBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 10, backgroundColor: '#10B98122', borderColor: '#10B981', borderWidth: 1 },
  joinText: { color: '#10B981', fontSize: 11, fontWeight: '700' },
  input: {
    backgroundColor: '#141414', borderRadius: 10, borderWidth: 1, borderColor: '#1F1F1F',
    paddingHorizontal: 12, paddingVertical: 10, color: '#f1f5f9', fontSize: 12,
  },
  createBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    backgroundColor: '#10B981', paddingVertical: 11, borderRadius: 10,
  },
  createText: { color: '#0A0A0A', fontSize: 13, fontWeight: '900' },
  actionBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: '#141414', borderRadius: 12, padding: 12,
    borderWidth: 1, marginBottom: 6,
  },
  actionIcon: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  actionLabel: { color: '#f1f5f9', fontSize: 13, fontWeight: '700', flex: 1 },
  resultBox: {
    marginTop: 12, padding: 12, backgroundColor: '#141414',
    borderRadius: 12, borderWidth: 1, borderColor: '#10B98155',
  },
  resultHead: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  resultHeadText: { color: '#10B981', fontSize: 10, fontWeight: '900', textTransform: 'uppercase', letterSpacing: 1 },
  resultText: { color: '#cbd5e1', fontSize: 12, lineHeight: 17, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  bridgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  bridgeBtn: { flex: 1, minWidth: 80, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 10, paddingHorizontal: 8, borderRadius: 8, borderWidth: 1 },
  bridgeText: { fontSize: 10, fontWeight: '800' },
});
