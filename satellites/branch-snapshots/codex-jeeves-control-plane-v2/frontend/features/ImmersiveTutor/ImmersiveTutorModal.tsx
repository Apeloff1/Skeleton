/**
 * Immersive Tutor Modal v14.5 - Jeeves Synergy Learning System
 * 
 * Full integration of:
 * - Jeeves AI Tutor with personality and voice
 * - Zone of Proximal Development (ZPD) tracking
 * - Gamification (XP, Levels, Achievements, Daily Quests)
 * - Managed learning curve with 4 stages
 * - Adaptive content based on energy/time/emotional state
 * - Socratic dialogue for deep understanding
 */

import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Dimensions,
  RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';

import { apiFetch } from '../../utils/apiController';
const { width: SCREEN_WIDTH } = Dimensions.get('window');
const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface ImmersiveTutorModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  userId?: string;
}

interface LearningStage {
  id: string;
  name: string;
  config: {
    hours_range: [number, number | string];
    scaffolding_level: string;
    difficulty_cap: number;
    xp_multiplier: number;
    focus: string;
    jeeves_style: string;
    goals: string[];
  };
  expressions_sample: string[];
}

interface Achievement {
  id: string;
  name: string;
  description: string;
  xp_reward: number;
  icon: string;
  rarity: string;
}

interface DailyQuest {
  id: string;
  name: string;
  description: string;
  xp_reward: number;
  difficulty: string;
  quest_type: string;
  estimated_time: number;
  target_count: number;
  progress?: number;
  completed?: boolean;
}

interface UserProgress {
  level: number;
  xp: number;
  xp_to_next: number;
  streak_days: number;
  total_hours: number;
  current_stage: string;
  stage_progress: number;
}

// Stage Badge Component
const StageBadge: React.FC<{
  stage: LearningStage;
  isActive: boolean;
  colors: any;
  onPress: () => void;
}> = ({ stage, isActive, colors, onPress }) => {
  const stageColors: Record<string, string> = {
    onboarding: '#10B981',
    foundation: '#3B82F6',
    growth: '#8B5CF6',
    mastery: '#F59E0B',
  };
  
  const stageIcons: Record<string, string> = {
    onboarding: 'leaf',
    foundation: 'construct',
    growth: 'trending-up',
    mastery: 'trophy',
  };
  
  const color = stageColors[stage.id] || colors.primary;
  const icon = stageIcons[stage.id] || 'star';

  return (
    <TouchableOpacity
      style={[
        styles.stageBadge,
        { 
          backgroundColor: isActive ? color + '20' : colors.surfaceAlt,
          borderColor: isActive ? color : 'transparent',
          borderWidth: isActive ? 2 : 0,
        }
      ]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <View style={[styles.stageIconContainer, { backgroundColor: color + '30' }]}>
        <Ionicons name={icon as any} size={24} color={color} />
      </View>
      <Text style={[styles.stageName, { color: colors.text }]}>{stage.name}</Text>
      <Text style={[styles.stageHours, { color: colors.textMuted }]}>
        {stage.config.hours_range[0]}-{stage.config.hours_range[1] === 'Infinity' ? '∞' : stage.config.hours_range[1]}h
      </Text>
      {isActive && (
        <View style={[styles.activeIndicator, { backgroundColor: color }]} />
      )}
    </TouchableOpacity>
  );
};

// Achievement Card Component
const AchievementCard: React.FC<{
  achievement: Achievement;
  colors: any;
  unlocked?: boolean;
}> = ({ achievement, colors, unlocked = false }) => {
  const rarityColors: Record<string, string> = {
    common: '#9CA3AF',
    uncommon: '#10B981',
    rare: '#3B82F6',
    epic: '#8B5CF6',
    legendary: '#F59E0B',
  };
  
  const rarityColor = rarityColors[achievement.rarity] || colors.textMuted;

  return (
    <View
      style={[
        styles.achievementCard,
        { 
          backgroundColor: unlocked ? colors.surfaceAlt : colors.surface,
          opacity: unlocked ? 1 : 0.6,
        }
      ]}
    >
      <View style={[
        styles.achievementIcon,
        { backgroundColor: rarityColor + (unlocked ? '30' : '10') }
      ]}>
        <Ionicons
          name={achievement.icon as any}
          size={24}
          color={unlocked ? rarityColor : colors.textMuted}
        />
      </View>
      <View style={styles.achievementInfo}>
        <Text style={[styles.achievementName, { color: unlocked ? colors.text : colors.textMuted }]}>
          {achievement.name}
        </Text>
        <Text style={[styles.achievementDesc, { color: colors.textMuted }]} numberOfLines={1}>
          {achievement.description}
        </Text>
      </View>
      <View style={[styles.xpBadge, { backgroundColor: rarityColor + '20' }]}>
        <Text style={[styles.xpText, { color: rarityColor }]}>+{achievement.xp_reward} XP</Text>
      </View>
    </View>
  );
};

// Daily Quest Card Component
const QuestCard: React.FC<{
  quest: DailyQuest;
  colors: any;
  onComplete: () => void;
}> = ({ quest, colors, onComplete }) => {
  const difficultyColors: Record<string, string> = {
    easy: '#10B981',
    medium: '#F59E0B',
    hard: '#EF4444',
  };
  
  const questIcons: Record<string, string> = {
    practice: 'code-slash',
    streak: 'flame',
    exploration: 'compass',
    challenge: 'flash',
    review: 'refresh',
  };
  
  const color = difficultyColors[quest.difficulty] || colors.primary;
  const icon = questIcons[quest.quest_type] || 'star';
  const progress = (quest.progress || 0) / quest.target_count;

  return (
    <TouchableOpacity
      style={[styles.questCard, { backgroundColor: colors.surfaceAlt }]}
      onPress={onComplete}
      activeOpacity={0.7}
      disabled={quest.completed}
    >
      <View style={[styles.questIconContainer, { backgroundColor: color + '20' }]}>
        <Ionicons name={icon as any} size={20} color={color} />
      </View>
      <View style={styles.questInfo}>
        <View style={styles.questHeader}>
          <Text style={[styles.questName, { color: colors.text }]}>{quest.name}</Text>
          <View style={[styles.difficultyBadge, { backgroundColor: color + '20' }]}>
            <Text style={[styles.difficultyText, { color }]}>{quest.difficulty}</Text>
          </View>
        </View>
        <Text style={[styles.questDesc, { color: colors.textMuted }]} numberOfLines={1}>
          {quest.description}
        </Text>
        <View style={styles.questMeta}>
          <View style={[styles.progressBar, { backgroundColor: colors.surface }]}>
            <View 
              style={[
                styles.progressFill, 
                { backgroundColor: color, width: `${progress * 100}%` }
              ]} 
            />
          </View>
          <Text style={[styles.questXp, { color }]}>+{quest.xp_reward} XP</Text>
        </View>
      </View>
      {quest.completed && (
        <View style={[styles.completedBadge, { backgroundColor: '#10B981' }]}>
          <Ionicons name="checkmark" size={16} color="#fff" />
        </View>
      )}
    </TouchableOpacity>
  );
};

// Jeeves Message Component
const JeevesMessage: React.FC<{
  message: string;
  style?: string;
  colors: any;
}> = ({ message, style = 'encouraging', colors }) => {
  const styleColors: Record<string, string> = {
    encouraging: '#10B981',
    challenging: '#F59E0B',
    supportive: '#3B82F6',
    celebratory: '#8B5CF6',
    analytical: '#6366F1',
    playful: '#EC4899',
  };
  
  const color = styleColors[style] || colors.primary;

  return (
    <View style={[styles.jeevesMessage, { backgroundColor: color + '10', borderLeftColor: color }]}>
      <View style={styles.jeevesAvatar}>
        <Ionicons name="person-circle" size={36} color={color} />
      </View>
      <View style={styles.jeevesContent}>
        <Text style={[styles.jeevesName, { color }]}>Jeeves</Text>
        <Text style={[styles.jeevesText, { color: colors.text }]}>{message}</Text>
      </View>
    </View>
  );
};

// XP Progress Component
const XPProgress: React.FC<{
  level: number;
  xp: number;
  xpToNext: number;
  colors: any;
}> = ({ level, xp, xpToNext, colors }) => {
  const progress = xpToNext > 0 ? (xp % xpToNext) / xpToNext : 0;

  return (
    <View style={[styles.xpProgress, { backgroundColor: colors.surfaceAlt }]}>
      <View style={styles.levelBadge}>
        <Text style={[styles.levelText, { color: colors.primary }]}>Lv.{level}</Text>
      </View>
      <View style={styles.xpBarContainer}>
        <View style={[styles.xpBar, { backgroundColor: colors.surface }]}>
          <View 
            style={[
              styles.xpFill, 
              { backgroundColor: colors.primary, width: `${progress * 100}%` }
            ]} 
          />
        </View>
        <Text style={[styles.xpLabel, { color: colors.textMuted }]}>
          {xp} / {xpToNext} XP
        </Text>
      </View>
    </View>
  );
};

// Main Immersive Tutor Modal
export const ImmersiveTutorModal: React.FC<ImmersiveTutorModalProps> = ({
  visible,
  onClose,
  colors,
  userId = 'user_1',
}) => {
  // State
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview' | 'quests' | 'achievements' | 'stages'>('overview');
  const [stages, setStages] = useState<LearningStage[]>([]);
  const [achievements, setAchievements] = useState<Achievement[]>([]);
  const [dailyQuests, setDailyQuests] = useState<DailyQuest[]>([]);
  const [synergyData, setSynergyData] = useState<any>(null);
  const [jeevesGreeting, setJeevesGreeting] = useState<string>('');
  const [userProgress, setUserProgress] = useState<UserProgress>({
    level: 1,
    xp: 0,
    xp_to_next: 100,
    streak_days: 0,
    total_hours: 0,
    current_stage: 'onboarding',
    stage_progress: 0,
  });
  const [error, setError] = useState<string | null>(null);

  // Fetch all data
  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch stages
      const stagesRes = await apiFetch(`${API_BASE}/api/jeeves-synergy/stages/all`);
      if (stagesRes.ok) {
        const stagesData = await stagesRes.json();
        setStages(stagesData.stages || []);
      }

      // Fetch achievements
      const achievementsRes = await apiFetch(`${API_BASE}/api/immersive-tutor/achievements/list`);
      if (achievementsRes.ok) {
        const achievementsData = await achievementsRes.json();
        setAchievements(achievementsData.achievements || []);
      }

      // Fetch daily quests
      const questsRes = await apiFetch(
        `${API_BASE}/api/immersive-tutor/quest/daily?user_level=${userProgress.level}&streak_days=${userProgress.streak_days}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        }
      );
      if (questsRes.ok) {
        const questsData = await questsRes.json();
        setDailyQuests(questsData.quests || []);
      }

      // Fetch synergy analysis
      const synergyRes = await apiFetch(`${API_BASE}/api/jeeves-synergy/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          total_hours: userProgress.total_hours,
          domains_explored: ['programming', 'algorithms'],
          achievements_earned: 5,
          streak_days: userProgress.streak_days,
          mastery_scores: { programming: 0.6, algorithms: 0.4 },
        }),
      });
      if (synergyRes.ok) {
        const synergyResult = await synergyRes.json();
        setSynergyData(synergyResult);
        if (synergyResult.jeeves_says) {
          setJeevesGreeting(synergyResult.jeeves_says);
        }
        if (synergyResult.current_stage) {
          setUserProgress(prev => ({
            ...prev,
            current_stage: synergyResult.current_stage,
            stage_progress: synergyResult.stage_progress || 0,
          }));
        }
      }

      // Fetch Jeeves greeting
      const greetRes = await apiFetch(`${API_BASE}/api/jeeves-voice/greet`);
      if (greetRes.ok) {
        const greetData = await greetRes.json();
        if (greetData.message) {
          setJeevesGreeting(greetData.message);
        }
      }

    } catch (err) {
      console.error('Failed to fetch immersive tutor data:', err);
      setError('Failed to load data. Please try again.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [userId, userProgress.level, userProgress.streak_days, userProgress.total_hours]);

  useEffect(() => {
    if (visible) {
      fetchData();
    }
  }, [visible, fetchData]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const handleTabChange = (tab: typeof activeTab) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setActiveTab(tab);
  };

  const renderTabs = () => (
    <View style={[styles.tabBar, { backgroundColor: colors.surface }]}>
      {(['overview', 'quests', 'achievements', 'stages'] as const).map((tab) => {
        const icons: Record<string, string> = {
          overview: 'home',
          quests: 'flash',
          achievements: 'trophy',
          stages: 'layers',
        };
        const isActive = activeTab === tab;
        
        return (
          <TouchableOpacity
            key={tab}
            style={[
              styles.tab,
              isActive && { borderBottomColor: colors.primary, borderBottomWidth: 2 }
            ]}
            onPress={() => handleTabChange(tab)}
          >
            <Ionicons
              name={icons[tab] as any}
              size={20}
              color={isActive ? colors.primary : colors.textMuted}
            />
            <Text style={[
              styles.tabText,
              { color: isActive ? colors.primary : colors.textMuted }
            ]}>
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );

  const renderOverview = () => (
    <View style={styles.overviewContainer}>
      {/* Jeeves Greeting */}
      {jeevesGreeting && (
        <JeevesMessage 
          message={jeevesGreeting} 
          style={synergyData?.insights?.[0]?.type || 'encouraging'}
          colors={colors} 
        />
      )}

      {/* XP Progress */}
      <XPProgress
        level={userProgress.level}
        xp={userProgress.xp}
        xpToNext={userProgress.xp_to_next}
        colors={colors}
      />

      {/* Quick Stats */}
      <View style={styles.quickStats}>
        <View style={[styles.statCard, { backgroundColor: colors.surfaceAlt }]}>
          <Ionicons name="flame" size={24} color="#F59E0B" />
          <Text style={[styles.statValue, { color: colors.text }]}>{userProgress.streak_days}</Text>
          <Text style={[styles.statLabel, { color: colors.textMuted }]}>Day Streak</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: colors.surfaceAlt }]}>
          <Ionicons name="time" size={24} color="#3B82F6" />
          <Text style={[styles.statValue, { color: colors.text }]}>{userProgress.total_hours.toFixed(1)}</Text>
          <Text style={[styles.statLabel, { color: colors.textMuted }]}>Total Hours</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: colors.surfaceAlt }]}>
          <Ionicons name="trending-up" size={24} color="#10B981" />
          <Text style={[styles.statValue, { color: colors.text }]}>{userProgress.stage_progress.toFixed(0)}%</Text>
          <Text style={[styles.statLabel, { color: colors.textMuted }]}>Stage Progress</Text>
        </View>
      </View>

      {/* Current Stage */}
      {synergyData && (
        <View style={[styles.stageCard, { backgroundColor: colors.surfaceAlt }]}>
          <View style={styles.stageHeader}>
            <Text style={[styles.stageTitle, { color: colors.text }]}>Current Stage</Text>
            <View style={[styles.stageBadgeSmall, { backgroundColor: colors.primary + '20' }]}>
              <Text style={[styles.stageBadgeText, { color: colors.primary }]}>
                {userProgress.current_stage.toUpperCase()}
              </Text>
            </View>
          </View>
          <Text style={[styles.stageDesc, { color: colors.textMuted }]}>
            {synergyData.hours_to_next_stage > 0 
              ? `${synergyData.hours_to_next_stage.toFixed(1)} hours to next stage`
              : 'Mastery achieved!'}
          </Text>
          
          {/* Stage Progress Bar */}
          <View style={[styles.stageProgressBar, { backgroundColor: colors.surface }]}>
            <View 
              style={[
                styles.stageProgressFill, 
                { backgroundColor: colors.primary, width: `${userProgress.stage_progress}%` }
              ]} 
            />
          </View>
        </View>
      )}

      {/* Today's Goals */}
      <View style={styles.goalsSection}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>{"Today's Goals"}</Text>
        {dailyQuests.slice(0, 3).map((quest) => (
          <QuestCard
            key={quest.id}
            quest={quest}
            colors={colors}
            onComplete={() => {}}
          />
        ))}
      </View>
    </View>
  );

  const renderQuests = () => (
    <View style={styles.questsContainer}>
      <Text style={[styles.sectionTitle, { color: colors.text }]}>Daily Quests</Text>
      <Text style={[styles.sectionSubtitle, { color: colors.textMuted }]}>
        Complete quests to earn XP and maintain your streak
      </Text>
      {dailyQuests.map((quest) => (
        <QuestCard
          key={quest.id}
          quest={quest}
          colors={colors}
          onComplete={() => {
            Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          }}
        />
      ))}
    </View>
  );

  const renderAchievements = () => (
    <View style={styles.achievementsContainer}>
      <Text style={[styles.sectionTitle, { color: colors.text }]}>Achievements</Text>
      <Text style={[styles.sectionSubtitle, { color: colors.textMuted }]}>
        Unlock achievements to showcase your progress
      </Text>
      {achievements.map((achievement) => (
        <AchievementCard
          key={achievement.id}
          achievement={achievement}
          colors={colors}
          unlocked={Math.random() > 0.5} // Mock - replace with actual user data
        />
      ))}
    </View>
  );

  const renderStages = () => (
    <View style={styles.stagesContainer}>
      <Text style={[styles.sectionTitle, { color: colors.text }]}>Learning Journey</Text>
      <Text style={[styles.sectionSubtitle, { color: colors.textMuted }]}>
        Your path from beginner to master
      </Text>
      <View style={styles.stagesGrid}>
        {stages.map((stage) => (
          <StageBadge
            key={stage.id}
            stage={stage}
            isActive={userProgress.current_stage === stage.id}
            colors={colors}
            onPress={() => {
              Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
            }}
          />
        ))}
      </View>
      
      {/* Stage Details */}
      {stages.filter(s => s.id === userProgress.current_stage).map((stage) => (
        <View key={stage.id} style={[styles.stageDetails, { backgroundColor: colors.surfaceAlt }]}>
          <Text style={[styles.stageDetailTitle, { color: colors.text }]}>
            {stage.name} Stage
          </Text>
          <View style={styles.stageGoals}>
            {stage.config.goals.map((goal, index) => (
              <View key={index} style={styles.goalItem}>
                <Ionicons name="checkmark-circle" size={16} color={colors.primary} />
                <Text style={[styles.goalText, { color: colors.text }]}>{goal}</Text>
              </View>
            ))}
          </View>
          <View style={styles.stageConfig}>
            <View style={styles.configItem}>
              <Text style={[styles.configLabel, { color: colors.textMuted }]}>Scaffolding</Text>
              <Text style={[styles.configValue, { color: colors.text }]}>{stage.config.scaffolding_level}</Text>
            </View>
            <View style={styles.configItem}>
              <Text style={[styles.configLabel, { color: colors.textMuted }]}>XP Multiplier</Text>
              <Text style={[styles.configValue, { color: colors.text }]}>{stage.config.xp_multiplier}x</Text>
            </View>
            <View style={styles.configItem}>
              <Text style={[styles.configLabel, { color: colors.textMuted }]}>Focus</Text>
              <Text style={[styles.configValue, { color: colors.text }]}>{stage.config.focus.replace('_', ' ')}</Text>
            </View>
          </View>
        </View>
      ))}
    </View>
  );

  const renderContent = () => {
    switch (activeTab) {
      case 'overview':
        return renderOverview();
      case 'quests':
        return renderQuests();
      case 'achievements':
        return renderAchievements();
      case 'stages':
        return renderStages();
      default:
        return renderOverview();
    }
  };

  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        {/* Header */}
        <View style={[styles.header, { backgroundColor: colors.surface }]}>
          <TouchableOpacity onPress={onClose} style={styles.closeButton}>
            <Ionicons name="close" size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerTitle}>
            <Ionicons name="school" size={24} color={colors.primary} />
            <Text style={[styles.title, { color: colors.text }]}>Immersive Tutor</Text>
          </View>
          <TouchableOpacity onPress={onRefresh} style={styles.refreshButton}>
            <Ionicons name="refresh" size={24} color={colors.textMuted} />
          </TouchableOpacity>
        </View>

        {/* Tabs */}
        {renderTabs()}

        {/* Content */}
        <ScrollView
          style={styles.content}
          contentContainerStyle={styles.contentContainer}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
          }
        >
          {loading ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color={colors.primary} />
              <Text style={[styles.loadingText, { color: colors.textMuted }]}>
                Loading your learning journey...
              </Text>
            </View>
          ) : error ? (
            <View style={styles.errorContainer}>
              <Ionicons name="alert-circle" size={48} color={colors.error} />
              <Text style={[styles.errorText, { color: colors.error }]}>{error}</Text>
              <TouchableOpacity
                style={[styles.retryButton, { backgroundColor: colors.primary }]}
                onPress={fetchData}
              >
                <Text style={styles.retryText}>Try Again</Text>
              </TouchableOpacity>
            </View>
          ) : (
            renderContent()
          )}
        </ScrollView>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.1)',
  },
  closeButton: {
    padding: 8,
  },
  headerTitle: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
  },
  refreshButton: {
    padding: 8,
  },
  tabBar: {
    flexDirection: 'row',
    paddingHorizontal: 8,
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    gap: 4,
  },
  tabText: {
    fontSize: 12,
    fontWeight: '600',
  },
  content: {
    flex: 1,
  },
  contentContainer: {
    padding: 16,
    paddingBottom: 32,
  },
  loadingContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 64,
  },
  loadingText: {
    marginTop: 16,
    fontSize: 14,
  },
  errorContainer: {
    alignItems: 'center',
    paddingVertical: 64,
  },
  errorText: {
    marginTop: 16,
    fontSize: 14,
    textAlign: 'center',
  },
  retryButton: {
    marginTop: 16,
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
  },
  retryText: {
    color: '#fff',
    fontWeight: '600',
  },
  
  // Overview styles
  overviewContainer: {
    gap: 16,
  },
  quickStats: {
    flexDirection: 'row',
    gap: 12,
  },
  statCard: {
    flex: 1,
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 24,
    fontWeight: '700',
    marginTop: 8,
  },
  statLabel: {
    fontSize: 12,
    marginTop: 4,
  },
  stageCard: {
    padding: 16,
    borderRadius: 12,
  },
  stageHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  stageTitle: {
    fontSize: 16,
    fontWeight: '600',
  },
  stageBadgeSmall: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },
  stageBadgeText: {
    fontSize: 10,
    fontWeight: '700',
  },
  stageDesc: {
    fontSize: 13,
    marginTop: 8,
  },
  stageProgressBar: {
    height: 6,
    borderRadius: 3,
    marginTop: 12,
    overflow: 'hidden',
  },
  stageProgressFill: {
    height: '100%',
    borderRadius: 3,
  },
  goalsSection: {
    gap: 12,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 4,
  },
  sectionSubtitle: {
    fontSize: 13,
    marginBottom: 12,
  },

  // Jeeves Message
  jeevesMessage: {
    flexDirection: 'row',
    padding: 16,
    borderRadius: 12,
    borderLeftWidth: 4,
    gap: 12,
  },
  jeevesAvatar: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  jeevesContent: {
    flex: 1,
  },
  jeevesName: {
    fontSize: 12,
    fontWeight: '700',
    marginBottom: 4,
  },
  jeevesText: {
    fontSize: 14,
    lineHeight: 20,
  },

  // XP Progress
  xpProgress: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
    gap: 12,
  },
  levelBadge: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(99, 102, 241, 0.2)',
  },
  levelText: {
    fontSize: 14,
    fontWeight: '700',
  },
  xpBarContainer: {
    flex: 1,
  },
  xpBar: {
    height: 8,
    borderRadius: 4,
    overflow: 'hidden',
  },
  xpFill: {
    height: '100%',
    borderRadius: 4,
  },
  xpLabel: {
    fontSize: 11,
    marginTop: 4,
  },

  // Stage Badge
  stageBadge: {
    width: (SCREEN_WIDTH - 48) / 2,
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
    position: 'relative',
  },
  stageIconContainer: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 8,
  },
  stageName: {
    fontSize: 14,
    fontWeight: '600',
  },
  stageHours: {
    fontSize: 12,
    marginTop: 4,
  },
  activeIndicator: {
    position: 'absolute',
    top: 8,
    right: 8,
    width: 8,
    height: 8,
    borderRadius: 4,
  },

  // Achievement Card
  achievementCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderRadius: 12,
    marginBottom: 8,
    gap: 12,
  },
  achievementIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  achievementInfo: {
    flex: 1,
  },
  achievementName: {
    fontSize: 14,
    fontWeight: '600',
  },
  achievementDesc: {
    fontSize: 12,
    marginTop: 2,
  },
  xpBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },
  xpText: {
    fontSize: 11,
    fontWeight: '600',
  },

  // Quest Card
  questCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderRadius: 12,
    marginBottom: 8,
    gap: 12,
  },
  questIconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  questInfo: {
    flex: 1,
  },
  questHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  questName: {
    fontSize: 14,
    fontWeight: '600',
    flex: 1,
  },
  difficultyBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  difficultyText: {
    fontSize: 10,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  questDesc: {
    fontSize: 12,
    marginTop: 2,
  },
  questMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 8,
    gap: 8,
  },
  progressBar: {
    flex: 1,
    height: 4,
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: 2,
  },
  questXp: {
    fontSize: 11,
    fontWeight: '600',
  },
  completedBadge: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },

  // Stages Container
  stagesContainer: {
    gap: 16,
  },
  stagesGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  stageDetails: {
    padding: 16,
    borderRadius: 12,
    marginTop: 8,
  },
  stageDetailTitle: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 12,
  },
  stageGoals: {
    gap: 8,
  },
  goalItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  goalText: {
    fontSize: 13,
    flex: 1,
  },
  stageConfig: {
    flexDirection: 'row',
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.1)',
  },
  configItem: {
    flex: 1,
    alignItems: 'center',
  },
  configLabel: {
    fontSize: 11,
    marginBottom: 4,
  },
  configValue: {
    fontSize: 13,
    fontWeight: '600',
    textTransform: 'capitalize',
  },

  // Quests & Achievements Containers
  questsContainer: {
    gap: 8,
  },
  achievementsContainer: {
    gap: 8,
  },
});

export default ImmersiveTutorModal;
