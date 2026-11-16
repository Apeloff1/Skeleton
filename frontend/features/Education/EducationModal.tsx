/**
 * Interactive Education Modal v11.0.0
 * Gamified Coding Challenges & AI-Powered Learning
 */

import React, { useState, useEffect } from 'react';
import { API_BASE } from '../../utils/apiBase';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput,
  Modal, ActivityIndicator, Dimensions, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API_URL = API_BASE;
const { width: SCREEN_WIDTH } = Dimensions.get('window');

interface EducationModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  onCodeLoad?: (code: string, language: string) => void;
}

type EducationTab = 'challenges' | 'daily' | 'achievements' | 'learn';

export const EducationModal: React.FC<EducationModalProps> = ({
  visible, onClose, colors, onCodeLoad
}) => {
  const [activeTab, setActiveTab] = useState<EducationTab>('challenges');
  const [isLoading, setIsLoading] = useState(false);
  const [challenges, setChallenges] = useState<any[]>([]);
  const [dailyChallenge, setDailyChallenge] = useState<any>(null);
  const [achievements, setAchievements] = useState<any[]>([]);
  const [selectedChallenge, setSelectedChallenge] = useState<any>(null);
  const [userCode, setUserCode] = useState('');
  const [submissionResult, setSubmissionResult] = useState<any>(null);
  const [selectedLanguage, setSelectedLanguage] = useState('python');
  const [selectedDifficulty, setSelectedDifficulty] = useState('beginner');
  
  // Learning path state
  const [learningPath, setLearningPath] = useState<any>(null);
  const [pathGoals, setPathGoals] = useState<string[]>(['web_development']);
  const [pathLevel, setPathLevel] = useState<'beginner' | 'intermediate' | 'advanced'>('beginner');

  useEffect(() => {
    if (visible) {
      loadChallenges();
      loadDailyChallenge();
      loadAchievements();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  const loadChallenges = async () => {
    setIsLoading(true);
    try {
      const response = await apiFetch(`${API_URL}/api/education/challenges/${selectedLanguage}?difficulty=${selectedDifficulty}`);
      const data = await response.json();
      setChallenges(data.challenges || []);
    } catch (error) {
      console.error('Failed to load challenges:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const loadDailyChallenge = async () => {
    try {
      const response = await apiFetch(`${API_URL}/api/education/daily-challenge`);
      const data = await response.json();
      setDailyChallenge(data.daily_challenge);
    } catch (error) {
      console.error('Failed to load daily challenge:', error);
    }
  };

  const loadAchievements = async () => {
    try {
      const response = await apiFetch(`${API_URL}/api/education/achievements`);
      const data = await response.json();
      setAchievements(data.achievements || []);
    } catch (error) {
      console.error('Failed to load achievements:', error);
    }
  };

  const submitChallenge = async () => {
    if (!selectedChallenge || !userCode.trim()) return;
    setIsLoading(true);
    setSubmissionResult(null);
    try {
      const response = await apiFetch(`${API_URL}/api/education/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          challenge_id: selectedChallenge.id,
          code: userCode,
          language: selectedChallenge.language || selectedLanguage
        })
      });
      const data = await response.json();
      setSubmissionResult(data.evaluation);
    } catch (error) {
      console.error('Submission failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const generateLearningPath = async () => {
    setIsLoading(true);
    try {
      const response = await apiFetch(`${API_URL}/api/education/learning-path`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_level: pathLevel,
          goals: pathGoals,
          time_commitment: 'moderate',
          preferred_languages: [selectedLanguage]
        })
      });
      const data = await response.json();
      setLearningPath(data.learning_path);
    } catch (error) {
      console.error('Failed to generate path:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const startChallenge = (challenge: any) => {
    setSelectedChallenge(challenge);
    setUserCode(challenge.starter_code || '');
    setSubmissionResult(null);
  };

  const tabs = [
    { key: 'challenges', icon: 'code-slash-outline', label: 'Challenges' },
    { key: 'daily', icon: 'today-outline', label: 'Daily' },
    { key: 'achievements', icon: 'trophy-outline', label: 'Badges' },
    { key: 'learn', icon: 'map-outline', label: 'Path' },
  ];

  const renderTabs = () => (
    <View style={[styles.tabBar, { backgroundColor: colors.surfaceAlt, borderBottomColor: colors.border }]}>
      {tabs.map((tab) => (
        <TouchableOpacity
          key={tab.key}
          style={[styles.tab, activeTab === tab.key && { borderBottomColor: colors.primary, borderBottomWidth: 2 }]}
          onPress={() => setActiveTab(tab.key as EducationTab)}
        >
          <Ionicons name={tab.icon as any} size={20} color={activeTab === tab.key ? colors.primary : colors.textMuted} />
          <Text style={[styles.tabText, { color: activeTab === tab.key ? colors.primary : colors.textMuted }]}>{tab.label}</Text>
        </TouchableOpacity>
      ))}
    </View>
  );

  const renderChallenges = () => (
    <View style={styles.section}>
      <View style={styles.filtersRow}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          {['python', 'javascript'].map((lang) => (
            <TouchableOpacity
              key={lang}
              style={[styles.filterChip, { backgroundColor: selectedLanguage === lang ? colors.primary : colors.surfaceAlt }]}
              onPress={() => { setSelectedLanguage(lang); }}
            >
              <Text style={[styles.filterText, { color: selectedLanguage === lang ? '#FFF' : colors.text }]}>{lang}</Text>
            </TouchableOpacity>
          ))}
          <View style={styles.filterDivider} />
          {['beginner', 'intermediate', 'advanced'].map((diff) => (
            <TouchableOpacity
              key={diff}
              style={[styles.filterChip, { backgroundColor: selectedDifficulty === diff ? colors.secondary : colors.surfaceAlt }]}
              onPress={() => { setSelectedDifficulty(diff); loadChallenges(); }}
            >
              <Text style={[styles.filterText, { color: selectedDifficulty === diff ? '#FFF' : colors.text }]}>{diff}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      {isLoading ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />
      ) : (
        <ScrollView style={styles.challengesList}>
          {challenges.map((challenge: any) => (
            <TouchableOpacity
              key={challenge.id}
              style={[styles.challengeCard, { backgroundColor: colors.surfaceAlt }]}
              onPress={() => startChallenge(challenge)}
            >
              <View style={styles.challengeHeader}>
                <View style={[styles.xpBadge, { backgroundColor: '#F59E0B20' }]}>
                  <Ionicons name="star" size={14} color="#F59E0B" />
                  <Text style={[styles.xpText, { color: '#F59E0B' }]}>{challenge.xp} XP</Text>
                </View>
                <Text style={[styles.timeLimit, { color: colors.textMuted }]}>
                  <Ionicons name="time-outline" size={12} /> {challenge.time_limit}s
                </Text>
              </View>
              <Text style={[styles.challengeTitle, { color: colors.text }]}>{challenge.title}</Text>
              <Text style={[styles.challengeDesc, { color: colors.textMuted }]}>{challenge.description}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      )}
    </View>
  );

  const renderDailyChallenge = () => (
    <View style={styles.section}>
      {dailyChallenge ? (
        <View style={[styles.dailyCard, { backgroundColor: colors.surfaceAlt, borderColor: colors.primary }]}>
          <View style={styles.dailyHeader}>
            <View style={[styles.dailyBadge, { backgroundColor: colors.primary + '20' }]}>
              <Ionicons name="flame" size={24} color={colors.primary} />
            </View>
            <View style={styles.dailyInfo}>
              <Text style={[styles.dailyLabel, { color: colors.textMuted }]}>TODAY&apos;S CHALLENGE</Text>
              <Text style={[styles.dailyTitle, { color: colors.text }]}>{dailyChallenge.title}</Text>
            </View>
            <View style={[styles.bonusBadge, { backgroundColor: '#10B98120' }]}>
              <Text style={[styles.bonusText, { color: '#10B981' }]}>+{dailyChallenge.bonus_xp} Bonus</Text>
            </View>
          </View>
          <Text style={[styles.dailyDesc, { color: colors.textMuted }]}>{dailyChallenge.description}</Text>
          <View style={styles.dailyMeta}>
            <View style={[styles.metaTag, { backgroundColor: colors.primary + '20' }]}>
              <Text style={[styles.metaText, { color: colors.primary }]}>{dailyChallenge.language}</Text>
            </View>
            <View style={[styles.metaTag, { backgroundColor: colors.secondary + '20' }]}>
              <Text style={[styles.metaText, { color: colors.secondary }]}>{dailyChallenge.difficulty}</Text>
            </View>
            <View style={[styles.metaTag, { backgroundColor: '#F59E0B20' }]}>
              <Text style={[styles.metaText, { color: '#F59E0B' }]}>{dailyChallenge.xp + dailyChallenge.bonus_xp} XP Total</Text>
            </View>
          </View>
          <TouchableOpacity
            style={[styles.startBtn, { backgroundColor: colors.primary }]}
            onPress={() => startChallenge(dailyChallenge)}
          >
            <Ionicons name="play" size={20} color="#FFF" />
            <Text style={styles.startBtnText}>Start Challenge</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <ActivityIndicator size="large" color={colors.primary} />
      )}
    </View>
  );

  const renderAchievements = () => (
    <ScrollView style={styles.section}>
      <View style={styles.achievementsGrid}>
        {achievements.map((achievement: any) => (
          <View
            key={achievement.id}
            style={[styles.achievementCard, { backgroundColor: colors.surfaceAlt }]}
          >
            <Text style={styles.achievementIcon}>{achievement.icon}</Text>
            <Text style={[styles.achievementName, { color: colors.text }]}>{achievement.name}</Text>
            <Text style={[styles.achievementDesc, { color: colors.textMuted }]}>{achievement.description}</Text>
            <View style={[styles.achievementXP, { backgroundColor: '#F59E0B20' }]}>
              <Text style={[styles.achievementXPText, { color: '#F59E0B' }]}>{achievement.xp} XP</Text>
            </View>
          </View>
        ))}
      </View>
    </ScrollView>
  );

  const renderLearningPath = () => (
    <ScrollView style={styles.section}>
      {!learningPath ? (
        <View style={styles.pathForm}>
          <Text style={[styles.formLabel, { color: colors.textMuted }]}>Your Level</Text>
          <View style={styles.levelSelector}>
            {(['beginner', 'intermediate', 'advanced'] as const).map((level) => (
              <TouchableOpacity
                key={level}
                style={[styles.levelBtn, { backgroundColor: pathLevel === level ? colors.primary : colors.surfaceAlt }]}
                onPress={() => setPathLevel(level)}
              >
                <Text style={[styles.levelText, { color: pathLevel === level ? '#FFF' : colors.text }]}>{level}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={[styles.formLabel, { color: colors.textMuted }]}>Your Goals</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            {['web_development', 'data_science', 'mobile_apps', 'game_dev', 'ai_ml'].map((goal) => (
              <TouchableOpacity
                key={goal}
                style={[styles.goalChip, { backgroundColor: pathGoals.includes(goal) ? colors.secondary : colors.surfaceAlt }]}
                onPress={() => {
                  if (pathGoals.includes(goal)) {
                    setPathGoals(pathGoals.filter(g => g !== goal));
                  } else {
                    setPathGoals([...pathGoals, goal]);
                  }
                }}
              >
                <Text style={[styles.goalText, { color: pathGoals.includes(goal) ? '#FFF' : colors.text }]}>
                  {goal.replace('_', ' ')}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <TouchableOpacity
            style={[styles.generatePathBtn, { backgroundColor: colors.primary }]}
            onPress={generateLearningPath}
            disabled={isLoading}
          >
            {isLoading ? (
              <ActivityIndicator color="#FFF" />
            ) : (
              <>
                <Ionicons name="map" size={20} color="#FFF" />
                <Text style={styles.generatePathText}>Generate My Path</Text>
              </>
            )}
          </TouchableOpacity>
        </View>
      ) : (
        <View style={styles.pathResult}>
          <TouchableOpacity
            style={[styles.resetPathBtn, { backgroundColor: colors.surfaceAlt }]}
            onPress={() => setLearningPath(null)}
          >
            <Ionicons name="refresh" size={18} color={colors.primary} />
            <Text style={[styles.resetPathText, { color: colors.primary }]}>Generate New Path</Text>
          </TouchableOpacity>
          <Text style={[styles.pathText, { color: colors.text }]}>{learningPath}</Text>
        </View>
      )}
    </ScrollView>
  );

  const renderChallengeView = () => (
    <View style={styles.challengeView}>
      <View style={[styles.challengeViewHeader, { backgroundColor: colors.surfaceAlt }]}>
        <TouchableOpacity onPress={() => { setSelectedChallenge(null); setSubmissionResult(null); }}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={[styles.challengeViewTitle, { color: colors.text }]}>{selectedChallenge.title}</Text>
        <View style={[styles.xpBadge, { backgroundColor: '#F59E0B20' }]}>
          <Text style={[styles.xpText, { color: '#F59E0B' }]}>{selectedChallenge.xp} XP</Text>
        </View>
      </View>

      <ScrollView style={styles.challengeContent}>
        <Text style={[styles.challengeDescription, { color: colors.text }]}>{selectedChallenge.description}</Text>
        
        {selectedChallenge.hints && (
          <View style={[styles.hintsBox, { backgroundColor: colors.surfaceAlt }]}>
            <Text style={[styles.hintsTitle, { color: colors.textMuted }]}>Hints</Text>
            {selectedChallenge.hints.map((hint: string, idx: number) => (
              <Text key={idx} style={[styles.hintText, { color: colors.text }]}>• {hint}</Text>
            ))}
          </View>
        )}

        <Text style={[styles.codeLabel, { color: colors.textMuted }]}>Your Solution</Text>
        <TextInput
          style={[styles.codeInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
          multiline
          value={userCode}
          onChangeText={setUserCode}
          placeholder="Write your code here..."
          placeholderTextColor={colors.textMuted}
        />

        <TouchableOpacity
          style={[styles.submitBtn, { backgroundColor: colors.primary }]}
          onPress={submitChallenge}
          disabled={isLoading}
        >
          {isLoading ? (
            <ActivityIndicator color="#FFF" />
          ) : (
            <>
              <Ionicons name="paper-plane" size={20} color="#FFF" />
              <Text style={styles.submitBtnText}>Submit Solution</Text>
            </>
          )}
        </TouchableOpacity>

        {submissionResult && (
          <View style={[styles.resultBox, { backgroundColor: submissionResult.passed ? '#10B98120' : '#EF444420' }]}>
            <View style={styles.resultHeader}>
              <Ionicons
                name={submissionResult.passed ? 'checkmark-circle' : 'close-circle'}
                size={28}
                color={submissionResult.passed ? '#10B981' : '#EF4444'}
              />
              <Text style={[styles.resultTitle, { color: submissionResult.passed ? '#10B981' : '#EF4444' }]}>
                {submissionResult.passed ? 'Passed!' : 'Try Again'}
              </Text>
              <Text style={[styles.resultScore, { color: colors.text }]}>Score: {submissionResult.score}/100</Text>
            </View>
            {submissionResult.xp_earned && (
              <View style={[styles.xpEarned, { backgroundColor: '#F59E0B20' }]}>
                <Ionicons name="star" size={20} color="#F59E0B" />
                <Text style={[styles.xpEarnedText, { color: '#F59E0B' }]}>+{submissionResult.xp_earned} XP Earned!</Text>
              </View>
            )}
            <Text style={[styles.feedbackText, { color: colors.text }]}>{submissionResult.feedback}</Text>
          </View>
        )}
      </ScrollView>
    </View>
  );

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <View style={[styles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
            <Ionicons name="close" size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerTitle}>
            <Ionicons name="game-controller" size={24} color="#10B981" />
            <Text style={[styles.title, { color: colors.text }]}>Code Academy</Text>
          </View>
          <View style={{ width: 40 }} />
        </View>

        {selectedChallenge ? renderChallengeView() : (
          <>
            {renderTabs()}
            {activeTab === 'challenges' && renderChallenges()}
            {activeTab === 'daily' && renderDailyChallenge()}
            {activeTab === 'achievements' && renderAchievements()}
            {activeTab === 'learn' && renderLearningPath()}
          </>
        )}
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1 },
  closeBtn: { width: 40, height: 40, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: 18, fontWeight: '700' },
  tabBar: { flexDirection: 'row', borderBottomWidth: 1 },
  tab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 12, gap: 6 },
  tabText: { fontSize: 12, fontWeight: '600' },
  section: { flex: 1, padding: 16 },
  filtersRow: { marginBottom: 16 },
  filterChip: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20, marginRight: 8 },
  filterText: { fontSize: 13, fontWeight: '600' },
  filterDivider: { width: 1, backgroundColor: '#333', marginHorizontal: 8 },
  challengesList: { flex: 1 },
  challengeCard: { padding: 16, borderRadius: 12, marginBottom: 12 },
  challengeHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  xpBadge: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12, gap: 4 },
  xpText: { fontSize: 12, fontWeight: '700' },
  timeLimit: { fontSize: 12 },
  challengeTitle: { fontSize: 16, fontWeight: '700', marginBottom: 4 },
  challengeDesc: { fontSize: 13, lineHeight: 20 },
  dailyCard: { padding: 20, borderRadius: 16, borderWidth: 2 },
  dailyHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 12, gap: 12 },
  dailyBadge: { width: 48, height: 48, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
  dailyInfo: { flex: 1 },
  dailyLabel: { fontSize: 11, fontWeight: '600', letterSpacing: 1 },
  dailyTitle: { fontSize: 18, fontWeight: '800' },
  bonusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  bonusText: { fontSize: 11, fontWeight: '700' },
  dailyDesc: { fontSize: 14, lineHeight: 22, marginBottom: 12 },
  dailyMeta: { flexDirection: 'row', gap: 8, marginBottom: 16 },
  metaTag: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16 },
  metaText: { fontSize: 12, fontWeight: '600' },
  startBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 14, borderRadius: 12, gap: 8 },
  startBtnText: { color: '#FFF', fontSize: 16, fontWeight: '700' },
  achievementsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  achievementCard: { width: (SCREEN_WIDTH - 48) / 2, padding: 16, borderRadius: 12, alignItems: 'center' },
  achievementIcon: { fontSize: 36, marginBottom: 8 },
  achievementName: { fontSize: 14, fontWeight: '700', textAlign: 'center' },
  achievementDesc: { fontSize: 11, textAlign: 'center', marginTop: 4 },
  achievementXP: { marginTop: 8, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10 },
  achievementXPText: { fontSize: 11, fontWeight: '700' },
  pathForm: { gap: 20 },
  formLabel: { fontSize: 13, fontWeight: '600', marginBottom: 8 },
  levelSelector: { flexDirection: 'row', gap: 10 },
  levelBtn: { flex: 1, paddingVertical: 12, borderRadius: 10, alignItems: 'center' },
  levelText: { fontSize: 14, fontWeight: '600' },
  goalChip: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 20, marginRight: 10 },
  goalText: { fontSize: 13, fontWeight: '600', textTransform: 'capitalize' },
  generatePathBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 16, borderRadius: 12, gap: 10 },
  generatePathText: { color: '#FFF', fontSize: 16, fontWeight: '700' },
  pathResult: { gap: 16 },
  resetPathBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, alignSelf: 'flex-start', paddingHorizontal: 16, paddingVertical: 10, borderRadius: 20 },
  resetPathText: { fontSize: 14, fontWeight: '600' },
  pathText: { fontSize: 14, lineHeight: 24 },
  challengeView: { flex: 1 },
  challengeViewHeader: { flexDirection: 'row', alignItems: 'center', padding: 16, gap: 12 },
  challengeViewTitle: { flex: 1, fontSize: 16, fontWeight: '700' },
  challengeContent: { flex: 1, padding: 16 },
  challengeDescription: { fontSize: 15, lineHeight: 24, marginBottom: 16 },
  hintsBox: { padding: 16, borderRadius: 12, marginBottom: 16 },
  hintsTitle: { fontSize: 13, fontWeight: '600', marginBottom: 8 },
  hintText: { fontSize: 13, lineHeight: 22 },
  codeLabel: { fontSize: 13, fontWeight: '600', marginBottom: 8 },
  codeInput: { minHeight: 200, padding: 16, borderRadius: 12, borderWidth: 1, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', fontSize: 13, textAlignVertical: 'top' },
  submitBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 16, borderRadius: 12, gap: 10, marginTop: 16 },
  submitBtnText: { color: '#FFF', fontSize: 16, fontWeight: '700' },
  resultBox: { padding: 16, borderRadius: 12, marginTop: 16 },
  resultHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 },
  resultTitle: { flex: 1, fontSize: 18, fontWeight: '800' },
  resultScore: { fontSize: 14, fontWeight: '600' },
  xpEarned: { flexDirection: 'row', alignItems: 'center', gap: 8, alignSelf: 'flex-start', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, marginBottom: 12 },
  xpEarnedText: { fontSize: 14, fontWeight: '700' },
  feedbackText: { fontSize: 14, lineHeight: 22 },
});
