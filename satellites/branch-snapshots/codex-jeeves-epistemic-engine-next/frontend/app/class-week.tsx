/**
 * Class Week Detail
 *
 * Renders the full week payload from `/api/curriculum/classes/{id}/week/{w}`:
 *   • Learning objectives chips
 *   • Prose sections (markdown-lite)
 *   • Code examples (mono-spaced)
 *   • Exercises (numbered)
 *   • Lab assignment (problem / starter / hints / tests / rubric)
 *   • Glossary (interactive expand cards)
 *   • Comprehension questions (self-assess)
 *   • Further reading
 *
 * Reached from `/my-classes` by tapping a week row.
 */
import { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { api } from '../utils/apiController';
import theme from '../theme/tokens';
import { Screen, AppHeader } from '../components/ui';

interface WeekContent {
  week: number;
  title: string;
  topics?: string[];
  learning_objectives?: string[];
  prose?: { heading: string; text: string }[];
  code_examples?: { language: string; code: string; caption?: string }[];
  exercises?: string[];
  lab?: {
    title: string;
    problem: string;
    starter_code: string;
    hints: string[];
    tests: string[];
    estimated_minutes: number;
    grading_rubric: Record<string, number>;
  };
  glossary?: { term: string; definition: string }[];
  comprehension_questions?: string[];
  further_reading?: string[];
  assessment_rubric?: Record<string, number>;
  estimated_hours?: number;
  depth_level?: string;
}

export default function ClassWeekScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ classId?: string; week?: string; classTitle?: string }>();
  const classId = String(params.classId || '');
  const weekIdx = Number(params.week || 1);

  const [content, setContent] = useState<WeekContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedGlossary, setExpandedGlossary] = useState<Record<number, boolean>>({});
  const [expandedCompQ, setExpandedCompQ] = useState<Record<number, boolean>>({});
  const [tab, setTab] = useState<'read' | 'lab' | 'practice'>('read');

  const load = useCallback(async () => {
    if (!classId || !weekIdx) return;
    setLoading(true); setError(null);
    try {
      const d = await api.get<WeekContent>(
        `/api/curriculum/classes/${classId}/week/${weekIdx}`,
        { tag: 'curriculum.week', cacheTtlMs: 10 * 60_000, cachePersist: true, timeoutMs: 12_000 },
      );
      setContent(d);
    } catch (e: any) {
      setError(e?.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [classId, weekIdx]);

  useEffect(() => { load(); }, [load]);

  // ★ 2026-05 fix — proper empty state when route is hit with no params.
  // Previously the screen would idle on "Loading week…" forever because
  // `load()` early-returned. Now shows a clear empty-state with back +
  // "Pick a class" CTA.
  if (!classId || !weekIdx) {
    return (
      <Screen edges={['top']}>
        <AppHeader title="Class Week" onBack={() => router.back()} />
        <View style={s.center}>
          <Ionicons name="school-outline" size={48} color={theme.colors.textMuted} />
          <Text style={[s.dimText, { fontSize: 14 }]}>Pick a class to view its weekly content.</Text>
          <TouchableOpacity onPress={() => router.push('/my-classes')} style={s.retryBtn}>
            <Text style={s.retryText}>Browse Classes</Text>
          </TouchableOpacity>
        </View>
      </Screen>
    );
  }

  if (loading) {
    return (
      <Screen edges={['top']}>
        <AppHeader title="Class Week" subtitle={`Week ${weekIdx}`} onBack={() => router.back()} />
        <View style={s.center}><ActivityIndicator color={theme.colors.primary} /><Text style={s.dimText}>Loading week…</Text></View>
      </Screen>
    );
  }
  if (error || !content) {
    return (
      <Screen edges={['top']}>
        <AppHeader title="Class Week" subtitle={`Week ${weekIdx}`} onBack={() => router.back()} />
        <View style={s.center}>
          <Ionicons name="alert-circle" size={32} color={theme.colors.danger} />
          <Text style={s.dimText}>{error || 'No content'}</Text>
          <TouchableOpacity onPress={load} style={s.retryBtn}><Text style={s.retryText}>Retry</Text></TouchableOpacity>
        </View>
      </Screen>
    );
  }

  return (
    <Screen edges={['top']}>
      <LinearGradient
        colors={['#8B5CF622', '#3B82F622', 'transparent'] as any}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.9, y: 0.6 }}
        style={[s.aurora, { pointerEvents: 'none' }]}
      />
      <AppHeader
        title={content.title}
        subtitle={`Week ${content.week} · ${content.depth_level || 'graduate'}`}
        onBack={() => router.back()}
        right={
          <TouchableOpacity
            onPress={() => router.push('/readingLibrary' as any)}
            style={[s.hdrBadge, { backgroundColor: '#fcd34d22', borderColor: '#fcd34d55' }]}
            activeOpacity={0.7}
            accessibilityLabel="Open reading library"
          >
            <Ionicons name="library-outline" size={12} color="#fcd34d" />
            <Text style={[s.hdrBadgeText, { color: '#fde68a', marginLeft: 4 }]}>Reading</Text>
          </TouchableOpacity>
        }
      />

      <View style={s.tabsRow}>
        {([
          { key: 'read', label: 'Read', icon: 'book' },
          { key: 'lab', label: 'Lab', icon: 'flask' },
          { key: 'practice', label: 'Practice', icon: 'school' },
        ] as const).map(t => (
          <TouchableOpacity key={t.key} style={[s.tab, tab === t.key && s.tabActive]} onPress={() => setTab(t.key as any)} activeOpacity={0.7}>
            <Ionicons name={t.icon as any} size={14} color={tab === t.key ? '#fff' : '#94A3B8'} />
            <Text style={[s.tabText, tab === t.key && s.tabTextActive]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 60 }}>
        {tab === 'read' && (
          <>
            {/* Topics */}
            {content.topics && content.topics.length > 0 && (
              <View style={s.topicsRow}>
                {content.topics.map(t => <View key={t} style={s.topicChip}><Text style={s.topicChipText}>{t}</Text></View>)}
              </View>
            )}

            {/* Learning objectives */}
            {content.learning_objectives && content.learning_objectives.length > 0 && (
              <View style={s.card}>
                <Text style={s.cardLabel}>Learning Objectives</Text>
                {content.learning_objectives.map((lo, i) => (
                  <View key={i} style={s.bulletRow}>
                    <View style={s.bulletDot} />
                    <Text style={s.bulletText}>{lo}</Text>
                  </View>
                ))}
              </View>
            )}

            {/* Prose */}
            {(content.prose || []).map((p, i) => (
              <View key={i} style={s.proseBlock}>
                <Text style={s.proseHeading}>{p.heading}</Text>
                <Text style={s.proseText}>{p.text}</Text>
              </View>
            ))}

            {/* Code examples */}
            {(content.code_examples || []).map((c, i) => (
              <View key={i} style={s.codeCard}>
                <View style={s.codeHead}>
                  <Ionicons name="code-slash" size={12} color="#3B82F6" />
                  <Text style={s.codeLang}>{c.language || 'code'}</Text>
                  {c.caption ? <Text style={s.codeCaption}> · {c.caption}</Text> : null}
                </View>
                <Text style={s.codeBody}>{c.code}</Text>
              </View>
            ))}

            {/* Further reading */}
            {(content.further_reading || []).length > 0 && (
              <View style={s.card}>
                <Text style={s.cardLabel}>Further Reading</Text>
                {(content.further_reading || []).map((fr, i) => (
                  <Text key={i} style={s.refText}>• {fr}</Text>
                ))}
              </View>
            )}
          </>
        )}

        {tab === 'lab' && (
          <>
            {content.lab ? (
              <View>
                <View style={s.labHead}>
                  <Ionicons name="flask" size={20} color="#F59E0B" />
                  <View style={{ flex: 1 }}>
                    <Text style={s.labTitle}>{content.lab.title}</Text>
                    <Text style={s.labMeta}>~{content.lab.estimated_minutes} min · graded</Text>
                  </View>
                </View>
                <View style={s.card}>
                  <Text style={s.cardLabel}>Problem</Text>
                  <Text style={s.proseText}>{content.lab.problem}</Text>
                </View>
                <View style={s.codeCard}>
                  <View style={s.codeHead}>
                    <Ionicons name="document-text" size={12} color="#10B981" />
                    <Text style={s.codeLang}>starter</Text>
                  </View>
                  <Text style={s.codeBody}>{content.lab.starter_code}</Text>
                </View>
                {content.lab.hints && content.lab.hints.length > 0 && (
                  <View style={s.card}>
                    <Text style={s.cardLabel}>Hints</Text>
                    {content.lab.hints.map((h, i) => (
                      <View key={i} style={s.bulletRow}>
                        <Text style={s.bulletNum}>{i + 1}.</Text>
                        <Text style={s.bulletText}>{h}</Text>
                      </View>
                    ))}
                  </View>
                )}
                {content.lab.tests && content.lab.tests.length > 0 && (
                  <View style={s.card}>
                    <Text style={s.cardLabel}>Acceptance Tests</Text>
                    {content.lab.tests.map((t, i) => (
                      <View key={i} style={s.bulletRow}>
                        <Ionicons name="checkmark-circle" size={14} color="#10B981" />
                        <Text style={s.bulletText}>{t}</Text>
                      </View>
                    ))}
                  </View>
                )}
                {content.lab.grading_rubric && (
                  <View style={s.card}>
                    <Text style={s.cardLabel}>Grading Rubric</Text>
                    {Object.entries(content.lab.grading_rubric).map(([k, v]) => (
                      <View key={k} style={s.rubricRow}>
                        <Text style={s.rubricLabel}>{k.replace(/_/g, ' ')}</Text>
                        <View style={s.rubricBar}>
                          <View style={[s.rubricFill, { width: `${v}%` }]} />
                        </View>
                        <Text style={s.rubricPct}>{v}%</Text>
                      </View>
                    ))}
                  </View>
                )}
              </View>
            ) : (
              <Text style={s.dimText}>This week does not have a lab assigned.</Text>
            )}
          </>
        )}

        {tab === 'practice' && (
          <>
            {/* Comprehension questions */}
            {(content.comprehension_questions || []).length > 0 && (
              <View style={s.card}>
                <Text style={s.cardLabel}>Comprehension Self-Check</Text>
                {(content.comprehension_questions || []).map((q, i) => (
                  <TouchableOpacity
                    key={i}
                    style={s.compRow}
                    onPress={() => setExpandedCompQ(e => ({ ...e, [i]: !e[i] }))}
                    activeOpacity={0.8}
                  >
                    <Ionicons name={expandedCompQ[i] ? 'chevron-down' : 'chevron-forward'} size={14} color="#94A3B8" />
                    <Text style={s.compText}>{q}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}

            {/* Glossary */}
            {(content.glossary || []).length > 0 && (
              <View style={s.card}>
                <Text style={s.cardLabel}>Glossary ({(content.glossary || []).length})</Text>
                {(content.glossary || []).map((g, i) => (
                  <TouchableOpacity
                    key={i}
                    style={s.glossRow}
                    onPress={() => setExpandedGlossary(e => ({ ...e, [i]: !e[i] }))}
                    activeOpacity={0.8}
                  >
                    <View style={s.glossHead}>
                      <Ionicons name={expandedGlossary[i] ? 'chevron-down' : 'chevron-forward'} size={14} color="#A78BFA" />
                      <Text style={s.glossTerm}>{g.term}</Text>
                    </View>
                    {expandedGlossary[i] && <Text style={s.glossDef}>{g.definition}</Text>}
                  </TouchableOpacity>
                ))}
              </View>
            )}

            {/* Exercises */}
            {(content.exercises || []).length > 0 && (
              <View style={s.card}>
                <Text style={s.cardLabel}>Exercises</Text>
                {(content.exercises || []).map((ex, i) => (
                  <View key={i} style={s.bulletRow}>
                    <Text style={s.bulletNum}>•</Text>
                    <Text style={s.bulletText}>{ex}</Text>
                  </View>
                ))}
              </View>
            )}

            {/* Assessment rubric */}
            {content.assessment_rubric && (
              <View style={s.card}>
                <Text style={s.cardLabel}>Weekly Assessment Rubric</Text>
                {Object.entries(content.assessment_rubric).map(([k, v]) => (
                  <View key={k} style={s.rubricRow}>
                    <Text style={s.rubricLabel}>{k.replace(/_/g, ' ')}</Text>
                    <View style={s.rubricBar}>
                      <View style={[s.rubricFill, { width: `${v}%` }]} />
                    </View>
                    <Text style={s.rubricPct}>{v}%</Text>
                  </View>
                ))}
              </View>
            )}
          </>
        )}
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  aurora: { position: 'absolute', top: 0, left: 0, right: 0, height: 240 },
  container: { flex: 1, backgroundColor: theme.colors.bg },
  header: { flexDirection: 'row', alignItems: 'center', padding: 10, backgroundColor: theme.colors.bgElevated, borderBottomWidth: 1, borderBottomColor: theme.colors.border, gap: 8 },
  hdrBtn: { width: 36, height: 36, justifyContent: 'center', alignItems: 'center' },
  hdrCrumb: { color: theme.colors.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase' },
  hdrTitle: { color: theme.colors.text, fontSize: 15, fontWeight: '800' },
  hdrBadge: { backgroundColor: theme.colors.primarySoft, paddingHorizontal: 10, paddingVertical: 5, borderRadius: theme.radii.full, borderWidth: 1, borderColor: theme.colors.primary + '44' },
  hdrBadgeText: { color: theme.colors.primary, fontSize: 9, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5 },
  tabsRow: { flexDirection: 'row', backgroundColor: theme.colors.surface, borderRadius: theme.radii.lg, padding: 4, marginHorizontal: theme.spacing.base, marginTop: theme.spacing.sm, borderWidth: 1, borderColor: theme.colors.border, gap: 4 },
  tab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 9, borderRadius: theme.radii.md },
  tabActive: { backgroundColor: theme.colors.primary, ...theme.elevation.xs },
  tabText: { color: theme.colors.textMuted, fontSize: 12, fontWeight: '700' },
  tabTextActive: { color: '#fff' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 12 },
  dimText: { color: theme.colors.textMuted, fontSize: 13 },
  retryBtn: { backgroundColor: theme.colors.primary, borderRadius: theme.radii.md, paddingHorizontal: 16, paddingVertical: 8 },
  retryText: { color: '#fff', fontSize: 13, fontWeight: '700' },
  topicsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 10 },
  topicChip: { backgroundColor: theme.colors.surface, borderRadius: theme.radii.full, paddingHorizontal: 10, paddingVertical: 4, borderWidth: 1, borderColor: theme.colors.border },
  topicChipText: { color: theme.colors.primary, fontSize: 10, fontWeight: '700' },
  card: { backgroundColor: theme.colors.surface, borderRadius: theme.radii.lg, padding: theme.spacing.md, marginBottom: theme.spacing.md, borderWidth: 1, borderColor: theme.colors.border },
  cardLabel: { color: theme.colors.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 0.6, textTransform: 'uppercase', marginBottom: 8 },
  bulletRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, marginBottom: 6 },
  bulletDot: { width: 5, height: 5, borderRadius: 2.5, backgroundColor: theme.colors.primary, marginTop: 7 },
  bulletNum: { color: theme.colors.primary, fontSize: 12, fontWeight: '800', minWidth: 18 },
  bulletText: { color: theme.colors.text, fontSize: 13, lineHeight: 19, flex: 1 },
  proseBlock: { marginBottom: 16 },
  proseHeading: { color: theme.colors.text, fontSize: 17, fontWeight: '800', letterSpacing: -0.2, marginBottom: 6 },
  proseText: { color: theme.colors.textMuted, fontSize: 13, lineHeight: 20 },
  codeCard: { backgroundColor: theme.colors.bgSubtle, borderRadius: theme.radii.md, padding: 10, marginBottom: 12, borderWidth: 1, borderColor: theme.colors.border },
  codeHead: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 6 },
  codeLang: { color: theme.colors.primary, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5 },
  codeCaption: { color: theme.colors.textDim, fontSize: 10 },
  codeBody: { color: theme.colors.text, fontSize: 11, fontFamily: theme.typography.fontFamily.mono, lineHeight: 16 },
  refText: { color: theme.colors.textMuted, fontSize: 12, marginBottom: 4 },
  labHead: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12, backgroundColor: theme.colors.warning + '14', padding: 12, borderRadius: theme.radii.lg, borderWidth: 1, borderColor: theme.colors.warning + '44' },
  labTitle: { color: theme.colors.text, fontSize: 14, fontWeight: '800' },
  labMeta: { color: theme.colors.warning, fontSize: 10, fontWeight: '700', marginTop: 2 },
  compRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, paddingVertical: 8, borderTopWidth: 1, borderTopColor: theme.colors.border },
  compText: { color: theme.colors.text, fontSize: 13, lineHeight: 19, flex: 1 },
  glossRow: { paddingVertical: 8, borderTopWidth: 1, borderTopColor: theme.colors.border },
  glossHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  glossTerm: { color: theme.colors.primary, fontSize: 13, fontWeight: '800' },
  glossDef: { color: theme.colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 6, paddingLeft: 20 },
  rubricRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  rubricLabel: { color: theme.colors.text, fontSize: 11, fontWeight: '600', flex: 1, textTransform: 'capitalize' },
  rubricBar: { flex: 2, height: 6, backgroundColor: theme.colors.bgSubtle, borderRadius: theme.radii.full, overflow: 'hidden' },
  rubricFill: { height: '100%', backgroundColor: theme.colors.success, borderRadius: theme.radii.full },
  rubricPct: { color: theme.colors.textMuted, fontSize: 10, fontWeight: '700', minWidth: 30, textAlign: 'right' },
});
