import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE } from '../../utils/apiBase';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, Modal,
  ActivityIndicator, SafeAreaView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Animated, {
  useSharedValue, useAnimatedStyle, withTiming, withSequence,
} from 'react-native-reanimated';
import * as haptics from '../../utils/haptics';
import { toast } from '../../components/Toast';
import { apiFetch } from '../../utils/apiController';
const API_URL = API_BASE;

const DOMAIN_COLORS: Record<string, string> = {
  cs_fundamentals: '#3B82F6',
  os_systems: '#8B5CF6',
  networking: '#2563EB',
  databases: '#10B981',
  security: '#EF4444',
  game_dev: '#F59E0B',
  ml_ai: '#EC4899',
  web_dev: '#3B82F6',
  physics_gamedev: '#6366F1',
  rendering_graphics: '#F97316',
};

const DOMAIN_LABELS: Record<string, string> = {
  cs_fundamentals: 'CS Fundamentals',
  os_systems: 'Operating Systems',
  networking: 'Networking',
  databases: 'Databases',
  security: 'Security',
  game_dev: 'Game Dev',
  ml_ai: 'ML & AI',
  web_dev: 'Web Dev',
  physics_gamedev: 'Physics (GameDev)',
  rendering_graphics: 'Rendering & Graphics',
};

const DIFF_COLORS: Record<string, string> = {
  beginner: '#10B981',
  intermediate: '#3B82F6',
  advanced: '#F59E0B',
  expert: '#EF4444',
  master: '#8B5CF6',
};

interface Props {
  visible: boolean;
  onClose: () => void;
}

export const InteractiveQuizzesModal: React.FC<Props> = ({ visible, onClose }) => {
  const [domains, setDomains] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<'domains' | 'quiz'>('domains');
  const [quizzes, setQuizzes] = useState<any[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [score, setScore] = useState(0);
  const [total, setTotal] = useState(0);
  const [sessionDomain, setSessionDomain] = useState<string | null>(null);
  const [sessionDifficulty, setSessionDifficulty] = useState<string | null>(null);
  const [grandTotal, setGrandTotal] = useState(0);
  // Reanimated shared value driving the cross-fade between questions.
  // Reduce-Motion clamps the duration to 0 so transitions are instant.
  const fadeAnim = useSharedValue(1);
  const fadeStyle = useAnimatedStyle(() => ({ opacity: fadeAnim.value }));

  const fetchDomains = useCallback(async () => {
    try {
      setLoading(true);
      const res = await apiFetch(`${API_URL}/api/academy/quizzes/domains`);
      const data = await res.json();
      setDomains(data.domains || []);
      setGrandTotal(data.grand_total || 0);
    } catch (e) {
      console.error('Failed to fetch quiz domains:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  const startQuizSession = useCallback(async (domain?: string, difficulty?: string) => {
    try {
      setLoading(true);
      let url = `${API_URL}/api/academy/quizzes/random?count=20`;
      if (domain) url += `&domain=${domain}`;
      if (difficulty) url += `&difficulty=${difficulty}`;
      const res = await apiFetch(url);
      const data = await res.json();
      setQuizzes(data.quizzes || []);
      setCurrentIdx(0);
      setScore(0);
      setTotal(0);
      setSelectedAnswer(null);
      setResult(null);
      setSessionDomain(domain || null);
      setSessionDifficulty(difficulty || null);
      setView('quiz');
    } catch (e) {
      console.error('Failed to start quiz session:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  const checkAnswer = useCallback(async (quizId: string, answer: string) => {
    setSelectedAnswer(answer);
    haptics.tap();
    try {
      const res = await apiFetch(`${API_URL}/api/academy/quiz/${quizId}/answer?answer=${encodeURIComponent(answer)}`, { method: 'POST' });
      const data = await res.json();
      setResult(data);
      setTotal((t) => t + 1);
      if (data.is_correct) {
        setScore((s) => s + (data.points_earned || 10));
        haptics.success();
        toast.success(`+${data.points_earned || 10} XP · keep going`);
      } else {
        haptics.error();
        toast.warn('Not quite · check the explanation below');
      }
    } catch (e) {
      console.error('Failed to check answer:', e);
      toast.error('Could not check answer · retry');
    }
  }, []);

  const nextQuestion = useCallback(() => {
    haptics.tap();
    const dur = haptics.isReduceMotionOn() ? 0 : 150;
    fadeAnim.value = withSequence(
      withTiming(0, { duration: dur }),
      withTiming(1, { duration: dur }),
    );
    setSelectedAnswer(null);
    setResult(null);
    setCurrentIdx((i) => i + 1);
  }, [fadeAnim]);

  useEffect(() => {
    if (visible) fetchDomains();
  }, [visible, fetchDomains]);

  const handleBack = () => {
    if (view === 'quiz') {
      setView('domains');
      setQuizzes([]);
    } else {
      onClose();
    }
  };

  const currentQuiz = quizzes[currentIdx];
  const isFinished = currentIdx >= quizzes.length && quizzes.length > 0;

  const renderDomains = () => (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
      <View style={styles.heroCard}>
        <Ionicons name="bulb" size={40} color="#F59E0B" />
        <Text style={styles.heroTitle}>10,000 Interactive Quizzes</Text>
        <Text style={styles.heroSub}>Test your knowledge across every domain</Text>
        <TouchableOpacity testID="start-random-quiz-btn" style={styles.heroBtn} onPress={() => startQuizSession()}>
          <Ionicons name="shuffle" size={18} color="#FFF" />
          <Text style={styles.heroBtnText}>Random Challenge (20 questions)</Text>
        </TouchableOpacity>
      </View>
      <Text style={styles.sectionTitle}>{grandTotal.toLocaleString()} QUIZZES ACROSS {domains.length} DOMAINS</Text>
      {domains.map((d) => {
        const color = DOMAIN_COLORS[d.domain] || '#888';
        const label = DOMAIN_LABELS[d.domain] || d.domain;
        const dist = d.difficulty_distribution || {};
        return (
          <TouchableOpacity
            key={d.domain}
            testID={`quiz-domain-${d.domain}`}
            style={[styles.domainCard, { borderLeftColor: color }]}
            onPress={() => startQuizSession(d.domain)}
          >
            <View style={styles.domainTop}>
              <Text style={[styles.domainName, { color }]}>{label}</Text>
              <Text style={styles.domainCount}>{d.total_quizzes.toLocaleString()}</Text>
            </View>
            <View style={styles.diffRow}>
              {Object.entries(dist).map(([diff, count]) => (
                <View key={diff} style={[styles.diffBadge, { backgroundColor: (DIFF_COLORS[diff] || '#888') + '25' }]}>
                  <View style={[styles.diffDot, { backgroundColor: DIFF_COLORS[diff] || '#888' }]} />
                  <Text style={[styles.diffText, { color: DIFF_COLORS[diff] || '#888' }]}>
                    {diff.charAt(0).toUpperCase() + diff.slice(1)}: {String(count)}
                  </Text>
                </View>
              ))}
            </View>
          </TouchableOpacity>
        );
      })}
    </ScrollView>
  );

  const renderQuiz = () => {
    if (isFinished) {
      const pct = total > 0 ? Math.round((score / (total * 50)) * 100) : 0;
      return (
        <View style={styles.finishedContainer}>
          <Ionicons name={pct >= 70 ? 'trophy' : 'ribbon'} size={64} color={pct >= 70 ? '#F59E0B' : '#94A3B8'} />
          <Text style={styles.finishedTitle}>{pct >= 70 ? 'Excellent!' : 'Keep Learning!'}</Text>
          <Text style={styles.finishedScore}>Score: {score} points</Text>
          <Text style={styles.finishedStat}>{total} questions answered</Text>
          <TouchableOpacity testID="quiz-retry-btn" style={styles.retryBtn} onPress={() => startQuizSession(sessionDomain || undefined, sessionDifficulty || undefined)}>
            <Ionicons name="refresh" size={18} color="#FFF" />
            <Text style={styles.retryBtnText}>Try Again</Text>
          </TouchableOpacity>
          <TouchableOpacity testID="quiz-back-btn" style={[styles.retryBtn, { backgroundColor: '#334155' }]} onPress={() => setView('domains')}>
            <Text style={styles.retryBtnText}>Back to Domains</Text>
          </TouchableOpacity>
        </View>
      );
    }

    if (!currentQuiz) return null;
    const diffColor = DIFF_COLORS[currentQuiz.difficulty] || '#888';

    return (
      <Animated.View style={[styles.quizContainer, fadeStyle]}>
        <View style={styles.quizHeader}>
          <Text style={styles.quizProgress}>Question {currentIdx + 1} / {quizzes.length}</Text>
          <View style={styles.scoreChip}>
            <Ionicons name="star" size={14} color="#F59E0B" />
            <Text style={styles.scoreText}>{score}</Text>
          </View>
        </View>
        <View style={styles.progressBarBg}>
          <View style={[styles.progressBarFill, { width: `${((currentIdx) / quizzes.length) * 100}%` }]} />
        </View>
        <View style={styles.quizMeta}>
          <View style={[styles.diffBadge, { backgroundColor: diffColor + '25' }]}>
            <View style={[styles.diffDot, { backgroundColor: diffColor }]} />
            <Text style={[styles.diffText, { color: diffColor }]}>{currentQuiz.difficulty}</Text>
          </View>
          <Text style={styles.quizDomain}>{DOMAIN_LABELS[currentQuiz.domain] || currentQuiz.domain}</Text>
          {currentQuiz.time_limit_seconds && (
            <View style={styles.timeBadge}>
              <Ionicons name="time" size={12} color="#94A3B8" />
              <Text style={styles.timeText}>{currentQuiz.time_limit_seconds}s</Text>
            </View>
          )}
        </View>
        <ScrollView style={styles.quizBody} showsVerticalScrollIndicator={false}>
          <Text style={styles.questionText}>{currentQuiz.question}</Text>
          {(currentQuiz.options || []).map((opt: string, i: number) => {
            let optStyle = styles.optionBtn;
            let textColor = '#E2E8F0';
            if (result && selectedAnswer) {
              if (opt === result.correct_answer) {
                optStyle = { ...styles.optionBtn, ...styles.optionCorrect };
                textColor = '#10B981';
              } else if (opt === selectedAnswer && !result.is_correct) {
                optStyle = { ...styles.optionBtn, ...styles.optionWrong };
                textColor = '#EF4444';
              }
            } else if (selectedAnswer === opt) {
              optStyle = { ...styles.optionBtn, ...styles.optionSelected };
            }
            return (
              <TouchableOpacity
                key={i}
                testID={`quiz-option-${i}`}
                style={optStyle}
                onPress={() => !result && checkAnswer(currentQuiz.id, opt)}
                disabled={!!result}
              >
                <View style={styles.optionLetter}>
                  <Text style={styles.optionLetterText}>{String.fromCharCode(65 + i)}</Text>
                </View>
                <Text style={[styles.optionText, { color: textColor }]}>{opt}</Text>
                {result && opt === result.correct_answer && (
                  <Ionicons name="checkmark-circle" size={22} color="#10B981" />
                )}
                {result && opt === selectedAnswer && !result.is_correct && opt !== result.correct_answer && (
                  <Ionicons name="close-circle" size={22} color="#EF4444" />
                )}
              </TouchableOpacity>
            );
          })}
          {result && (
            <View style={styles.explanationBox}>
              <Text style={styles.explanationTitle}>
                {result.is_correct ? '✅ Correct!' : '❌ Not quite'}
              </Text>
              <Text style={styles.explanationText}>{result.explanation}</Text>
              {result.hints && result.hints.length > 0 && !result.is_correct && (
                <View style={styles.hintsBox}>
                  <Text style={styles.hintLabel}>Hints:</Text>
                  {result.hints.map((h: string, i: number) => (
                    <Text key={i} style={styles.hintText}>• {h}</Text>
                  ))}
                </View>
              )}
            </View>
          )}
          {result && (
            <TouchableOpacity testID="quiz-next-btn" style={styles.nextBtn} onPress={nextQuestion}>
              <Text style={styles.nextBtnText}>{currentIdx + 1 >= quizzes.length ? 'See Results' : 'Next Question'}</Text>
              <Ionicons name="arrow-forward" size={18} color="#FFF" />
            </TouchableOpacity>
          )}
          <View style={{ height: 40 }} />
        </ScrollView>
      </Animated.View>
    );
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={handleBack}>
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity testID="quiz-close-btn" onPress={handleBack} style={styles.headerBtn}>
            <Ionicons name={view === 'quiz' ? 'arrow-back' : 'close'} size={24} color="#F8FAFC" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>
            {view === 'quiz' ? (sessionDomain ? DOMAIN_LABELS[sessionDomain] || 'Quiz' : 'Random Challenge') : 'Interactive Quizzes'}
          </Text>
          <View style={{ width: 44 }} />
        </View>
        {loading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color="#F59E0B" />
            <Text style={styles.loadingText}>Loading quizzes...</Text>
          </View>
        ) : view === 'quiz' ? renderQuiz() : renderDomains()}
      </SafeAreaView>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F172A' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, backgroundColor: '#1E293B', borderBottomWidth: 1, borderBottomColor: '#334155' },
  headerBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { flex: 1, fontSize: 18, fontWeight: '700', color: '#F8FAFC', textAlign: 'center' },
  content: { flex: 1, paddingHorizontal: 16 },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { color: '#94A3B8', marginTop: 12 },
  heroCard: { alignItems: 'center', padding: 28, backgroundColor: '#1E293B', borderRadius: 16, marginTop: 16, borderWidth: 1, borderColor: '#F59E0B30' },
  heroTitle: { fontSize: 22, fontWeight: '800', color: '#F8FAFC', marginTop: 12 },
  heroSub: { fontSize: 14, color: '#94A3B8', marginTop: 4 },
  heroBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#F59E0B', paddingHorizontal: 20, paddingVertical: 12, borderRadius: 10, marginTop: 16 },
  heroBtnText: { fontSize: 14, fontWeight: '700', color: '#FFF' },
  sectionTitle: { fontSize: 12, fontWeight: '700', color: '#64748B', letterSpacing: 1, marginTop: 24, marginBottom: 12 },
  domainCard: { padding: 16, backgroundColor: '#1E293B', borderRadius: 12, marginBottom: 10, borderLeftWidth: 4 },
  domainTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  domainName: { fontSize: 16, fontWeight: '700' },
  domainCount: { fontSize: 14, fontWeight: '600', color: '#94A3B8' },
  diffRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 },
  diffBadge: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 },
  diffDot: { width: 6, height: 6, borderRadius: 3, marginRight: 5 },
  diffText: { fontSize: 11, fontWeight: '600' },
  quizContainer: { flex: 1, paddingHorizontal: 16 },
  quizHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 12 },
  quizProgress: { fontSize: 14, fontWeight: '600', color: '#94A3B8' },
  scoreChip: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#F59E0B20', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  scoreText: { fontSize: 14, fontWeight: '700', color: '#F59E0B' },
  progressBarBg: { height: 4, backgroundColor: '#334155', borderRadius: 2, marginTop: 8 },
  progressBarFill: { height: 4, backgroundColor: '#3B82F6', borderRadius: 2 },
  quizMeta: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 12 },
  quizDomain: { fontSize: 12, color: '#94A3B8' },
  timeBadge: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  timeText: { fontSize: 11, color: '#94A3B8' },
  quizBody: { flex: 1, marginTop: 16 },
  questionText: { fontSize: 20, fontWeight: '700', color: '#F8FAFC', lineHeight: 28, marginBottom: 20 },
  optionBtn: { flexDirection: 'row', alignItems: 'center', padding: 16, backgroundColor: '#1E293B', borderRadius: 12, marginBottom: 10, borderWidth: 1, borderColor: '#334155', minHeight: 56, gap: 12 },
  optionSelected: { borderColor: '#3B82F6', backgroundColor: '#3B82F620' },
  optionCorrect: { borderColor: '#10B981', backgroundColor: '#10B98120' },
  optionWrong: { borderColor: '#EF4444', backgroundColor: '#EF444420' },
  optionLetter: { width: 32, height: 32, borderRadius: 8, backgroundColor: '#334155', justifyContent: 'center', alignItems: 'center', flexShrink: 0 },
  optionLetterText: { fontSize: 14, fontWeight: '700', color: '#94A3B8' },
  optionText: { flex: 1, fontSize: 15, fontWeight: '500', flexShrink: 1, lineHeight: 21 },
  explanationBox: { padding: 16, backgroundColor: '#1E293B', borderRadius: 12, marginTop: 8, borderWidth: 1, borderColor: '#334155' },
  explanationTitle: { fontSize: 16, fontWeight: '700', color: '#F8FAFC' },
  explanationText: { fontSize: 13, color: '#CBD5E1', marginTop: 6, lineHeight: 20 },
  hintsBox: { marginTop: 10 },
  hintLabel: { fontSize: 12, fontWeight: '700', color: '#F59E0B' },
  hintText: { fontSize: 12, color: '#94A3B8', marginTop: 3 },
  nextBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#3B82F6', paddingVertical: 14, borderRadius: 12, marginTop: 16 },
  nextBtnText: { fontSize: 16, fontWeight: '700', color: '#FFF' },
  finishedContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 32 },
  finishedTitle: { fontSize: 28, fontWeight: '800', color: '#F8FAFC', marginTop: 16 },
  finishedScore: { fontSize: 20, fontWeight: '700', color: '#F59E0B', marginTop: 8 },
  finishedStat: { fontSize: 14, color: '#94A3B8', marginTop: 4 },
  retryBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#3B82F6', paddingVertical: 14, paddingHorizontal: 32, borderRadius: 12, marginTop: 16, width: '100%' },
  retryBtnText: { fontSize: 16, fontWeight: '700', color: '#FFF' },
});
