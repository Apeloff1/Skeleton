/**
 * My Classes — enrolment + per-week progress + quiz + certificate.
 * Loads every enrolled class from classStore, fetches its detail from backend.
 */
import { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Modal, Pressable,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { api } from '../utils/apiController';
import {
  useEnrolmentsLive, setWeekStatus, saveQuiz, enrolClass, unenrolClass,
  isClassCompleted, classCompletionPercent,
} from '../utils/classStore';
import theme from '../theme/tokens';
import { Screen, AppHeader, Button, EmptyState, SectionHeader } from '../components/ui';
import { toast } from '../components/Toast';

export default function MyClassesScreen() {
  const router = useRouter();
  const { enrolments, progress, quizzes } = useEnrolmentsLive();
  const [catalog, setCatalog] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [quizState, setQuizState] = useState<any>(null);

  useEffect(() => {
    api.get<any>('/api/curriculum/classes', { tag: 'my-classes.list', cacheTtlMs: 5 * 60_000 }).then(d => {
      if (d?.classes) setCatalog(d.classes);
    }).catch(() => {});
  }, []);

  const openClass = useCallback(async (cls: any) => {
    try {
      const d = await api.get<any>(`/api/curriculum/classes/${cls.id}`, { tag: 'my-classes.detail', cacheTtlMs: 5 * 60_000 });
      setSelected(d);
    } catch {
      toast.error(`Could not load class ${cls.id}`);
    }
  }, []);

  const startQuiz = useCallback(async (classId: string, week: number) => {
    try {
      const d = await api.get<any>(`/api/curriculum/classes/${classId}/week/${week}/quiz`, { tag: 'my-classes.quiz', cacheTtlMs: 10 * 60_000 });
      setQuizState({ ...d, classId, answers: {} });
    } catch {
      toast.info('Could not load quiz right now.');
    }
  }, []);

  const submitQuiz = useCallback(async () => {
    if (!quizState) return;
    let score = 0;
    for (const q of quizState.questions) {
      if (quizState.answers[q.id] === q.correct_index) score++;
    }
    const total = quizState.questions.length;
    await saveQuiz(quizState.classId, quizState.week, score, total);
    if (score >= quizState.passing_score) {
      await setWeekStatus(quizState.classId, quizState.week, 'completed');
      toast.success(`Passed: ${score}/${total} — week complete & XP awarded`);
    } else {
      toast.warn(`Score ${score}/${total} — need ${quizState.passing_score} to pass`);
    }
    setQuizState(null);
  }, [quizState]);

  return (
    <Screen edges={['top']}>
      <LinearGradient
        colors={['#10B98122', '#3B82F622', 'transparent'] as any}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.9, y: 0.6 }}
        style={[s.aurora, { pointerEvents: 'none' }]}
      />

      <AppHeader title="My Classes" subtitle={`${enrolments.length} enrolled · ${catalog.length} available`} onBack={() => router.back()} />

      <ScrollView contentContainerStyle={s.scroll}>
        {/* 2026-05-15 — Quick links: Curriculum hub + Reading library */}
        <View style={{ flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingTop: 12 }}>
          <TouchableOpacity
            onPress={() => router.push('/curriculum' as any)}
            activeOpacity={0.8}
            style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
                     paddingVertical: 12, borderRadius: 10, backgroundColor: '#a78bfa22', borderWidth: 1, borderColor: '#a78bfa55' }}
          >
            <Ionicons name="grid-outline" size={16} color="#a78bfa" />
            <Text style={{ color: '#c4b5fd', fontSize: 12, fontWeight: '800' }}>Unified Curriculum</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => router.push('/readingLibrary' as any)}
            activeOpacity={0.8}
            style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
                     paddingVertical: 12, borderRadius: 10, backgroundColor: '#fcd34d22', borderWidth: 1, borderColor: '#fcd34d55' }}
          >
            <Ionicons name="library-outline" size={16} color="#fcd34d" />
            <Text style={{ color: '#fde68a', fontSize: 12, fontWeight: '800' }}>Reading Library</Text>
          </TouchableOpacity>
        </View>

        <SectionHeader label="Enrolled" count={enrolments.length} accentColor={theme.colors.success} />
        {enrolments.length === 0 ? (
          <EmptyState
            icon="school-outline"
            title="Start your first class"
            message="Pick from the catalog below to enrol — track week-by-week progress, take graded quizzes, and earn a verifiable certificate."
            accentColor={theme.colors.success}
          />
        ) : enrolments.map(en => {
          const cls = catalog.find(c => c.id === en.class_id) || {};
          const weeks = Number(cls.weeks_count || cls.weeks || 15);
          const prog = progress[en.class_id] || {};
          const pct = classCompletionPercent(weeks, prog);
          const completed = isClassCompleted(weeks, prog);
          const accent = completed ? theme.colors.warning : theme.colors.success;
          return (
            <View key={en.class_id} style={s.card}>
              <LinearGradient
                colors={[accent + '14', 'transparent'] as any}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
                style={[StyleSheet.absoluteFillObject, { pointerEvents: 'none' }]}
              />
              <Pressable style={s.cardHead} onPress={() => openClass({ id: en.class_id })}>
                <View style={[s.cardIcon, { backgroundColor: accent + '22', borderColor: accent + '44' }]}>
                  <Ionicons name={completed ? 'trophy' : 'school'} size={16} color={accent} />
                </View>
                <Text style={s.cardTitle} numberOfLines={1}>{en.title}</Text>
                {completed && (
                  <View style={[s.certPill, { backgroundColor: accent }]}>
                    <Text style={s.certPillText}>CERTIFIED</Text>
                  </View>
                )}
              </Pressable>
              <View style={s.progressTrack}>
                <View style={[s.progressFill, { width: `${pct}%`, backgroundColor: accent }]} />
              </View>
              <View style={s.cardRow}>
                <Text style={s.cardSub}>
                  {Object.values(prog).filter(p => p === 'completed').length} / {weeks} weeks · {pct}%
                </Text>
                <View style={{ flexDirection: 'row', gap: 6 }}>
                  {completed && (
                    <TouchableOpacity
                      style={[s.miniBtn, { backgroundColor: theme.colors.warning }]}
                      onPress={() => router.push(`/certificate?class=${en.class_id}&title=${encodeURIComponent(en.title)}` as any)}
                    >
                      <Ionicons name="ribbon" size={11} color="#1F1F1F" />
                      <Text style={[s.miniBtnText, { color: '#1F1F1F' }]}>Cert</Text>
                    </TouchableOpacity>
                  )}
                  <TouchableOpacity style={s.miniBtn} onPress={() => openClass({ id: en.class_id, title: en.title })}>
                    <Ionicons name="play" size={11} color="#fff" />
                    <Text style={s.miniBtnText}>Continue</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={s.miniBtnDanger} onPress={() => unenrolClass(en.class_id)} hitSlop={theme.hitSlop.sm}>
                    <Ionicons name="close" size={12} color={theme.colors.danger} />
                  </TouchableOpacity>
                </View>
              </View>
            </View>
          );
        })}

        <SectionHeader label="Catalog" count={catalog.length} accentColor={theme.colors.info} style={{ marginTop: theme.spacing.lg }} />
        {catalog.map(cls => {
          const isEnrolled = enrolments.find(e => e.class_id === cls.id);
          return (
            <View key={cls.id} style={s.card}>
              <View style={s.cardHead}>
                <View style={[s.cardIcon, { backgroundColor: theme.colors.info + '22', borderColor: theme.colors.info + '44' }]}>
                  <Ionicons name="library" size={14} color={theme.colors.info} />
                </View>
                <Text style={s.cardTitle} numberOfLines={1}>{cls.title}</Text>
              </View>
              {cls.description ? <Text style={s.cardDesc} numberOfLines={2}>{cls.description}</Text> : null}
              <View style={s.cardRow}>
                <Text style={s.cardSub}>{cls.weeks_count || cls.weeks || '?'} weeks · {cls.code || cls.level || ''}</Text>
                <TouchableOpacity
                  style={isEnrolled ? s.miniBtnDanger : s.miniBtn}
                  onPress={() => isEnrolled ? unenrolClass(cls.id) : enrolClass(cls.id, cls.title)}
                >
                  <Ionicons name={isEnrolled ? 'remove-circle' : 'add-circle'} size={11} color={isEnrolled ? theme.colors.danger : '#fff'} />
                  <Text style={[s.miniBtnText, isEnrolled && { color: theme.colors.danger }]}>
                    {isEnrolled ? 'Unenrol' : 'Enrol'}
                  </Text>
                </TouchableOpacity>
              </View>
            </View>
          );
        })}
      </ScrollView>

      {/* Class detail modal */}
      <Modal visible={!!selected} animationType="slide" transparent onRequestClose={() => setSelected(null)}>
        <View style={s.modalOverlay}>
          <View style={s.modalCard}>
            <View style={s.modalHdr}>
              <Text style={s.modalTitle} numberOfLines={1}>{selected?.title || selected?.id}</Text>
              <TouchableOpacity onPress={() => setSelected(null)} hitSlop={theme.hitSlop.md}>
                <Ionicons name="close" size={22} color={theme.colors.textMuted} />
              </TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={{ padding: theme.spacing.base }}>
              {(selected?.weeks || []).map((w: any, i: number) => {
                const status = (progress[selected?.id] || {})[w.week];
                const score = (quizzes[selected?.id] || {})[w.week];
                const statusColor =
                  status === 'completed' ? theme.colors.success :
                  status === 'started'   ? theme.colors.warning :
                  theme.colors.borderStrong;
                return (
                  <View key={w.week || i} style={s.weekRow}>
                    <TouchableOpacity
                      style={{ flex: 1 }}
                      onPress={() => router.push({ pathname: '/class-week' as any, params: { classId: selected.id, week: String(w.week), classTitle: selected.title || '' } })}
                      activeOpacity={0.7}
                    >
                      <Text style={s.weekTitle}>Week {w.week}: {w.title}</Text>
                      {score && <Text style={s.scoreText}>Quiz: {score.score}/{score.total}</Text>}
                      <Text style={[s.scoreText, { color: theme.colors.info }]}>Tap to read · lab · practice</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={s.weekQuizBtn} onPress={() => startQuiz(selected.id, w.week)}>
                      <Ionicons name="help-circle" size={13} color={theme.colors.warning} />
                      <Text style={s.weekQuizText}>Quiz</Text>
                    </TouchableOpacity>
                    <View style={[s.statusDot, { backgroundColor: statusColor }]} />
                  </View>
                );
              })}
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* Quiz modal */}
      <Modal visible={!!quizState} animationType="slide" transparent onRequestClose={() => setQuizState(null)}>
        <View style={s.modalOverlay}>
          <View style={s.modalCard}>
            <View style={s.modalHdr}>
              <Text style={s.modalTitle}>Quiz · Week {quizState?.week}</Text>
              <TouchableOpacity onPress={() => setQuizState(null)} hitSlop={theme.hitSlop.md}>
                <Ionicons name="close" size={22} color={theme.colors.textMuted} />
              </TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={{ padding: theme.spacing.base }}>
              {(quizState?.questions || []).map((q: any, qi: number) => (
                <View key={q.id} style={s.qBlock}>
                  <Text style={s.qPrompt}>{qi + 1}. {q.prompt}</Text>
                  {q.options.map((opt: string, oi: number) => {
                    const selectedAns = quizState.answers[q.id] === oi;
                    return (
                      <TouchableOpacity
                        key={oi}
                        style={[s.qOption, selectedAns && s.qOptionActive]}
                        onPress={() => setQuizState({ ...quizState, answers: { ...quizState.answers, [q.id]: oi } })}
                      >
                        <View style={[s.radio, selectedAns && s.radioActive]} />
                        <Text style={s.qOptionText}>{opt}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              ))}
              <Button
                label="Submit quiz"
                icon="checkmark"
                onPress={submitQuiz}
                variant="gradient"
                gradient="emerald"
                fullWidth
                size="lg"
                style={{ marginTop: theme.spacing.sm }}
              />
            </ScrollView>
          </View>
        </View>
      </Modal>
    </Screen>
  );
}

const s = StyleSheet.create({
  aurora: { position: 'absolute', top: 0, left: 0, right: 0, height: 240 },
  scroll: { padding: theme.spacing.base, paddingBottom: theme.spacing['3xl'] },
  section: {
    color: theme.colors.textMuted,
    fontSize: 11, fontWeight: '800',
    textTransform: 'uppercase', letterSpacing: 0.8,
    marginBottom: theme.spacing.sm, marginTop: theme.spacing.xs,
  },
  empty: {
    alignItems: 'center', paddingVertical: theme.spacing['2xl'],
    gap: theme.spacing.xs,
  },
  emptyText: { ...theme.typography.h4, color: theme.colors.text },
  emptySub: { ...theme.typography.caption, color: theme.colors.textMuted, fontWeight: '500' },
  card: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
    overflow: 'hidden',
    ...theme.elevation.xs,
  },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: theme.spacing.sm },
  cardIcon: {
    width: 32, height: 32,
    borderRadius: theme.radii.sm,
    borderWidth: 1,
    justifyContent: 'center', alignItems: 'center',
  },
  cardTitle: { color: theme.colors.text, ...theme.typography.h4, fontSize: 14, flex: 1 },
  cardDesc: { color: theme.colors.textMuted, fontSize: 12, marginTop: 6, lineHeight: 16 },
  cardRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: theme.spacing.sm },
  cardSub: { color: theme.colors.textMuted, fontSize: 11, fontWeight: '600' },
  progressTrack: {
    height: 6, backgroundColor: theme.colors.bgSubtle,
    borderRadius: theme.radii.full, overflow: 'hidden', marginTop: theme.spacing.sm,
  },
  progressFill: { height: '100%', borderRadius: theme.radii.full },
  miniBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    backgroundColor: theme.colors.primary,
    borderRadius: theme.radii.md,
    paddingHorizontal: 12, paddingVertical: 9,
    minHeight: 36,
  },
  miniBtnDanger: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    borderWidth: 1, borderColor: theme.colors.danger + '66',
    borderRadius: theme.radii.md,
    paddingHorizontal: 10, paddingVertical: 9,
    minHeight: 36, minWidth: 36, justifyContent: 'center',
  },
  miniBtnText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  certPill: {
    borderRadius: theme.radii.full,
    paddingHorizontal: 8, paddingVertical: 3,
  },
  certPillText: { color: '#1F1F1F', fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
  modalOverlay: { flex: 1, backgroundColor: theme.colors.overlay, justifyContent: 'flex-end' },
  modalCard: {
    backgroundColor: theme.colors.bgElevated,
    borderTopLeftRadius: theme.radii.xl,
    borderTopRightRadius: theme.radii.xl,
    maxHeight: '90%',
    borderWidth: 1, borderColor: theme.colors.border,
  },
  modalHdr: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    padding: theme.spacing.base,
    borderBottomWidth: 1, borderBottomColor: theme.colors.border,
  },
  modalTitle: { color: theme.colors.text, ...theme.typography.h3, flex: 1, marginRight: theme.spacing.sm },
  weekRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.md,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.xs,
    gap: theme.spacing.sm,
    borderWidth: 1, borderColor: theme.colors.border,
  },
  weekTitle: { color: theme.colors.text, fontSize: 13, fontWeight: '700' },
  scoreText: { color: theme.colors.success, fontSize: 10, marginTop: 2, fontWeight: '700' },
  weekQuizBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: 'transparent',
    borderWidth: 1, borderColor: theme.colors.warning + '88',
    borderRadius: theme.radii.sm,
    paddingHorizontal: 8, paddingVertical: 5,
  },
  weekQuizText: { color: theme.colors.warning, fontSize: 10, fontWeight: '700' },
  statusDot: { width: 10, height: 10, borderRadius: 5 },
  qBlock: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.sm,
    borderWidth: 1, borderColor: theme.colors.border,
  },
  qPrompt: { color: theme.colors.text, fontSize: 13, fontWeight: '700', marginBottom: theme.spacing.sm },
  qOption: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: theme.colors.bgSubtle,
    borderRadius: theme.radii.sm,
    padding: theme.spacing.sm,
    marginBottom: 6,
    borderWidth: 1, borderColor: theme.colors.border,
    gap: 10,
  },
  qOptionActive: { borderColor: theme.colors.primary, backgroundColor: theme.colors.primarySoft },
  qOptionText: { color: theme.colors.text, fontSize: 12, flex: 1 },
  radio: {
    width: 16, height: 16, borderRadius: 8,
    borderWidth: 2, borderColor: theme.colors.borderStrong,
  },
  radioActive: { borderColor: theme.colors.primary, backgroundColor: theme.colors.primary },
});
