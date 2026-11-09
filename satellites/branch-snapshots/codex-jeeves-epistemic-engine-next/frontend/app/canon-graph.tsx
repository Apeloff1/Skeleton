/**
 * /canon-graph — 🕸️ Canon knowledge graph + 🧠 RAG recall + 🩺 Consistency audit.
 * - A force-directed (radial-cluster) SVG map of typed nodes + inferred relationships.
 * - Interactive canon recall: type a query, retrieve the most relevant canon (RAG).
 * - Consistency Auditor: orphaned entities, stale artifacts, missing stages + a health score.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator, StyleSheet, SafeAreaView, TextInput,
} from 'react-native';
import Svg, { Circle, Line, Text as SvgText } from 'react-native-svg';
import { useRouter, useLocalSearchParams } from 'expo-router';
import api from '../src/utils/apiClient';

const TYPE_COLOR: Record<string, string> = {
  Faction: '#f472b6', Region: '#34d399', Character: '#fbbf24', Quest: '#60a5fa',
  Creature: '#f87171', Mechanic: '#c084fc', Concept: '#93C5FD', Pillar: '#a78bfa',
};
const W = 358, H = 358, CX = W / 2, CY = H / 2;

export default function CanonGraph() {
  const router = useRouter();
  const params = useLocalSearchParams<{ game?: string }>();
  const gameId = params?.game ? String(params.game) : '';
  const [graph, setGraph] = React.useState<any>(null);
  const [audit, setAudit] = React.useState<any>(null);
  const [sel, setSel] = React.useState<string | null>(null);
  const [filter, setFilter] = React.useState<string | null>(null);
  const [q, setQ] = React.useState('');
  const [hits, setHits] = React.useState<any[] | null>(null);
  const [recalling, setRecalling] = React.useState(false);
  const [heal, setHeal] = React.useState<any | null>(null);
  const [healing, setHealing] = React.useState(false);
  const [applied, setApplied] = React.useState<Record<number, string>>({});

  React.useEffect(() => {
    (async () => {
      const [g, a] = await Promise.all([
        api.get<any>(`/api/graph/${gameId}`, { timeoutMs: 12000 }),
        api.get<any>(`/api/graph/${gameId}/audit`, { timeoutMs: 12000 }),
      ]);
      if (g.ok && g.data && !g.data.error) setGraph(g.data);
      if (a.ok && a.data && !a.data.error) setAudit(a.data);
    })();
  }, [gameId]);

  // deterministic radial-cluster layout: cluster nodes by type, spread each cluster on a ring
  const pos = React.useMemo(() => {
    const m: Record<string, { x: number; y: number; color: string; type: string; name: string }> = {};
    if (!graph) return m;
    const types: string[] = Object.keys(graph.by_type || {});
    const byType: Record<string, any[]> = {};
    (graph.nodes || []).forEach((n: any) => { (byType[n.type] = byType[n.type] || []).push(n); });
    types.forEach((t, ti) => {
      const ca = (ti / Math.max(1, types.length)) * Math.PI * 2 - Math.PI / 2;
      const ccx = CX + Math.cos(ca) * 115, ccy = CY + Math.sin(ca) * 115;
      const list = byType[t] || [];
      list.forEach((n, j) => {
        const a = (j / Math.max(1, list.length)) * Math.PI * 2;
        const r = list.length > 1 ? 30 + (j % 2) * 14 : 0;
        m[n.id] = { x: ccx + Math.cos(a) * r, y: ccy + Math.sin(a) * r, color: TYPE_COLOR[t] || '#94a3b8', type: t, name: n.name };
      });
    });
    return m;
  }, [graph]);

  const recall = React.useCallback(async () => {
    const query = q.trim();
    if (!query || recalling) return;
    setRecalling(true); setHits(null);
    const r = await api.get<any>(`/api/rag/${gameId}/retrieve?q=${encodeURIComponent(query)}&k=6`, { timeoutMs: 12000 });
    setHits(r.ok && r.data?.hits ? r.data.hits : []);
    setRecalling(false);
  }, [q, recalling, gameId]);

  const runHeal = React.useCallback(async () => {
    if (healing) return;
    setHealing(true); setHeal(null);
    const r = await api.post<any>(`/api/graph/${gameId}/heal`, {}, { timeoutMs: 120000 });
    setHeal(r.ok && r.data && !r.data.error ? r.data : { error: r.data?.error || 'Auto-heal failed — try again.', fixes: [] });
    setHealing(false);
  }, [healing, gameId]);

  const applyFix = React.useCallback(async (idx: number, f: any) => {
    if (applied[idx]) return;
    setApplied((m) => ({ ...m, [idx]: 'applying' }));
    const r = await api.post<any>(`/api/graph/${gameId}/heal/apply`, {
      entity: f.entity, etype: f.etype, title: f.title, patch: f.patch, links: f.links,
    }, { timeoutMs: 15000 });
    setApplied((m) => ({ ...m, [idx]: r.ok && r.data?.ok ? 'done' : 'error' }));
  }, [applied, gameId]);

  const applyAll = React.useCallback(async () => {
    const fixes = heal?.fixes || [];
    if (!fixes.length) return;
    const r = await api.post<any>(`/api/graph/${gameId}/heal/apply-all`, { fixes }, { timeoutMs: 20000 });
    if (r.ok && r.data?.ok) {
      const done: Record<number, string> = {};
      fixes.forEach((_f: any, i: number) => { done[i] = 'done'; });
      setApplied(done);
    }
  }, [heal, gameId]);

  if (!graph) {
    return (
      <SafeAreaView style={s.root}>
        <View style={s.header}><Text style={s.title}>🕸️ Canon Graph</Text></View>
        <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color="#93C5FD" /></View>
      </SafeAreaView>
    );
  }

  const nameById: Record<string, any> = {};
  (graph.nodes || []).forEach((n: any) => { nameById[n.id] = n; });
  const selEdges = sel ? (graph.edges || []).filter((e: any) => e.source === sel || e.target === sel) : [];
  const types = Object.keys(graph.by_type || {});
  const listNodes = (graph.nodes || []).filter((n: any) => !filter || n.type === filter);

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.back}><Text style={s.backTxt}>‹ Back</Text></TouchableOpacity>
        <Text style={s.title}>🕸️ Canon Graph</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 50 }}>
        <Text style={s.stat}>{graph.node_count} nodes · {graph.edge_count} relationships</Text>

        {/* force-directed SVG map */}
        <View style={s.canvas}>
          <Svg width={W} height={H}>
            {(graph.edges || []).map((e: any, i: number) => {
              const a = pos[e.source], b = pos[e.target];
              if (!a || !b) return null;
              const hot = sel && (e.source === sel || e.target === sel);
              return <Line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke={hot ? '#93C5FD' : '#243046'} strokeWidth={hot ? 1.6 : 0.8} />;
            })}
            {(graph.nodes || []).map((n: any) => {
              const p = pos[n.id]; if (!p) return null;
              const on = sel === n.id;
              const dim = !!filter && n.type !== filter;
              return (
                <React.Fragment key={n.id}>
                  <Circle cx={p.x} cy={p.y} r={on ? 9 : 5.5} fill={p.color} opacity={dim ? 0.18 : 1}
                    stroke={on ? '#fff' : 'none'} strokeWidth={on ? 1.5 : 0}
                    onPress={() => setSel(on ? null : n.id)} />
                  {on && <SvgText x={p.x} y={p.y - 13} fill="#fff" fontSize="9" fontWeight="bold" textAnchor="middle">{n.name.slice(0, 18)}</SvgText>}
                </React.Fragment>
              );
            })}
          </Svg>
          <Text style={s.canvasHint}>tap a node to trace its relationships</Text>
        </View>

        {/* type filter chips */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, marginTop: 10 }}>
          <TouchableOpacity onPress={() => setFilter(null)} style={[s.chip, !filter && s.chipOn]}><Text style={[s.chipTxt, !filter && s.chipTxtOn]}>All</Text></TouchableOpacity>
          {types.map(t => (
            <TouchableOpacity key={t} testID={`graph-filter-${t}`} onPress={() => setFilter(filter === t ? null : t)} style={[s.chip, filter === t && s.chipOn, { borderColor: TYPE_COLOR[t] || '#334155' }]}>
              <Text style={[s.chipTxt, { color: TYPE_COLOR[t] || '#94a3b8' }]}>{t} {graph.by_type[t]}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* selected node detail */}
        {sel && nameById[sel] && (
          <View style={[s.detail, { borderLeftColor: TYPE_COLOR[nameById[sel].type] || '#334155' }]}>
            <Text style={[s.nodeType, { color: TYPE_COLOR[nameById[sel].type] }]}>{nameById[sel].type}</Text>
            <Text style={s.nodeName}>{nameById[sel].name}</Text>
            {selEdges.length === 0 && <Text style={s.noEdge}>No relationships inferred.</Text>}
            {selEdges.map((e: any, i: number) => {
              const out = e.source === sel; const other = nameById[out ? e.target : e.source];
              return <Text key={i} style={s.edge}>{out ? '→ ' : '← '}<Text style={s.edgeRel}>{e.rel}</Text> {other?.name} <Text style={s.edgeType}>({other?.type})</Text></Text>;
            })}
          </View>
        )}

        {/* 🧠 RAG recall */}
        <Text style={s.section}>🧠 Canon recall</Text>
        <View style={s.recallRow}>
          <TextInput testID="recall-input" value={q} onChangeText={setQ} onSubmitEditing={recall}
            placeholder="Ask the canon (e.g. 'rival factions', 'boss enemy')" placeholderTextColor="#475569" style={s.recallInput} />
          <TouchableOpacity testID="recall-btn" onPress={recall} disabled={recalling || !q.trim()} style={[s.recallBtn, (recalling || !q.trim()) && s.off]} activeOpacity={0.9}>
            {recalling ? <ActivityIndicator size="small" color="#fff" /> : <Text style={s.recallBtnTxt}>🔎</Text>}
          </TouchableOpacity>
        </View>
        {hits !== null && (
          <View style={s.hits}>
            {hits.length === 0 && <Text style={s.noEdge}>No matching canon found.</Text>}
            {hits.map((h: any, i: number) => (
              <View key={i} testID={`recall-hit-${i}`} style={s.hit}>
                <Text style={[s.hitType, { color: TYPE_COLOR[h.type] || '#94a3b8' }]}>{h.type} · {h.name} <Text style={s.hitScore}>({h.score})</Text></Text>
                <Text style={s.hitText} numberOfLines={2}>{h.text}</Text>
              </View>
            ))}
          </View>
        )}

        {/* 🩺 Consistency audit */}
        {audit && (
          <>
            <Text style={s.section}>🩺 Consistency audit</Text>
            <View style={s.auditBar}>
              <Text style={[s.auditScore, { color: audit.score >= 80 ? '#4ade80' : audit.score >= 50 ? '#fbbf24' : '#f87171' }]}>{audit.score}</Text>
              <View style={{ flex: 1 }}>
                <Text style={s.auditSummary}>{audit.errors} errors · {audit.warnings} warnings · {audit.issue_count} issues</Text>
                <Text style={s.auditHint}>{audit.issue_count === 0 ? 'Canon is consistent ✨' : 'Re-run flagged stages to resolve'}</Text>
              </View>
            </View>
            {audit.issue_count > 0 && (
              <TouchableOpacity testID="audit-autoresolve" onPress={() => router.push(`/groupchat?game=${gameId}&stale=1` as any)}
                style={{ marginTop: 10, backgroundColor: '#6366f1', borderRadius: 10, paddingVertical: 13, alignItems: 'center' }} activeOpacity={0.9}>
                <Text style={{ color: '#fff', fontSize: 13, fontWeight: '800' }}>⚡ Auto-resolve stale stages (GroupChat)</Text>
              </TouchableOpacity>
            )}
            {(audit.issues || []).map((it: any, i: number) => (
              <View key={i} testID={`audit-issue-${i}`} style={[s.issue, it.severity === 'error' ? s.issErr : it.severity === 'warn' ? s.issWarn : s.issInfo]}>
                <Text style={s.issTxt}>{it.severity === 'error' ? '⛔' : it.severity === 'warn' ? '⚠️' : 'ℹ️'} {it.message}</Text>
              </View>
            ))}

            {/* 🪄 Auto-heal — LLM proposes grounded canon patches for orphans/thin quests */}
            {audit.issue_count > 0 && (
              <TouchableOpacity testID="canon-heal-btn" onPress={runHeal} disabled={healing}
                style={[{ marginTop: 10, backgroundColor: '#7c3aed', borderRadius: 10, paddingVertical: 13, alignItems: 'center' }, healing && s.off]} activeOpacity={0.9}>
                {healing
                  ? <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}><ActivityIndicator size="small" color="#fff" /><Text style={{ color: '#fff', fontSize: 13, fontWeight: '800' }}>Healing canon…</Text></View>
                  : <Text style={{ color: '#fff', fontSize: 13, fontWeight: '800' }}>🪄 Auto-heal canon (AI fixes)</Text>}
              </TouchableOpacity>
            )}
            {heal && (
              heal.error ? (
                <View testID="canon-heal-error" style={[s.issue, s.issErr, { marginTop: 8 }]}>
                  <Text style={s.issTxt}>⛔ {heal.error}</Text>
                </View>
              ) : (heal.fixes || []).length === 0 ? (
                <View testID="canon-heal-empty" style={[s.issue, s.issInfo, { marginTop: 8 }]}>
                  <Text style={s.issTxt}>✨ {heal.message || 'No narrative gaps to heal.'}</Text>
                </View>
              ) : (
                <>
                  <Text testID="canon-heal-head" style={[s.auditHint, { marginTop: 10 }]}>🪄 {heal.fixes.length} proposed canon patches{heal.model ? ` · ${heal.model}` : ''}</Text>
                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 6 }}>
                    <TouchableOpacity testID="heal-apply-all" onPress={applyAll} style={{ flex: 1, backgroundColor: '#6d28d9', borderRadius: 8, paddingVertical: 10, alignItems: 'center' }}>
                      <Text style={{ color: '#fff', fontSize: 12, fontWeight: '800' }}>🩹 Apply all</Text>
                    </TouchableOpacity>
                    <TouchableOpacity testID="open-scorecard" onPress={() => router.push(`/scorecard?game=${gameId}` as any)} style={{ flex: 1, backgroundColor: '#1E40AF', borderRadius: 8, paddingVertical: 10, alignItems: 'center' }}>
                      <Text style={{ color: '#fff', fontSize: 12, fontWeight: '800' }}>🩺 Scorecard</Text>
                    </TouchableOpacity>
                  </View>
                  {heal.fixes.map((f: any, i: number) => (
                    <View key={i} testID={`heal-fix-${i}`} style={s.fix}>
                      <Text style={s.fixTitle}>{f.title}</Text>
                      <Text style={s.fixEntity}>{f.etype} · {f.entity}</Text>
                      <Text style={s.fixPatch}>{f.patch}</Text>
                      {(f.links || []).length > 0 && (
                        <View style={s.fixLinks}>
                          {f.links.map((l: string, j: number) => (
                            <View key={j} style={s.fixLink}><Text style={s.fixLinkTxt}>🔗 {l}</Text></View>
                          ))}
                        </View>
                      )}
                      <TouchableOpacity testID={`heal-apply-${i}`} onPress={() => applyFix(i, f)}
                        disabled={!!applied[i]} activeOpacity={0.85}
                        style={[s.applyBtn, applied[i] === 'done' && s.applyDone, applied[i] === 'error' && s.applyErr]}>
                        <Text style={s.applyTxt}>
                          {applied[i] === 'applying' ? '⏳ Applying…'
                            : applied[i] === 'done' ? '✓ Applied · stage marked for regen'
                            : applied[i] === 'error' ? '⚠️ Retry apply'
                            : '🩹 Apply patch'}
                        </Text>
                      </TouchableOpacity>
                    </View>
                  ))}
                </>
              )
            )}
          </>
        )}

        {/* node list */}
        <Text style={s.section}>All nodes</Text>
        {listNodes.map((n: any) => (
          <TouchableOpacity key={n.id} testID={`graph-node-${n.id}`} onPress={() => setSel(n.id)} activeOpacity={0.85}
            style={[s.lnode, sel === n.id && s.nodeOn, { borderLeftColor: TYPE_COLOR[n.type] || '#334155' }]}>
            <Text style={[s.nodeType, { color: TYPE_COLOR[n.type] }]}>{n.type}</Text>
            <Text style={s.nodeName}>{n.name}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#05070d' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#141c2e', gap: 8 },
  back: { paddingVertical: 6, paddingHorizontal: 8 },
  backTxt: { color: '#60a5fa', fontSize: 15, fontWeight: '700' },
  title: { color: '#F8FAFC', fontSize: 18, fontWeight: '800' },
  stat: { color: '#93C5FD', fontSize: 12, fontWeight: '700', marginBottom: 8 },
  canvas: { backgroundColor: '#070b16', borderRadius: 14, borderWidth: 1, borderColor: '#1e293b', alignItems: 'center', paddingVertical: 8 },
  canvasHint: { color: '#475569', fontSize: 11, marginTop: 2 },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, borderWidth: 1, borderColor: '#334155' },
  chipOn: { backgroundColor: '#141a36' },
  chipTxt: { color: '#94a3b8', fontSize: 12, fontWeight: '700' },
  chipTxtOn: { color: '#e2e8f0' },
  detail: { backgroundColor: '#0b1220', borderRadius: 10, borderWidth: 1, borderColor: '#1e293b', borderLeftWidth: 4, padding: 12, marginTop: 10, gap: 3 },
  nodeType: { fontSize: 10, fontWeight: '900' },
  nodeName: { color: '#E2E8F0', fontSize: 14, fontWeight: '700' },
  noEdge: { color: '#64748b', fontSize: 12, fontStyle: 'italic' },
  edge: { color: '#cbd5e1', fontSize: 12 },
  edgeRel: { color: '#fbbf24', fontWeight: '800' },
  edgeType: { color: '#64748b' },
  section: { color: '#94A3B8', fontSize: 13, fontWeight: '800', marginTop: 20, marginBottom: 8 },
  recallRow: { flexDirection: 'row', gap: 8 },
  recallInput: { flex: 1, backgroundColor: '#070b16', borderRadius: 9, borderWidth: 1, borderColor: '#27324A', color: '#E2E8F0', fontSize: 13, paddingHorizontal: 12, height: 44 },
  recallBtn: { width: 48, backgroundColor: '#6366f1', borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  recallBtnTxt: { fontSize: 18 },
  off: { opacity: 0.5 },
  hits: { marginTop: 8, gap: 6 },
  hit: { backgroundColor: '#0b1220', borderRadius: 8, borderWidth: 1, borderColor: '#1e293b', padding: 10 },
  hitType: { fontSize: 12, fontWeight: '800' },
  hitScore: { color: '#475569', fontWeight: '600' },
  hitText: { color: '#94A3B8', fontSize: 12, marginTop: 2 },
  auditBar: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#0b1220', borderRadius: 12, borderWidth: 1, borderColor: '#1e293b', padding: 14 },
  auditScore: { fontSize: 34, fontWeight: '900', minWidth: 52, textAlign: 'center' },
  auditSummary: { color: '#E2E8F0', fontSize: 13, fontWeight: '700' },
  auditHint: { color: '#64748b', fontSize: 12, marginTop: 2 },
  issue: { borderRadius: 8, borderWidth: 1, padding: 10, marginTop: 6 },
  issErr: { backgroundColor: '#2a0e0e', borderColor: '#7f1d1d' },
  issWarn: { backgroundColor: '#231a05', borderColor: '#854d0e' },
  issInfo: { backgroundColor: '#0a1528', borderColor: '#1e3a5f' },
  issTxt: { color: '#e2e8f0', fontSize: 12, lineHeight: 17 },
  fix: { backgroundColor: '#160d2e', borderRadius: 10, borderWidth: 1, borderColor: '#4c1d95', borderLeftWidth: 4, borderLeftColor: '#a855f7', padding: 12, marginTop: 8, gap: 3 },
  fixTitle: { color: '#f5f3ff', fontSize: 13, fontWeight: '800' },
  fixEntity: { color: '#c084fc', fontSize: 11, fontWeight: '700' },
  fixPatch: { color: '#cbd5e1', fontSize: 12, lineHeight: 17, marginTop: 2 },
  fixLinks: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 6 },
  fixLink: { backgroundColor: '#2e1065', borderRadius: 12, paddingHorizontal: 9, paddingVertical: 4 },
  fixLinkTxt: { color: '#ddd6fe', fontSize: 11, fontWeight: '600' },
  applyBtn: { marginTop: 8, backgroundColor: '#7c3aed', borderRadius: 8, paddingVertical: 9, alignItems: 'center' },
  applyDone: { backgroundColor: '#166534' },
  applyErr: { backgroundColor: '#7f1d1d' },
  applyTxt: { color: '#fff', fontSize: 12, fontWeight: '800' },
  lnode: { backgroundColor: '#0b1220', borderRadius: 10, borderWidth: 1, borderColor: '#1e293b', borderLeftWidth: 4, padding: 12, marginBottom: 8, gap: 2 },
  nodeOn: { borderColor: '#60A5FA' },
});
