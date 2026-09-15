/**
 * Immersive Learning Modal v11.6
 * Interactive, Gamified Learning Experience
 */

import { NATIVE_DRIVER } from '../../src/utils/platformStyles';
import React, { useState, useEffect, useRef, memo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput,
  Modal, ActivityIndicator, Dimensions, Animated, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';
import * as Haptics from 'expo-haptics';

import { apiFetch } from '../../utils/apiController';
const { width: SCREEN_WIDTH } = Dimensions.get('window');
const API_URL = Constants.expoConfig?.extra?.apiUrl || process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface ImmersiveLearningModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  userId?: string;
}

type Tab = 'dashboard' | 'challenges' | 'quiz' | 'achievements' | 'leaderboard';
type Category = 'physics' | 'math' | 'cs';
type Difficulty = 'easy' | 'medium' | 'hard' | 'expert';

interface Profile {
  xp: number;
  level: number;
  streak_days: number;
  achievements: string[];
  xp_to_next_level: number;
  current_level_xp: number;
  level_total_xp: number;
  total_challenges_completed: number;
  total_quizzes_completed: number;
  skill_ratings: Record<string, number>;
}

interface Challenge {
  challenge_id: string;
  title: string;
  description: string;
  difficulty: Difficulty;
  xp_reward: number;
  starter_code?: string;
  hints?: string[];
}

export const ImmersiveLearningModal = memo(function ImmersiveLearningModal({
  visible, onClose, colors, userId = 'default_user'
}: ImmersiveLearningModalProps) {
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<Category>('physics');
  const [challenges, setChallenges] = useState<Challenge[]>([]);
  const [activeChallenge, setActiveChallenge] = useState<any>(null);
  const [code, setCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [quiz, setQuiz] = useState<any>(null);
  const [quizAnswers, setQuizAnswers] = useState<Record<number, string>>({});
  const [quizResult, setQuizResult] = useState<any>(null);
  const [achievements, setAchievements] = useState<any[]>([]);
  const [leaderboard, setLeaderboard] = useState<any[]>([]);
  const [dailyChallenge, setDailyChallenge] = useState<any>(null);
  const [showHint, setShowHint] = useState(false);
  const [currentHintIndex, setCurrentHintIndex] = useState(0);
  const [preferredLanguage, setPreferredLanguage] = useState<string>('python');
  const [showSettings, setShowSettings] = useState(false);
  const [quizDifficulty, setQuizDifficulty] = useState<number>(0); // 0 = all
  const [quizCount, setQuizCount] = useState<number>(10);

  const xpAnim = useRef(new Animated.Value(0)).current;

  const LANGUAGES = [
    { id: 'python', name: 'Python', icon: 'logo-python' },
    { id: 'javascript', name: 'JavaScript', icon: 'logo-javascript' },
    { id: 'typescript', name: 'TypeScript', icon: 'code-slash' },
    { id: 'csharp', name: 'C#', icon: 'code' },
    { id: 'cpp', name: 'C++', icon: 'hardware-chip' },
    { id: 'rust', name: 'Rust', icon: 'cog' },
    { id: 'gdscript', name: 'GDScript', icon: 'game-controller' },
  ];

  useEffect(() => {
    if (visible) {
      loadProfile();
      loadDailyChallenge();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  const loadProfile = async () => {
    try {
      const res = await apiFetch(`${API_URL}/api/learning/profile/${userId}`);
      const data = await res.json();
      setProfile(data);
    } catch (e) {
      console.error('Failed to load profile:', e);
    }
  };

  const loadDailyChallenge = async () => {
    try {
      const res = await apiFetch(`${API_URL}/api/learning/daily-challenge`);
      const data = await res.json();
      setDailyChallenge(data);
    } catch (e) {
      console.error('Failed to load daily challenge:', e);
    }
  };

  const loadChallenges = async (category: Category) => {
    setLoading(true);
    try {
      const res = await apiFetch(`${API_URL}/api/learning/challenges/${category}`);
      const data = await res.json();
      setChallenges(data.challenges || []);
    } catch (e) {
      console.error('Failed to load challenges:', e);
    } finally {
      setLoading(false);
    }
  };

  const loadChallengeDetail = async (category: string, index: number) => {
    setLoading(true);
    try {
      const res = await apiFetch(`${API_URL}/api/learning/challenge/${category}/${index}`);
      const data = await res.json();
      setActiveChallenge(data);
      setCode(data.starter_code || '');
      setResult(null);
      setShowHint(false);
      setCurrentHintIndex(0);
    } catch (e) {
      console.error('Failed to load challenge:', e);
    } finally {
      setLoading(false);
    }
  };

  const submitChallenge = async () => {
    if (!activeChallenge || !code.trim()) return;
    setSubmitting(true);
    setResult(null);

    try {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      
      const [category, indexStr] = activeChallenge.challenge_id.split('_');
      const res = await apiFetch(`${API_URL}/api/learning/challenge/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          category,
          challenge_index: parseInt(indexStr),
          code,
          time_taken_seconds: 120
        })
      });
      const data = await res.json();
      setResult(data);

      if (data.passed) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        // Animate XP gain
        Animated.sequence([
          Animated.timing(xpAnim, { toValue: 1, duration: 300, useNativeDriver: NATIVE_DRIVER }),
          Animated.timing(xpAnim, { toValue: 0, duration: 300, useNativeDriver: NATIVE_DRIVER })
        ]).start();
        loadProfile();
      } else {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      }
    } catch (e) {
      console.error('Submit error:', e);
    } finally {
      setSubmitting(false);
    }
  };

  const loadQuiz = async (category: Category) => {
    setLoading(true);
    setQuizResult(null);
    setQuizAnswers({});
    try {
      // Use comprehensive quiz bank with difficulty filter
      const diffParam = quizDifficulty > 0 ? `&difficulty=${quizDifficulty}` : '';
      const res = await apiFetch(`${API_URL}/api/quiz-bank/${category}?count=${quizCount}${diffParam}`);
      const data = await res.json();
      setQuiz(data);
    } catch (e) {
      console.error('Failed to load quiz:', e);
    } finally {
      setLoading(false);
    }
  };

  const submitQuiz = async () => {
    if (!quiz) return;
    setSubmitting(true);

    try {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      
      const answers = Object.entries(quizAnswers).map(([idx, answer]) => ({
        question_index: parseInt(idx),
        answer
      }));

      const res = await apiFetch(`${API_URL}/api/learning/quiz/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          category: quiz.category,
          answers
        })
      });
      const data = await res.json();
      setQuizResult(data);

      if (data.perfect_score) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      }
      loadProfile();
    } catch (e) {
      console.error('Quiz submit error:', e);
    } finally {
      setSubmitting(false);
    }
  };

  const loadAchievements = async () => {
    try {
      const res = await apiFetch(`${API_URL}/api/learning/achievements`);
      const data = await res.json();
      setAchievements(data.achievements || []);
    } catch (e) {
      console.error('Failed to load achievements:', e);
    }
  };

  const loadLeaderboard = async () => {
    try {
      const res = await apiFetch(`${API_URL}/api/learning/leaderboard?limit=10`);
      const data = await res.json();
      setLeaderboard(data.leaderboard || []);
    } catch (e) {
      console.error('Failed to load leaderboard:', e);
    }
  };

  useEffect(() => {
    if (activeTab === 'challenges') loadChallenges(selectedCategory);
    if (activeTab === 'achievements') loadAchievements();
    if (activeTab === 'leaderboard') loadLeaderboard();
  }, [activeTab, selectedCategory]);

  const categories: { id: Category; name: string; icon: string; color: string }[] = [
    { id: 'physics', name: 'Physics', icon: 'nuclear', color: '#3B82F6' },
    { id: 'math', name: 'Math', icon: 'calculator', color: '#8B5CF6' },
    { id: 'cs', name: 'CS', icon: 'code-slash', color: '#10B981' },
  ];

  const difficultyColors: Record<Difficulty, string> = {
    easy: '#10B981',
    medium: '#F59E0B',
    hard: '#EF4444',
    expert: '#8B5CF6'
  };

  const tabs: { id: Tab; name: string; icon: string }[] = [
    { id: 'dashboard', name: 'Home', icon: 'home' },
    { id: 'challenges', name: 'Challenges', icon: 'code-working' },
    { id: 'quiz', name: 'Quiz', icon: 'help-circle' },
    { id: 'achievements', name: 'Badges', icon: 'trophy' },
    { id: 'leaderboard', name: 'Ranks', icon: 'podium' },
  ];

  const renderDashboard = () => (
    <ScrollView style={localStyles.tabContent} showsVerticalScrollIndicator={false}>
      {/* Profile Card */}
      {profile && (
        <View style={[localStyles.profileCard, { backgroundColor: colors.surfaceAlt }]}>
          <View style={localStyles.profileHeader}>
            <View style={[localStyles.levelBadge, { backgroundColor: '#6366F1' }]}>
              <Text style={localStyles.levelText}>Lv.{profile.level}</Text>
            </View>
            <View style={localStyles.profileInfo}>
              <Text style={[localStyles.xpText, { color: colors.text }]}>
                {(profile?.xp || 0).toLocaleString()} XP
              </Text>
              <View style={localStyles.xpBarContainer}>
                <View style={[localStyles.xpBar, { 
                  width: `${((profile?.current_level_xp || 0) / Math.max(1, profile?.level_total_xp || 1)) * 100}%`,
                  backgroundColor: '#6366F1'
                }]} />
              </View>
              <Text style={[localStyles.xpToNext, { color: colors.textMuted }]}>
                {profile.xp_to_next_level} XP to next level
              </Text>
            </View>
          </View>

          {/* Stats Row */}
          <View style={localStyles.statsRow}>
            <View style={localStyles.statItem}>
              <Ionicons name="flame" size={20} color="#F59E0B" />
              <Text style={[localStyles.statValue, { color: colors.text }]}>{profile.streak_days}</Text>
              <Text style={[localStyles.statLabel, { color: colors.textMuted }]}>Day Streak</Text>
            </View>
            <View style={localStyles.statItem}>
              <Ionicons name="checkmark-done" size={20} color="#10B981" />
              <Text style={[localStyles.statValue, { color: colors.text }]}>{profile.total_challenges_completed}</Text>
              <Text style={[localStyles.statLabel, { color: colors.textMuted }]}>Challenges</Text>
            </View>
            <View style={localStyles.statItem}>
              <Ionicons name="ribbon" size={20} color="#EC4899" />
              <Text style={[localStyles.statValue, { color: colors.text }]}>{profile.achievements?.length || 0}</Text>
              <Text style={[localStyles.statLabel, { color: colors.textMuted }]}>Badges</Text>
            </View>
          </View>
        </View>
      )}

      {/* Daily Challenge */}
      {dailyChallenge && (
        <TouchableOpacity 
          style={[localStyles.dailyCard, { backgroundColor: '#F59E0B20', borderColor: '#F59E0B' }]}
          onPress={() => {
            setActiveTab('challenges');
            setActiveChallenge(dailyChallenge);
            setCode(dailyChallenge.starter_code || '');
          }}
        >
          <View style={localStyles.dailyHeader}>
            <Ionicons name="sunny" size={24} color="#F59E0B" />
            <View style={localStyles.dailyInfo}>
              <Text style={[localStyles.dailyTitle, { color: colors.text }]}>Daily Challenge</Text>
              <Text style={[localStyles.dailyBonus, { color: '#F59E0B' }]}>{dailyChallenge.bonus}</Text>
            </View>
          </View>
          <Text style={[localStyles.dailyChallengeTitle, { color: colors.text }]}>
            {dailyChallenge.title}
          </Text>
          <View style={localStyles.dailyMeta}>
            <View style={[localStyles.difficultyBadge, { backgroundColor: difficultyColors[dailyChallenge.difficulty as Difficulty] }]}>
              <Text style={localStyles.difficultyText}>{dailyChallenge.difficulty}</Text>
            </View>
            <Text style={[localStyles.xpReward, { color: '#F59E0B' }]}>+{dailyChallenge.xp_reward} XP</Text>
          </View>
        </TouchableOpacity>
      )}

      {/* Skill Progress */}
      <Text style={[localStyles.sectionTitle, { color: colors.text }]}>Skill Progress</Text>
      {profile && (
        <View style={[localStyles.skillsCard, { backgroundColor: colors.surfaceAlt }]}>
          {categories.map((cat) => (
            <View key={cat.id} style={localStyles.skillRow}>
              <View style={localStyles.skillLabel}>
                <Ionicons name={cat.icon as any} size={18} color={cat.color} />
                <Text style={[localStyles.skillName, { color: colors.text }]}>{cat.name}</Text>
              </View>
              <View style={localStyles.skillBarContainer}>
                <View style={[
                  localStyles.skillBar,
                  { width: `${profile.skill_ratings?.[cat.id] || 50}%`, backgroundColor: cat.color }
                ]} />
              </View>
              <Text style={[localStyles.skillPercent, { color: colors.textMuted }]}>
                {profile.skill_ratings?.[cat.id] || 50}%
              </Text>
            </View>
          ))}
        </View>
      )}

      {/* Quick Actions */}
      <Text style={[localStyles.sectionTitle, { color: colors.text }]}>Quick Start</Text>
      <View style={localStyles.quickActions}>
        <TouchableOpacity
          style={[localStyles.quickAction, { backgroundColor: '#3B82F620' }]}
          onPress={() => { setSelectedCategory('physics'); setActiveTab('challenges'); }}
        >
          <Ionicons name="nuclear" size={28} color="#3B82F6" />
          <Text style={[localStyles.quickActionText, { color: colors.text }]}>Physics</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[localStyles.quickAction, { backgroundColor: '#8B5CF620' }]}
          onPress={() => { setSelectedCategory('math'); setActiveTab('quiz'); loadQuiz('math'); }}
        >
          <Ionicons name="calculator" size={28} color="#8B5CF6" />
          <Text style={[localStyles.quickActionText, { color: colors.text }]}>Math Quiz</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[localStyles.quickAction, { backgroundColor: '#10B98120' }]}
          onPress={() => { setSelectedCategory('cs'); setActiveTab('challenges'); }}
        >
          <Ionicons name="code-slash" size={28} color="#10B981" />
          <Text style={[localStyles.quickActionText, { color: colors.text }]}>CS Code</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );

  const renderChallenges = () => (
    <ScrollView style={localStyles.tabContent} showsVerticalScrollIndicator={false}>
      {activeChallenge ? (
        // Active Challenge View
        <View style={localStyles.challengeActive}>
          <TouchableOpacity
            style={localStyles.backBtn}
            onPress={() => { setActiveChallenge(null); setResult(null); }}
          >
            <Ionicons name="arrow-back" size={20} color={colors.text} />
            <Text style={[localStyles.backText, { color: colors.text }]}>Back to Challenges</Text>
          </TouchableOpacity>

          <View style={[localStyles.challengeHeader, { backgroundColor: colors.surfaceAlt }]}>
            <Text style={[localStyles.challengeTitle, { color: colors.text }]}>
              {activeChallenge.title}
            </Text>
            <View style={localStyles.challengeMeta}>
              <View style={[localStyles.difficultyBadge, { backgroundColor: difficultyColors[activeChallenge.difficulty as Difficulty] }]}>
                <Text style={localStyles.difficultyText}>{activeChallenge.difficulty}</Text>
              </View>
              <Text style={[localStyles.xpReward, { color: '#10B981' }]}>+{activeChallenge.xp_reward} XP</Text>
            </View>
            <Text style={[localStyles.challengeDesc, { color: colors.textMuted }]}>
              {activeChallenge.description}
            </Text>
          </View>

          {/* Hints */}
          {activeChallenge.hints?.length > 0 && (
            <TouchableOpacity
              style={[localStyles.hintBtn, { backgroundColor: colors.surfaceAlt }]}
              onPress={() => {
                setShowHint(true);
                Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
              }}
            >
              <Ionicons name="bulb" size={20} color="#F59E0B" />
              <Text style={[localStyles.hintBtnText, { color: '#F59E0B' }]}>
                {showHint ? `Hint ${currentHintIndex + 1}/${activeChallenge.hints.length}` : 'Need a hint?'}
              </Text>
            </TouchableOpacity>
          )}

          {showHint && activeChallenge.hints && (
            <View style={[localStyles.hintCard, { backgroundColor: '#F59E0B15', borderColor: '#F59E0B' }]}>
              <Text style={[localStyles.hintText, { color: colors.text }]}>
                {activeChallenge.hints[currentHintIndex]}
              </Text>
              {currentHintIndex < activeChallenge.hints.length - 1 && (
                <TouchableOpacity
                  style={localStyles.nextHintBtn}
                  onPress={() => setCurrentHintIndex(i => i + 1)}
                >
                  <Text style={[localStyles.nextHintText, { color: '#F59E0B' }]}>Next Hint</Text>
                </TouchableOpacity>
              )}
            </View>
          )}

          {/* Code Editor */}
          <Text style={[localStyles.editorLabel, { color: colors.text }]}>Your Solution</Text>
          <TextInput
            style={[
              localStyles.codeEditor,
              { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }
            ]}
            value={code}
            onChangeText={setCode}
            multiline
            placeholder="Write your code here..."
            placeholderTextColor={colors.textMuted}
            autoCapitalize="none"
            autoCorrect={false}
            spellCheck={false}
          />

          <TouchableOpacity
            style={[localStyles.submitBtn, { backgroundColor: submitting ? colors.surfaceAlt : '#10B981' }]}
            onPress={submitChallenge}
            disabled={submitting || !code.trim()}
          >
            {submitting ? (
              <ActivityIndicator color="#FFF" />
            ) : (
              <>
                <Ionicons name="checkmark-circle" size={20} color="#FFF" />
                <Text style={localStyles.submitBtnText}>Submit Solution</Text>
              </>
            )}
          </TouchableOpacity>

          {/* Result */}
          {result && (
            <View style={[
              localStyles.resultCard,
              { backgroundColor: result.passed ? '#10B98120' : '#EF444420', borderColor: result.passed ? '#10B981' : '#EF4444' }
            ]}>
              <View style={localStyles.resultHeader}>
                <Ionicons
                  name={result.passed ? 'checkmark-circle' : 'close-circle'}
                  size={28}
                  color={result.passed ? '#10B981' : '#EF4444'}
                />
                <Text style={[localStyles.resultTitle, { color: result.passed ? '#10B981' : '#EF4444' }]}>
                  {result.passed ? 'Challenge Completed!' : 'Not Quite Right'}
                </Text>
              </View>
              {result.passed && (
                <View style={localStyles.xpEarned}>
                  <Ionicons name="star" size={18} color="#F59E0B" />
                  <Text style={localStyles.xpEarnedText}>+{result.xp_earned} XP earned!</Text>
                </View>
              )}
              <Text style={[localStyles.feedbackText, { color: colors.text }]}>
                {result.feedback}
              </Text>
              {result.improvements?.length > 0 && (
                <View style={localStyles.improvements}>
                  <Text style={[localStyles.improvementsTitle, { color: colors.textMuted }]}>Suggestions:</Text>
                  {result.improvements.map((imp: string, i: number) => (
                    <Text key={i} style={[localStyles.improvementItem, { color: colors.text }]}>
                      • {imp}
                    </Text>
                  ))}
                </View>
              )}
            </View>
          )}
        </View>
      ) : (
        // Challenge List View
        <>
          {/* Category Tabs */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={localStyles.categoryTabs}>
            {categories.map((cat) => (
              <TouchableOpacity
                key={cat.id}
                style={[
                  localStyles.categoryTab,
                  { backgroundColor: selectedCategory === cat.id ? cat.color + '20' : colors.surfaceAlt }
                ]}
                onPress={() => setSelectedCategory(cat.id)}
              >
                <Ionicons name={cat.icon as any} size={20} color={cat.color} />
                <Text style={[localStyles.categoryTabText, { color: selectedCategory === cat.id ? cat.color : colors.text }]}>
                  {cat.name}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          {loading ? (
            <ActivityIndicator size="large" color="#6366F1" style={{ marginTop: 40 }} />
          ) : (
            <View style={localStyles.challengeList}>
              {challenges.map((challenge, index) => (
                <TouchableOpacity
                  key={challenge.challenge_id}
                  style={[localStyles.challengeCard, { backgroundColor: colors.surfaceAlt }]}
                  onPress={() => loadChallengeDetail(selectedCategory, index)}
                >
                  <View style={localStyles.challengeCardHeader}>
                    <Text style={[localStyles.challengeCardTitle, { color: colors.text }]}>
                      {challenge.title}
                    </Text>
                    <View style={[
                      localStyles.difficultyBadge,
                      { backgroundColor: difficultyColors[challenge.difficulty] }
                    ]}>
                      <Text style={localStyles.difficultyText}>{challenge.difficulty}</Text>
                    </View>
                  </View>
                  <Text style={[localStyles.challengeCardDesc, { color: colors.textMuted }]} numberOfLines={2}>
                    {challenge.description}
                  </Text>
                  <View style={localStyles.challengeCardFooter}>
                    <Text style={[localStyles.xpReward, { color: '#10B981' }]}>+{challenge.xp_reward} XP</Text>
                    <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                  </View>
                </TouchableOpacity>
              ))}
            </View>
          )}
        </>
      )}
    </ScrollView>
  );

  const renderQuiz = () => (
    <ScrollView style={localStyles.tabContent} showsVerticalScrollIndicator={false}>
      {quizResult ? (
        // Quiz Results
        <View style={localStyles.quizResults}>
          <View style={[
            localStyles.scoreCard,
            { backgroundColor: quizResult.perfect_score ? '#10B98120' : colors.surfaceAlt }
          ]}>
            <Text style={[localStyles.scorePercent, { color: quizResult.perfect_score ? '#10B981' : colors.text }]}>
              {quizResult.score_percent}%
            </Text>
            <Text style={[localStyles.scoreLabel, { color: colors.textMuted }]}>
              {quizResult.correct}/{quizResult.total} correct
            </Text>
            <View style={localStyles.xpEarned}>
              <Ionicons name="star" size={18} color="#F59E0B" />
              <Text style={localStyles.xpEarnedText}>+{quizResult.xp_earned} XP</Text>
            </View>
            <Text style={[localStyles.encouragement, { color: colors.text }]}>
              {quizResult.encouragement}
            </Text>
          </View>

          {quizResult.results?.map((r: any, i: number) => (
            <View
              key={i}
              style={[
                localStyles.resultItem,
                { backgroundColor: r.is_correct ? '#10B98115' : '#EF444415', borderLeftColor: r.is_correct ? '#10B981' : '#EF4444' }
              ]}
            >
              <View style={localStyles.resultItemHeader}>
                <Ionicons
                  name={r.is_correct ? 'checkmark-circle' : 'close-circle'}
                  size={20}
                  color={r.is_correct ? '#10B981' : '#EF4444'}
                />
                <Text style={[localStyles.resultQuestion, { color: colors.text }]}>{r.question}</Text>
              </View>
              {!r.is_correct && (
                <Text style={[localStyles.correctAnswer, { color: '#10B981' }]}>
                  Correct: {r.correct_answer}
                </Text>
              )}
              <Text style={[localStyles.explanation, { color: colors.textMuted }]}>
                {r.explanation}
              </Text>
            </View>
          ))}

          <TouchableOpacity
            style={[localStyles.retryBtn, { backgroundColor: colors.primary }]}
            onPress={() => { setQuizResult(null); setQuiz(null); loadQuiz(selectedCategory); }}
          >
            <Ionicons name="refresh" size={20} color="#FFF" />
            <Text style={localStyles.retryBtnText}>Try Another Quiz</Text>
          </TouchableOpacity>
        </View>
      ) : quiz ? (
        // Active Quiz
        <View style={localStyles.quizActive}>
          <View style={[localStyles.quizProgress, { backgroundColor: colors.surfaceAlt }]}>
            <Text style={[localStyles.quizProgressText, { color: colors.text }]}>
              {Object.keys(quizAnswers).length}/{quiz.questions.length} answered
            </Text>
            <Text style={[localStyles.quizXp, { color: '#F59E0B' }]}>+{quiz.total_xp} XP possible</Text>
          </View>

          {quiz.questions.map((q: any, i: number) => (
            <View key={q.question_id} style={[localStyles.questionCard, { backgroundColor: colors.surfaceAlt }]}>
              <Text style={[localStyles.questionNumber, { color: colors.textMuted }]}>Question {i + 1}</Text>
              <Text style={[localStyles.questionText, { color: colors.text }]}>{q.question}</Text>
              <View style={localStyles.optionsContainer}>
                {q.options?.map((option: string, optIdx: number) => (
                  <TouchableOpacity
                    key={optIdx}
                    style={[
                      localStyles.optionBtn,
                      {
                        backgroundColor: quizAnswers[i] === option ? '#6366F120' : colors.background,
                        borderColor: quizAnswers[i] === option ? '#6366F1' : colors.border
                      }
                    ]}
                    onPress={() => {
                      Haptics.selectionAsync();
                      setQuizAnswers(prev => ({ ...prev, [i]: option }));
                    }}
                  >
                    <View style={[
                      localStyles.optionRadio,
                      { borderColor: quizAnswers[i] === option ? '#6366F1' : colors.border }
                    ]}>
                      {quizAnswers[i] === option && <View style={localStyles.optionRadioInner} />}
                    </View>
                    <Text style={[localStyles.optionText, { color: colors.text }]}>{option}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          ))}

          <TouchableOpacity
            style={[
              localStyles.submitQuizBtn,
              { backgroundColor: Object.keys(quizAnswers).length === quiz.questions.length ? '#6366F1' : colors.surfaceAlt }
            ]}
            onPress={submitQuiz}
            disabled={submitting || Object.keys(quizAnswers).length < quiz.questions.length}
          >
            {submitting ? (
              <ActivityIndicator color="#FFF" />
            ) : (
              <>
                <Ionicons name="checkmark-done" size={20} color="#FFF" />
                <Text style={localStyles.submitQuizBtnText}>Submit Quiz</Text>
              </>
            )}
          </TouchableOpacity>
        </View>
      ) : (
        // Quiz Selection
        <>
          <Text style={[localStyles.sectionTitle, { color: colors.text }]}>Choose a Quiz</Text>
          {categories.map((cat) => (
            <TouchableOpacity
              key={cat.id}
              style={[localStyles.quizCard, { backgroundColor: cat.color + '15', borderColor: cat.color }]}
              onPress={() => { setSelectedCategory(cat.id); loadQuiz(cat.id); }}
            >
              <Ionicons name={cat.icon as any} size={32} color={cat.color} />
              <View style={localStyles.quizCardInfo}>
                <Text style={[localStyles.quizCardTitle, { color: colors.text }]}>{cat.name} Quiz</Text>
                <Text style={[localStyles.quizCardDesc, { color: colors.textMuted }]}>5 questions • Test your knowledge</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color={cat.color} />
            </TouchableOpacity>
          ))}
        </>
      )}
    </ScrollView>
  );

  const renderAchievements = () => (
    <ScrollView style={localStyles.tabContent} showsVerticalScrollIndicator={false}>
      <Text style={[localStyles.sectionTitle, { color: colors.text }]}>Your Badges</Text>
      <View style={localStyles.achievementGrid}>
        {achievements.map((ach) => {
          const unlocked = profile?.achievements?.includes(ach.id);
          return (
            <View
              key={ach.id}
              style={[
                localStyles.achievementCard,
                { backgroundColor: unlocked ? '#F59E0B15' : colors.surfaceAlt, opacity: unlocked ? 1 : 0.5 }
              ]}
            >
              <Ionicons
                name={ach.icon as any}
                size={32}
                color={unlocked ? '#F59E0B' : colors.textMuted}
              />
              <Text style={[localStyles.achievementName, { color: unlocked ? colors.text : colors.textMuted }]}>
                {ach.name}
              </Text>
              <Text style={[localStyles.achievementDesc, { color: colors.textMuted }]} numberOfLines={2}>
                {ach.description}
              </Text>
              <Text style={[localStyles.achievementXp, { color: unlocked ? '#F59E0B' : colors.textMuted }]}>
                +{ach.xp_bonus} XP
              </Text>
              {unlocked && (
                <View style={localStyles.unlockedBadge}>
                  <Ionicons name="checkmark-circle" size={16} color="#10B981" />
                </View>
              )}
            </View>
          );
        })}
      </View>
    </ScrollView>
  );

  const renderLeaderboard = () => (
    <ScrollView style={localStyles.tabContent} showsVerticalScrollIndicator={false}>
      <Text style={[localStyles.sectionTitle, { color: colors.text }]}>Leaderboard</Text>
      {leaderboard.map((entry, index) => (
        <View
          key={entry.user_id}
          style={[
            localStyles.leaderboardRow,
            { backgroundColor: index < 3 ? ['#FFD70020', '#C0C0C020', '#CD7F3220'][index] : colors.surfaceAlt }
          ]}
        >
          <View style={localStyles.rankContainer}>
            <Text style={[
              localStyles.rankText,
              { color: index < 3 ? ['#FFD700', '#C0C0C0', '#CD7F32'][index] : colors.text }
            ]}>
              #{entry.rank}
            </Text>
          </View>
          <View style={localStyles.leaderInfo}>
            <Text style={[localStyles.leaderName, { color: colors.text }]}>{entry.display_name}</Text>
            <Text style={[localStyles.leaderMeta, { color: colors.textMuted }]}>
              Level {entry.level} • {entry.streak_days} day streak
            </Text>
          </View>
          <View style={localStyles.leaderXp}>
            <Text style={[localStyles.leaderXpText, { color: '#F59E0B' }]}>{(entry?.xp || 0).toLocaleString()}</Text>
            <Text style={[localStyles.leaderXpLabel, { color: colors.textMuted }]}>XP</Text>
          </View>
        </View>
      ))}
    </ScrollView>
  );

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={localStyles.overlay}>
        <View style={[localStyles.modal, { backgroundColor: colors.surface }]}>
          {/* Header */}
          <View style={[localStyles.header, { borderBottomColor: colors.border }]}>
            <View style={localStyles.headerTitle}>
              <Ionicons name="school" size={24} color="#6366F1" />
              <Text style={[localStyles.title, { color: colors.text }]}>Learning Hub</Text>
            </View>
            <View style={localStyles.headerActions}>
              {/* Language Selector Button */}
              <TouchableOpacity 
                style={[localStyles.langBtn, { backgroundColor: colors.surfaceAlt }]}
                onPress={() => setShowSettings(!showSettings)}
              >
                <Ionicons name="code-slash" size={16} color="#6366F1" />
                <Text style={[localStyles.langText, { color: colors.text }]}>{preferredLanguage.toUpperCase()}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setShowSettings(!showSettings)}>
                <Ionicons name="settings-outline" size={22} color={colors.textSecondary} />
              </TouchableOpacity>
              <TouchableOpacity onPress={onClose} style={{ marginLeft: 12 }}>
                <Ionicons name="close" size={24} color={colors.textSecondary} />
              </TouchableOpacity>
            </View>
          </View>

          {/* Settings Panel */}
          {showSettings && (
            <View style={[localStyles.settingsPanel, { backgroundColor: colors.surfaceAlt }]}>
              <Text style={[localStyles.settingsTitle, { color: colors.text }]}>Preferences</Text>
              
              {/* Language Selection */}
              <Text style={[localStyles.settingsLabel, { color: colors.textMuted }]}>Code Language</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={localStyles.langRow}>
                {LANGUAGES.map((lang) => (
                  <TouchableOpacity
                    key={lang.id}
                    style={[
                      localStyles.langChip,
                      { backgroundColor: preferredLanguage === lang.id ? '#6366F120' : colors.background }
                    ]}
                    onPress={() => setPreferredLanguage(lang.id)}
                  >
                    <Ionicons name={lang.icon as any} size={16} color={preferredLanguage === lang.id ? '#6366F1' : colors.textMuted} />
                    <Text style={[localStyles.langChipText, { color: preferredLanguage === lang.id ? '#6366F1' : colors.text }]}>
                      {lang.name}
                    </Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>

              {/* Quiz Settings */}
              <Text style={[localStyles.settingsLabel, { color: colors.textMuted, marginTop: 12 }]}>Quiz Difficulty</Text>
              <View style={localStyles.difficultyRow}>
                {[{ id: 0, name: 'All' }, { id: 1, name: 'Easy' }, { id: 2, name: 'Medium' }, { id: 3, name: 'Hard' }, { id: 4, name: 'Expert' }].map((d) => (
                  <TouchableOpacity
                    key={d.id}
                    style={[
                      localStyles.diffChip,
                      { backgroundColor: quizDifficulty === d.id ? '#6366F1' : colors.background }
                    ]}
                    onPress={() => setQuizDifficulty(d.id)}
                  >
                    <Text style={[localStyles.diffChipText, { color: quizDifficulty === d.id ? '#FFF' : colors.text }]}>
                      {d.name}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Quiz Count */}
              <Text style={[localStyles.settingsLabel, { color: colors.textMuted, marginTop: 12 }]}>Questions per Quiz</Text>
              <View style={localStyles.countRow}>
                {[5, 10, 15, 20, 30].map((c) => (
                  <TouchableOpacity
                    key={c}
                    style={[
                      localStyles.countChip,
                      { backgroundColor: quizCount === c ? '#6366F1' : colors.background }
                    ]}
                    onPress={() => setQuizCount(c)}
                  >
                    <Text style={[localStyles.countChipText, { color: quizCount === c ? '#FFF' : colors.text }]}>
                      {c}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <TouchableOpacity
                style={[localStyles.closeSettings, { backgroundColor: '#6366F1' }]}
                onPress={() => setShowSettings(false)}
              >
                <Text style={localStyles.closeSettingsText}>Done</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* Tab Content */}
          {activeTab === 'dashboard' && renderDashboard()}
          {activeTab === 'challenges' && renderChallenges()}
          {activeTab === 'quiz' && renderQuiz()}
          {activeTab === 'achievements' && renderAchievements()}
          {activeTab === 'leaderboard' && renderLeaderboard()}

          {/* Bottom Tabs */}
          <View style={[localStyles.bottomTabs, { backgroundColor: colors.surface, borderTopColor: colors.border }]}>
            {tabs.map((tab) => (
              <TouchableOpacity
                key={tab.id}
                style={localStyles.tabBtn}
                onPress={() => setActiveTab(tab.id)}
              >
                <Ionicons
                  name={tab.icon as any}
                  size={22}
                  color={activeTab === tab.id ? '#6366F1' : colors.textMuted}
                />
                <Text style={[
                  localStyles.tabLabel,
                  { color: activeTab === tab.id ? '#6366F1' : colors.textMuted }
                ]}>
                  {tab.name}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </View>
    </Modal>
  );
});

const localStyles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  modal: { height: '95%', borderTopLeftRadius: 20, borderTopRightRadius: 20 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1 },
  headerTitle: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  title: { fontSize: 18, fontWeight: '700' },
  tabContent: { flex: 1, padding: 16 },
  
  // Profile Card
  profileCard: { padding: 16, borderRadius: 16, marginBottom: 16 },
  profileHeader: { flexDirection: 'row', alignItems: 'center', gap: 16, marginBottom: 16 },
  levelBadge: { width: 56, height: 56, borderRadius: 28, justifyContent: 'center', alignItems: 'center' },
  levelText: { color: '#FFF', fontSize: 16, fontWeight: '800' },
  profileInfo: { flex: 1 },
  xpText: { fontSize: 18, fontWeight: '700', marginBottom: 6 },
  xpBarContainer: { height: 8, backgroundColor: '#333', borderRadius: 4, marginBottom: 4 },
  xpBar: { height: '100%', borderRadius: 4 },
  xpToNext: { fontSize: 11 },
  statsRow: { flexDirection: 'row', justifyContent: 'space-around' },
  statItem: { alignItems: 'center' },
  statValue: { fontSize: 18, fontWeight: '700', marginTop: 4 },
  statLabel: { fontSize: 11, marginTop: 2 },

  // Daily Challenge
  dailyCard: { padding: 16, borderRadius: 16, borderWidth: 1, marginBottom: 16 },
  dailyHeader: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 8 },
  dailyInfo: { flex: 1 },
  dailyTitle: { fontSize: 14, fontWeight: '700' },
  dailyBonus: { fontSize: 12, fontWeight: '600' },
  dailyChallengeTitle: { fontSize: 16, fontWeight: '600', marginBottom: 8 },
  dailyMeta: { flexDirection: 'row', alignItems: 'center', gap: 10 },

  // Difficulty & XP
  difficultyBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  difficultyText: { color: '#FFF', fontSize: 11, fontWeight: '600', textTransform: 'uppercase' },
  xpReward: { fontSize: 13, fontWeight: '700' },

  // Skills
  sectionTitle: { fontSize: 16, fontWeight: '700', marginBottom: 12, marginTop: 8 },
  skillsCard: { padding: 16, borderRadius: 12, marginBottom: 16, gap: 14 },
  skillRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  skillLabel: { flexDirection: 'row', alignItems: 'center', gap: 8, width: 80 },
  skillName: { fontSize: 13, fontWeight: '600' },
  skillBarContainer: { flex: 1, height: 8, backgroundColor: '#333', borderRadius: 4 },
  skillBar: { height: '100%', borderRadius: 4 },
  skillPercent: { fontSize: 12, width: 35, textAlign: 'right' },

  // Quick Actions
  quickActions: { flexDirection: 'row', gap: 12, marginBottom: 20 },
  quickAction: { flex: 1, padding: 16, borderRadius: 12, alignItems: 'center', gap: 8 },
  quickActionText: { fontSize: 12, fontWeight: '600' },

  // Challenges
  categoryTabs: { marginBottom: 16 },
  categoryTab: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, marginRight: 10, gap: 8 },
  categoryTabText: { fontSize: 14, fontWeight: '600' },
  challengeList: { gap: 12 },
  challengeCard: { padding: 16, borderRadius: 12 },
  challengeCardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  challengeCardTitle: { fontSize: 15, fontWeight: '700', flex: 1, marginRight: 10 },
  challengeCardDesc: { fontSize: 13, lineHeight: 18, marginBottom: 10 },
  challengeCardFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },

  // Active Challenge
  challengeActive: {},
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 },
  backText: { fontSize: 14, fontWeight: '600' },
  challengeHeader: { padding: 16, borderRadius: 12, marginBottom: 16 },
  challengeTitle: { fontSize: 18, fontWeight: '700', marginBottom: 8 },
  challengeMeta: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 },
  challengeDesc: { fontSize: 14, lineHeight: 22 },
  hintBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12, borderRadius: 10, marginBottom: 12 },
  hintBtnText: { fontSize: 14, fontWeight: '600' },
  hintCard: { padding: 14, borderRadius: 10, borderWidth: 1, marginBottom: 12 },
  hintText: { fontSize: 14, lineHeight: 22 },
  nextHintBtn: { marginTop: 10, alignItems: 'flex-end' },
  nextHintText: { fontSize: 13, fontWeight: '600' },
  editorLabel: { fontSize: 14, fontWeight: '600', marginBottom: 8 },
  codeEditor: { minHeight: 200, padding: 14, borderRadius: 12, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', fontSize: 13, borderWidth: 1, textAlignVertical: 'top' },
  submitBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, paddingVertical: 14, borderRadius: 12, marginTop: 12 },
  submitBtnText: { color: '#FFF', fontSize: 16, fontWeight: '700' },
  resultCard: { padding: 16, borderRadius: 12, borderWidth: 1, marginTop: 16 },
  resultHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 },
  resultTitle: { fontSize: 16, fontWeight: '700' },
  xpEarned: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 },
  xpEarnedText: { color: '#F59E0B', fontSize: 14, fontWeight: '700' },
  feedbackText: { fontSize: 14, lineHeight: 22 },
  improvements: { marginTop: 12 },
  improvementsTitle: { fontSize: 13, fontWeight: '600', marginBottom: 6 },
  improvementItem: { fontSize: 13, lineHeight: 20 },

  // Quiz
  quizCard: { flexDirection: 'row', alignItems: 'center', padding: 16, borderRadius: 12, borderWidth: 1, marginBottom: 12, gap: 12 },
  quizCardInfo: { flex: 1 },
  quizCardTitle: { fontSize: 16, fontWeight: '700' },
  quizCardDesc: { fontSize: 13, marginTop: 2 },
  quizActive: {},
  quizProgress: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 14, borderRadius: 12, marginBottom: 16 },
  quizProgressText: { fontSize: 14, fontWeight: '600' },
  quizXp: { fontSize: 14, fontWeight: '700' },
  questionCard: { padding: 16, borderRadius: 12, marginBottom: 12 },
  questionNumber: { fontSize: 12, fontWeight: '600', marginBottom: 6 },
  questionText: { fontSize: 15, fontWeight: '600', lineHeight: 22, marginBottom: 14 },
  optionsContainer: { gap: 10 },
  optionBtn: { flexDirection: 'row', alignItems: 'center', padding: 14, borderRadius: 10, borderWidth: 1, gap: 12 },
  optionRadio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, justifyContent: 'center', alignItems: 'center' },
  optionRadioInner: { width: 12, height: 12, borderRadius: 6, backgroundColor: '#6366F1' },
  optionText: { flex: 1, fontSize: 14 },
  submitQuizBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, paddingVertical: 14, borderRadius: 12, marginTop: 8 },
  submitQuizBtnText: { color: '#FFF', fontSize: 16, fontWeight: '700' },
  quizResults: {},
  scoreCard: { padding: 20, borderRadius: 16, alignItems: 'center', marginBottom: 16 },
  scorePercent: { fontSize: 48, fontWeight: '800' },
  scoreLabel: { fontSize: 14, marginTop: 4, marginBottom: 10 },
  encouragement: { fontSize: 14, fontWeight: '600', textAlign: 'center', marginTop: 8 },
  resultItem: { padding: 14, borderRadius: 10, marginBottom: 10, borderLeftWidth: 3 },
  resultItemHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, marginBottom: 6 },
  resultQuestion: { flex: 1, fontSize: 13, fontWeight: '600' },
  correctAnswer: { fontSize: 13, fontWeight: '600', marginBottom: 6, marginLeft: 30 },
  explanation: { fontSize: 12, lineHeight: 18, marginLeft: 30 },
  retryBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, paddingVertical: 14, borderRadius: 12, marginTop: 12 },
  retryBtnText: { color: '#FFF', fontSize: 16, fontWeight: '700' },

  // Achievements
  achievementGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  achievementCard: { width: (SCREEN_WIDTH - 56) / 2, padding: 14, borderRadius: 12, alignItems: 'center' },
  achievementName: { fontSize: 13, fontWeight: '700', marginTop: 8, textAlign: 'center' },
  achievementDesc: { fontSize: 11, textAlign: 'center', marginTop: 4, lineHeight: 16 },
  achievementXp: { fontSize: 12, fontWeight: '600', marginTop: 6 },
  unlockedBadge: { position: 'absolute', top: 8, right: 8 },

  // Leaderboard
  leaderboardRow: { flexDirection: 'row', alignItems: 'center', padding: 14, borderRadius: 12, marginBottom: 10, gap: 12 },
  rankContainer: { width: 40, alignItems: 'center' },
  rankText: { fontSize: 18, fontWeight: '800' },
  leaderInfo: { flex: 1 },
  leaderName: { fontSize: 15, fontWeight: '600' },
  leaderMeta: { fontSize: 12, marginTop: 2 },
  leaderXp: { alignItems: 'flex-end' },
  leaderXpText: { fontSize: 16, fontWeight: '700' },
  leaderXpLabel: { fontSize: 11 },

  // Bottom Tabs
  bottomTabs: { flexDirection: 'row', borderTopWidth: 1, paddingVertical: 8, paddingBottom: Platform.OS === 'ios' ? 24 : 8 },
  tabBtn: { flex: 1, alignItems: 'center', paddingVertical: 6 },
  tabLabel: { fontSize: 10, marginTop: 4, fontWeight: '600' },

  // Settings Panel (v11.7)
  headerActions: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  langBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8 },
  langText: { fontSize: 12, fontWeight: '600' },
  settingsPanel: { padding: 16, margin: 16, borderRadius: 12, marginTop: 0 },
  settingsTitle: { fontSize: 16, fontWeight: '700', marginBottom: 16 },
  settingsLabel: { fontSize: 12, fontWeight: '600', marginBottom: 8 },
  langRow: { flexDirection: 'row', marginBottom: 8 },
  langChip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, marginRight: 8 },
  langChipText: { fontSize: 13, fontWeight: '600' },
  difficultyRow: { flexDirection: 'row', gap: 8, marginBottom: 8 },
  diffChip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 },
  diffChipText: { fontSize: 12, fontWeight: '600' },
  countRow: { flexDirection: 'row', gap: 8, marginBottom: 16 },
  countChip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 },
  countChipText: { fontSize: 12, fontWeight: '600' },
  closeSettings: { alignItems: 'center', paddingVertical: 12, borderRadius: 10 },
  closeSettingsText: { color: '#FFF', fontSize: 14, fontWeight: '700' },
});
