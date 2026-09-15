/**
 * Flashcards — spaced-repetition deck built from any class's glossary terms.
 * Pick a class → backend serves the glossary → app converts to flip cards.
 * Self-grade Easy/Medium/Hard → advances or repeats card.
 */
import { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { api } from '../utils/apiController';
import { bumpStat } from '../utils/userStore';
import { openModalFromRoute } from '../utils/openModalFromRoute';
import theme from '../theme/tokens';
import { Screen, AppHeader } from '../components/ui';

interface Card { id: string; term: string; definition: string; }

export default function FlashcardsScreen() {
  const router = useRouter();
  const [catalog, setCatalog] = useState<any[]>([]);
  const [selectedClass, setSelectedClass] = useState<string | null>(null);
  const [cards, setCards] = useState<Card[]>([]);
  const [idx, setIdx] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<{ id: string; grade: 'easy'|'med'|'hard' }[]>([]);

  useEffect(() => {
    api.get<any>('/api/curriculum/classes', { tag: 'curriculum.classes', cacheTtlMs: 5 * 60_000 }).catch(() => null).then(d => {
      if (d?.classes) setCatalog(d.classes);
    });
  }, []);

  const pickClass = useCallback(async (cls: any) => {
    setLoading(true);
    setSelectedClass(cls.id);
    setIdx(0); setFlipped(false); setHistory([]);
    try {
      // Pull all 15 weeks; each week may have a glossary in the deep generator output
      const promises = Array.from({ length: 15 }, (_, i) =>
        api.get<any>(`/api/curriculum/classes/${cls.id}/week/${i + 1}`, { tag: 'curriculum.week', cacheTtlMs: 10 * 60_000 })
          .catch(() => null)
      );
      const weeks = await Promise.all(promises);
      const all: Card[] = [];
      let cardIdx = 0;
      weeks.forEach((w: any, wi: number) => {
        if (!w) return;
        const topics: string[] = w.topics || [];
        const objectives: string[] = w.learning_objectives || [];
        // Build a card per topic — term=topic, definition=first matching objective or generated stub
        topics.forEach((t, ti) => {
          const obj = objectives.find((o: string) => o.toLowerCase().includes(t.toLowerCase().slice(0, 10)));
          all.push({
            id: `c_${wi}_${ti}_${cardIdx++}`,
            term: t,
            definition: obj || `From week ${w.week} — ${w.title}. Tap to recall the key idea from this week's coverage of ${t}.`,
          });
        });
      });
      // Shuffle deterministically by class id
      const seed = cls.id.split('').reduce((a: number, c: string) => a + c.charCodeAt(0), 0);
      const rng = (n: number) => ((seed * 9301 + n * 49297) % 233280) / 233280;
      const shuffled = all.map((c, i) => ({ c, r: rng(i) })).sort((a, b) => a.r - b.r).map(x => x.c);
      setCards(shuffled.slice(0, 40)); // cap at 40 to keep session short
    } catch {
      setCards([]);
    }
    setLoading(false);
  }, []);

  const grade = useCallback((g: 'easy'|'med'|'hard') => {
    if (!cards.length) return;
    setHistory(h => [...h, { id: cards[idx].id, grade: g }]);
    bumpStat('classes_weeks_completed', 0, g === 'easy' ? 5 : g === 'med' ? 3 : 1);
    setFlipped(false);
    if (g === 'hard') {
      // Push current card to end of deck
      setCards(prev => {
        const c = prev[idx];
        return [...prev.slice(0, idx), ...prev.slice(idx + 1), c];
      });
    } else {
      setIdx(i => Math.min(i + 1, cards.length));
    }
  }, [cards, idx]);

  const reset = () => { setSelectedClass(null); setCards([]); setIdx(0); setFlipped(false); setHistory([]); };

  // P3 — Review only the cards that were graded "hard" during this session.
  const reviewHardOnly = () => {
    const hardIds = new Set(history.filter(h => h.grade === 'hard').map(h => h.id));
    const hardCards = cards.filter(c => hardIds.has(c.id));
    if (hardCards.length === 0) return;
    setCards(hardCards);
    setIdx(0); setFlipped(false); setHistory([]);
  };

  return (
    <Screen edges={['top']}>
      <LinearGradient
        colors={['#8B5CF622', '#3B82F622', 'transparent'] as any}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.9, y: 0.6 }}
        style={[{ position: 'absolute', top: 0, left: 0, right: 0, height: 240 }, { pointerEvents: 'none' }]}
      />
      <AppHeader title="Flashcards" onBack={() => router.back()} />

      {!selectedClass ? (
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 80 }}>
          <Text style={s.intro}>Pick a class to study. Cards are drawn from every week&apos;s topics and shuffled.</Text>
          {catalog.map(cls => (
            <TouchableOpacity key={cls.id} style={s.classRow} onPress={() => pickClass(cls)} activeOpacity={0.7}>
              <Ionicons name="school" size={18} color="#10B981" />
              <Text style={s.classTitle}>{cls.title}</Text>
              <Ionicons name="chevron-forward" size={18} color="#475569" />
            </TouchableOpacity>
          ))}
        </ScrollView>
      ) : loading ? (
        <View style={s.loading}><ActivityIndicator color="#8B5CF6" size="large" /><Text style={s.loadingText}>Building your deck…</Text></View>
      ) : idx >= cards.length ? (
        <View style={s.done}>
          <Ionicons name="trophy" size={48} color="#F5C451" />
          <Text style={s.doneTitle}>Deck complete</Text>
          <Text style={s.doneSub}>{history.filter(h => h.grade === 'easy').length} easy · {history.filter(h => h.grade === 'med').length} medium · {history.filter(h => h.grade === 'hard').length} hard</Text>
          {history.some(h => h.grade === 'hard') && (
            <TouchableOpacity style={[s.resetBtn, { backgroundColor: '#EF4444', marginTop: 16 }]} onPress={reviewHardOnly}>
              <Text style={s.resetBtnText}>Review hard cards only ({history.filter(h => h.grade === 'hard').length})</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity style={s.resetBtn} onPress={reset}>
            <Text style={s.resetBtnText}>Pick another class</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.resetBtn, { backgroundColor: '#8B5CF6', marginTop: 10 }]}
            onPress={() => openModalFromRoute(router, 'interactiveQuizzes')}
            activeOpacity={0.85}
          >
            <Text style={s.resetBtnText}>Take a graded quiz →</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <View style={s.deckWrap}>
          <Text style={s.deckProgress}>{idx + 1} of {cards.length}</Text>
          <TouchableOpacity activeOpacity={0.85} onPress={() => setFlipped(f => !f)} style={[s.card, flipped && s.cardFlipped]}>
            <Ionicons name={flipped ? 'eye' : 'eye-off'} size={20} color={flipped ? '#10B981' : '#8B5CF6'} />
            <Text style={s.cardSide}>{flipped ? 'DEFINITION' : 'TERM'}</Text>
            <Text style={s.cardBody}>{flipped ? cards[idx].definition : cards[idx].term}</Text>
            {!flipped && <Text style={s.hint}>Tap to reveal</Text>}
          </TouchableOpacity>
          {flipped && (
            <View style={s.gradeRow}>
              <TouchableOpacity style={[s.gradeBtn, { backgroundColor: '#EF4444' }]} onPress={() => grade('hard')}>
                <Text style={s.gradeText}>Again</Text>
                <Text style={s.gradeSub}>Hard</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[s.gradeBtn, { backgroundColor: '#F59E0B' }]} onPress={() => grade('med')}>
                <Text style={s.gradeText}>Good</Text>
                <Text style={s.gradeSub}>Med</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[s.gradeBtn, { backgroundColor: '#10B981' }]} onPress={() => grade('easy')}>
                <Text style={s.gradeText}>Easy</Text>
                <Text style={s.gradeSub}>+5 XP</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      )}
    </Screen>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.bg },
  header: { flexDirection: 'row', alignItems: 'center', padding: 14, backgroundColor: theme.colors.bgElevated, borderBottomWidth: 1, borderBottomColor: theme.colors.border },
  hdrBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  hdrTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700', color: theme.colors.text },
  intro: { color: theme.colors.textMuted, fontSize: 13, marginBottom: theme.spacing.base, fontStyle: 'italic', lineHeight: 19 },
  classRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: theme.colors.surface, borderRadius: theme.radii.lg, padding: theme.spacing.md, marginBottom: theme.spacing.xs, gap: theme.spacing.sm, borderWidth: 1, borderColor: theme.colors.border, minHeight: 52 },
  classTitle: { color: theme.colors.text, fontSize: 14, fontWeight: '700', flex: 1 },
  loading: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { color: theme.colors.textMuted, fontSize: 12, marginTop: theme.spacing.sm },
  done: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: theme.spacing.lg },
  doneTitle: { color: theme.colors.text, ...theme.typography.h1, marginTop: theme.spacing.base },
  doneSub: { color: theme.colors.textMuted, fontSize: 12, marginTop: 6, fontWeight: '600' },
  resetBtn: { backgroundColor: theme.colors.primary, borderRadius: theme.radii.md, paddingHorizontal: theme.spacing.lg, paddingVertical: theme.spacing.md, marginTop: 30, ...theme.elevation.glow },
  resetBtnText: { color: '#fff', fontSize: 14, fontWeight: '800' },
  deckWrap: { flex: 1, padding: theme.spacing.lg, justifyContent: 'center' },
  deckProgress: { color: theme.colors.textMuted, fontSize: 12, textAlign: 'center', marginBottom: theme.spacing.base, fontWeight: '700', letterSpacing: 0.5 },
  card: { backgroundColor: theme.colors.surface, borderRadius: theme.radii.xl, padding: 30, minHeight: 280, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: theme.colors.border, ...theme.elevation.md },
  cardFlipped: { backgroundColor: theme.colors.success + '14', borderColor: theme.colors.success },
  cardSide: { color: theme.colors.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 2, marginTop: 10, marginBottom: 16 },
  cardBody: { color: theme.colors.text, fontSize: 19, textAlign: 'center', fontWeight: '700', lineHeight: 27 },
  hint: { color: theme.colors.textDim, fontSize: 11, marginTop: 20, fontStyle: 'italic' },
  gradeRow: { flexDirection: 'row', gap: theme.spacing.sm, marginTop: theme.spacing.lg },
  gradeBtn: { flex: 1, alignItems: 'center', paddingVertical: 16, borderRadius: theme.radii.md },
  gradeText: { color: '#fff', fontSize: 14, fontWeight: '800' },
  gradeSub: { color: '#ffffffCC', fontSize: 10, marginTop: 2, fontWeight: '700' },
});
