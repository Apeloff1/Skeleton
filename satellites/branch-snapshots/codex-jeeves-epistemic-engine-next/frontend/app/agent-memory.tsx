/**
 * /agent-memory — I.2 Agent Long-Term Memory.
 *
 * Give an autonomous agent a persistent memory: REMEMBER episodes, RECALL the
 * most relevant ones (keyword × recency × importance), and REFLECT — distil
 * recent episodes into a durable lesson via the Model Router. Pick an agent
 * from the roster or type a new id; inspect its memory profile.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, SafeAreaView, TextInput, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';

type Memory = { memory_id: string; content: string; kind: string; importance: number; tags: string[]; relevance?: number; created_at: string; model?: string };
type AgentRow = { agent_id: string; memories: number; reflections: number; last_at: string };
type Profile = { agent_id: string; memories: number; by_kind: Record<string, number>; top_tags: { tag: string; count: number }[]; reflections: Memory[] };

const KIND_EMOJI: Record<string, string> = { episode: '📓', observation: '👁️', outcome: '🎯', reflection: '💡' };

export default function AgentMemory() {
  const router = useRouter();
  const haptics = useHaptics();
  const [agent, setAgent] = React.useState('atlas');
  const [agentInput, setAgentInput] = React.useState('');
  const [agents, setAgents] = React.useState<AgentRow[]>([]);
  const [profile, setProfile] = React.useState<Profile | null>(null);
  const [recall, setRecall] = React.useState<Memory[]>([]);
  const [query, setQuery] = React.useState('');
  const [newMem, setNewMem] = React.useState('');
  const [reflection, setReflection] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [reflecting, setReflecting] = React.useState(false);
  const [toast, setToast] = React.useState<string | null>(null);

  const flash = (m: string) => { setToast(m); setTimeout(() => setToast(null), 2400); };

  const loadAgents = React.useCallback(async () => {
    const r = await api.get<{ agents: AgentRow[] }>('/api/agent-memory/agents?limit=20', { timeoutMs: 12000 });
    if (r.ok && r.data) setAgents(r.data.agents || []);
  }, []);

  const loadProfile = React.useCallback(async (a: string) => {
    setLoading(true);
    const [p, rc] = await Promise.all([
      api.get<Profile>(`/api/agent-memory/${encodeURIComponent(a)}/profile`, { timeoutMs: 12000 }),
      api.get<{ memories: Memory[] }>(`/api/agent-memory/recall?agent_id=${encodeURIComponent(a)}&limit=8`, { timeoutMs: 12000 }),
    ]);
    if (p.ok && p.data) setProfile(p.data);
    if (rc.ok && rc.data) setRecall(rc.data.memories || []);
    setLoading(false);
  }, []);

  React.useEffect(() => { loadAgents(); }, [loadAgents]);
  React.useEffect(() => { loadProfile(agent); setReflection(null); }, [agent, loadProfile]);

  const doRecall = React.useCallback(async () => {
    haptics.selection();
    const r = await api.get<{ memories: Memory[] }>(
      `/api/agent-memory/recall?agent_id=${encodeURIComponent(agent)}&q=${encodeURIComponent(query)}&limit=8`,
      { timeoutMs: 12000 });
    if (r.ok && r.data) setRecall(r.data.memories || []);
  }, [agent, query, haptics]);

  const doRemember = React.useCallback(async () => {
    const c = newMem.trim();
    if (c.length < 3) { flash('Write a bit more to remember'); return; }
    haptics.selection();
    const r = await api.post<any>('/api/agent-memory/remember',
      { agent_id: agent, content: c, kind: 'episode', importance: 0.6 }, { timeoutMs: 12000 });
    if (r.ok && r.data?.memory_id) {
      setNewMem(''); flash('🧠 Remembered');
      loadProfile(agent); loadAgents();
    } else flash(r.data?.error || 'Failed to remember');
  }, [agent, newMem, haptics, loadProfile, loadAgents]);

  const doReflect = React.useCallback(async () => {
    haptics.notify('success'); setReflecting(true); setReflection(null);
    const r = await api.post<any>('/api/agent-memory/reflect', { agent_id: agent, window: 12 }, { timeoutMs: 90000 });
    setReflecting(false);
    if (r.ok && r.data?.reflection?.content) {
      setReflection(r.data.reflection.content);
      loadProfile(agent);
    } else flash(r.data?.error || 'Reflection unavailable');
  }, [agent, haptics, loadProfile]);

  const switchAgent = (a: string) => { haptics.selection(); setAgent(a); };
  const createAgent = () => {
    const a = agentInput.trim().toLowerCase().replace(/\s+/g, '_');
    if (a) { setAgentInput(''); setAgent(a); }
  };

  return (
    <SafeAreaView style={styles.safe} testID="agent-memory-screen">
      <View style={styles.header}>
        <TouchableOpacity testID="am-back" onPress={() => router.back()} style={styles.backBtn}><Text style={styles.backTxt}>‹ Back</Text></TouchableOpacity>
        <Text style={styles.title}>🧠 Agent Memory</Text>
      </View>

      {toast ? <View testID="am-toast" style={styles.toast}><Text style={styles.toastTxt}>{toast}</Text></View> : null}

      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={() => { loadProfile(agent); loadAgents(); }} tintColor="#A78BFA" />}
      >
        {/* agent roster */}
        <Text style={styles.sectionTitle}>Agent</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 10 }}>
          {agents.map((a) => (
            <TouchableOpacity key={a.agent_id} testID={`am-agent-${a.agent_id}`}
              style={[styles.agentChip, a.agent_id === agent && styles.agentChipOn]} onPress={() => switchAgent(a.agent_id)}>
              <Text style={[styles.agentName, a.agent_id === agent && styles.agentNameOn]}>{a.agent_id}</Text>
              <Text style={styles.agentMeta}>{a.memories}🧠 · {a.reflections}💡</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        <View style={styles.row}>
          <TextInput testID="am-agent-input" style={styles.input} value={agentInput} onChangeText={setAgentInput}
            placeholder="new agent id…" placeholderTextColor="#52525b" onSubmitEditing={createAgent} returnKeyType="go" />
          <TouchableOpacity testID="am-agent-create" style={styles.smallBtn} onPress={createAgent}><Text style={styles.smallBtnTxt}>+ Agent</Text></TouchableOpacity>
        </View>

        {/* profile stats */}
        {profile ? (
          <View testID="am-profile" style={styles.statsRow}>
            <View style={styles.stat}><Text style={styles.statNum}>{profile.memories}</Text><Text style={styles.statLbl}>Memories</Text></View>
            <View style={styles.stat}><Text style={styles.statNum}>{profile.by_kind?.reflection || 0}</Text><Text style={styles.statLbl}>Reflections</Text></View>
            <View style={styles.stat}><Text style={styles.statNum}>{profile.top_tags?.length || 0}</Text><Text style={styles.statLbl}>Topics</Text></View>
          </View>
        ) : null}

        {profile?.top_tags?.length ? (
          <View style={styles.tagWrap}>
            {profile.top_tags.slice(0, 8).map((t) => (
              <View key={t.tag} style={styles.tag}><Text style={styles.tagTxt}>#{t.tag} · {t.count}</Text></View>
            ))}
          </View>
        ) : null}

        {/* remember */}
        <Text style={styles.sectionTitle}>Remember an episode</Text>
        <View style={styles.row}>
          <TextInput testID="am-new-input" style={[styles.input, { minHeight: 44 }]} value={newMem} onChangeText={setNewMem}
            placeholder="what happened…" placeholderTextColor="#52525b" multiline />
          <TouchableOpacity testID="am-remember" style={styles.primaryBtn} onPress={doRemember}><Text style={styles.primaryTxt}>Save</Text></TouchableOpacity>
        </View>

        {/* reflect */}
        <TouchableOpacity testID="am-reflect" style={styles.reflectBtn} onPress={doReflect} disabled={reflecting}>
          {reflecting ? <ActivityIndicator color="#fff" /> : <Text style={styles.reflectTxt}>💡 Reflect on recent memories</Text>}
        </TouchableOpacity>
        {reflection ? (
          <View testID="am-reflection" style={styles.reflectionCard}>
            <Text style={styles.reflectionLabel}>DISTILLED LESSON</Text>
            <Text style={styles.reflectionTxt}>{reflection}</Text>
          </View>
        ) : null}

        {/* recall */}
        <Text style={styles.sectionTitle}>Recall</Text>
        <View style={styles.row}>
          <TextInput testID="am-recall-input" style={styles.input} value={query} onChangeText={setQuery}
            placeholder="search memories…" placeholderTextColor="#52525b" onSubmitEditing={doRecall} returnKeyType="search" />
          <TouchableOpacity testID="am-recall-btn" style={styles.smallBtn} onPress={doRecall}><Text style={styles.smallBtnTxt}>🔍</Text></TouchableOpacity>
        </View>

        {loading ? <ActivityIndicator color="#A78BFA" style={{ marginTop: 20 }} /> : recall.length === 0 ? (
          <Text testID="am-empty" style={styles.empty}>No memories yet — save an episode above to begin building this agent memory.</Text>
        ) : recall.map((m) => (
          <View key={m.memory_id} testID={`am-mem-${m.memory_id}`} style={[styles.memRow, m.kind === 'reflection' && styles.memReflection]}>
            <Text style={styles.memKind}>{KIND_EMOJI[m.kind] || '📓'}</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.memContent}>{m.content}</Text>
              <Text style={styles.memMeta}>
                {m.kind}{m.relevance != null ? ` · ${Math.round(m.relevance * 100)}% match` : ''}{m.importance ? ` · ⭐${m.importance}` : ''}
              </Text>
            </View>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#0A0A0A' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#262626' },
  backBtn: { paddingVertical: 6, paddingRight: 12 }, backTxt: { color: '#94a3b8', fontSize: 15 },
  title: { flex: 1, color: '#f1f5f9', fontSize: 20, fontWeight: '800' },
  toast: { backgroundColor: '#2E1B5B', margin: 12, padding: 12, borderRadius: 10, borderWidth: 1, borderColor: '#8B5CF6' }, toastTxt: { color: '#e0e7ff', fontWeight: '700' },
  sectionTitle: { color: '#cbd5e1', fontSize: 15, fontWeight: '800', marginBottom: 10, marginTop: 14 },
  row: { flexDirection: 'row', gap: 8, alignItems: 'flex-start' },
  input: { flex: 1, backgroundColor: '#141414', borderRadius: 10, borderWidth: 1, borderColor: '#262626', color: '#f1f5f9', paddingHorizontal: 12, paddingVertical: 11, fontSize: 14 },
  smallBtn: { backgroundColor: '#262626', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 11, justifyContent: 'center' }, smallBtnTxt: { color: '#e2e8f0', fontWeight: '700' },
  primaryBtn: { backgroundColor: '#8B5CF6', borderRadius: 10, paddingHorizontal: 16, paddingVertical: 11, justifyContent: 'center' }, primaryTxt: { color: '#fff', fontWeight: '800' },
  agentChip: { backgroundColor: '#141414', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10, marginRight: 8, borderWidth: 1, borderColor: '#262626' },
  agentChipOn: { borderColor: '#8B5CF6', backgroundColor: '#160f24' },
  agentName: { color: '#cbd5e1', fontWeight: '800' }, agentNameOn: { color: '#d8b4fe' },
  agentMeta: { color: '#64748b', fontSize: 11, marginTop: 2 },
  statsRow: { flexDirection: 'row', gap: 10, marginTop: 14 },
  stat: { flex: 1, backgroundColor: '#141414', borderRadius: 12, paddingVertical: 14, alignItems: 'center', borderWidth: 1, borderColor: '#262626' },
  statNum: { color: '#A78BFA', fontSize: 20, fontWeight: '800' }, statLbl: { color: '#64748b', fontSize: 12, marginTop: 2 },
  tagWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 12 },
  tag: { backgroundColor: '#1f1f1f', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5 }, tagTxt: { color: '#94a3b8', fontSize: 12 },
  reflectBtn: { backgroundColor: '#7C3AED', borderRadius: 12, paddingVertical: 14, alignItems: 'center', marginTop: 14 }, reflectTxt: { color: '#fff', fontWeight: '800', fontSize: 15 },
  reflectionCard: { backgroundColor: '#160f24', borderRadius: 12, padding: 16, marginTop: 12, borderWidth: 1, borderColor: '#8B5CF6' },
  reflectionLabel: { color: '#a78bfa', fontSize: 11, fontWeight: '800', letterSpacing: 1, marginBottom: 6 },
  reflectionTxt: { color: '#ede9fe', fontSize: 15, lineHeight: 22 },
  empty: { color: '#64748b', fontSize: 13, marginTop: 16, lineHeight: 20, textAlign: 'center' },
  memRow: { flexDirection: 'row', gap: 10, backgroundColor: '#141414', borderRadius: 12, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: '#262626' },
  memReflection: { borderColor: '#8B5CF6', backgroundColor: '#160f24' },
  memKind: { fontSize: 18 },
  memContent: { color: '#e2e8f0', fontSize: 14, lineHeight: 20 },
  memMeta: { color: '#64748b', fontSize: 11, marginTop: 4 },
});
