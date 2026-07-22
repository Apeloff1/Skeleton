// ============================================================================
// CODEDOCK QUANTUM NEXUS - Learning Intelligence Dashboard
// Mastery heatmaps, knowledge-gap predictions, achievement tracking
// ============================================================================

import React, { useState, useMemo, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Dimensions, Modal,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Rect, Text as SvgText, G } from 'react-native-svg';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

// ============================================================================
// TYPES
// ============================================================================
export interface SkillLevel {
  skill: string;
  category: string;
  level: number; // 0-100
  practiceCount: number;
  lastPracticed?: Date;
  trend: 'improving' | 'stable' | 'declining';
}

export interface KnowledgeGap {
  skill: string;
  prerequisite: string;
  confidence: number;
  recommendation: string;
}

export interface LearningStreak {
  current: number;
  longest: number;
  lastActiveDate: Date;
}

export interface Achievement {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  unlockedAt?: Date;
  progress?: number;
  maxProgress?: number;
}

export interface LearningStats {
  totalPracticeMinutes: number;
  totalExercisesCompleted: number;
  averageAccuracy: number;
  languagesPracticed: string[];
  conceptsMastered: number;
  streak: LearningStreak;
}

// ============================================================================
// DEFAULT DATA
// ============================================================================
const SKILL_CATEGORIES = [
  { name: 'Syntax', skills: ['Variables', 'Functions', 'Classes', 'Loops', 'Conditionals', 'Operators'] },
  { name: 'Data Structures', skills: ['Arrays', 'Lists', 'Dictionaries', 'Sets', 'Trees', 'Graphs'] },
  { name: 'Algorithms', skills: ['Sorting', 'Searching', 'Recursion', 'Dynamic Programming', 'Greedy'] },
  { name: 'Memory', skills: ['Pointers', 'References', 'Allocation', 'Garbage Collection', 'Lifetimes'] },
  { name: 'Concurrency', skills: ['Threads', 'Async/Await', 'Locks', 'Channels', 'Atomics'] },
  { name: 'Optimization', skills: ['Complexity', 'Profiling', 'Caching', 'Vectorization', 'Inlining'] },
];

const DEFAULT_ACHIEVEMENTS: Achievement[] = [
  { id: 'first_run', name: 'First Compile', description: 'Run your first program', icon: 'rocket', color: '#6366F1', unlockedAt: new Date() },
  { id: 'syntax_master', name: 'Syntax Master', description: 'Master all basic syntax', icon: 'code-slash', color: '#8B5CF6', progress: 4, maxProgress: 6 },
  { id: 'algorithm_ace', name: 'Algorithm Ace', description: 'Complete 10 algorithm challenges', icon: 'trophy', color: '#F59E0B', progress: 3, maxProgress: 10 },
  { id: 'debugger', name: 'Bug Hunter', description: 'Fix 25 bugs using sanitizers', icon: 'bug', color: '#EF4444', progress: 8, maxProgress: 25 },
  { id: 'optimizer', name: 'Speed Demon', description: 'Improve code performance 10 times', icon: 'flash', color: '#10B981', progress: 2, maxProgress: 10 },
  { id: 'polyglot', name: 'Polyglot', description: 'Write code in 5 languages', icon: 'globe', color: '#2563EB', progress: 2, maxProgress: 5 },
  { id: 'streak_7', name: 'Weekly Warrior', description: '7-day coding streak', icon: 'flame', color: '#F43F5E' },
  { id: 'streak_30', name: 'Monthly Master', description: '30-day coding streak', icon: 'diamond', color: '#EC4899' },
  { id: 'bible_reader', name: 'Scholar', description: 'Complete 10 Bible chapters', icon: 'book', color: '#FFD700', progress: 0, maxProgress: 10 },
  { id: 'voice_user', name: 'Voice Commander', description: 'Use 20 voice commands', icon: 'mic', color: '#8B5CF6', progress: 0, maxProgress: 20 },
];

// ============================================================================
// STORAGE KEY
// ============================================================================

// ============================================================================
// PROPS
// ============================================================================
interface LearningDashboardProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================
export function LearningDashboard({ visible, onClose, colors }: LearningDashboardProps) {
  const [activeTab, setActiveTab] = useState<'overview' | 'heatmap' | 'gaps' | 'achievements'>('overview');
  const [skills, setSkills] = useState<SkillLevel[]>([]);
  const [achievements] = useState<Achievement[]>(DEFAULT_ACHIEVEMENTS);
  const [stats] = useState<LearningStats>({
    totalPracticeMinutes: 127,
    totalExercisesCompleted: 45,
    averageAccuracy: 78,
    languagesPracticed: ['Python', 'JavaScript'],
    conceptsMastered: 12,
    streak: { current: 3, longest: 7, lastActiveDate: new Date() },
  });

  // Generate mock skills on load
  useEffect(() => {
    const mockSkills: SkillLevel[] = [];
    SKILL_CATEGORIES.forEach(cat => {
      cat.skills.forEach(skill => {
        mockSkills.push({
          skill,
          category: cat.name,
          level: Math.floor(Math.random() * 100),
          practiceCount: Math.floor(Math.random() * 50),
          trend: ['improving', 'stable', 'declining'][Math.floor(Math.random() * 3)] as any,
        });
      });
    });
    setSkills(mockSkills);
  }, []);

  // Knowledge gaps prediction
  const knowledgeGaps = useMemo((): KnowledgeGap[] => {
    const lowSkills = skills.filter(s => s.level < 40);
    return lowSkills.slice(0, 5).map(s => ({
      skill: s.skill,
      prerequisite: skills.find(sk => sk.level > 60 && sk.category === s.category)?.skill || 'Basics',
      confidence: 0.85 + Math.random() * 0.1,
      recommendation: `Practice ${s.skill} exercises in the Coding Bible`,
    }));
  }, [skills]);

  // Get mastery color
  const getMasteryColor = (level: number) => {
    if (level >= 80) return '#10B981';
    if (level >= 60) return '#22C55E';
    if (level >= 40) return '#F59E0B';
    if (level >= 20) return '#F97316';
    return '#EF4444';
  };

  // ============================================================================
  // RENDER OVERVIEW TAB
  // ============================================================================
  const renderOverview = () => (
    <ScrollView style={styles.tabContent}>
      {/* Stats Cards */}
      <View style={styles.statsGrid}>
        <View style={[styles.statCard, { backgroundColor: '#6366F120' }]}>
          <Ionicons name="time" size={24} color="#6366F1" />
          <Text style={[styles.statValue, { color: colors.text }]}>{stats.totalPracticeMinutes}</Text>
          <Text style={[styles.statLabel, { color: colors.textMuted }]}>Minutes</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#10B98120' }]}>
          <Ionicons name="checkmark-circle" size={24} color="#10B981" />
          <Text style={[styles.statValue, { color: colors.text }]}>{stats.totalExercisesCompleted}</Text>
          <Text style={[styles.statLabel, { color: colors.textMuted }]}>Exercises</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#F59E0B20' }]}>
          <Ionicons name="analytics" size={24} color="#F59E0B" />
          <Text style={[styles.statValue, { color: colors.text }]}>{stats.averageAccuracy}%</Text>
          <Text style={[styles.statLabel, { color: colors.textMuted }]}>Accuracy</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#EF444420' }]}>
          <Ionicons name="flame" size={24} color="#EF4444" />
          <Text style={[styles.statValue, { color: colors.text }]}>{stats.streak.current}</Text>
          <Text style={[styles.statLabel, { color: colors.textMuted }]}>Day Streak</Text>
        </View>
      </View>

      {/* Mastery Summary */}
      <View style={[styles.section, { backgroundColor: colors.surface }]}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Skill Mastery</Text>
        {SKILL_CATEGORIES.map(cat => {
          const catSkills = skills.filter(s => s.category === cat.name);
          const avgLevel = catSkills.length > 0 
            ? Math.round(catSkills.reduce((sum, s) => sum + s.level, 0) / catSkills.length) 
            : 0;
          
          return (
            <View key={cat.name} style={styles.masteryRow}>
              <Text style={[styles.masteryCategory, { color: colors.text }]}>{cat.name}</Text>
              <View style={[styles.masteryBar, { backgroundColor: colors.surfaceAlt }]}>
                <View style={[styles.masteryFill, { width: `${avgLevel}%`, backgroundColor: getMasteryColor(avgLevel) }]} />
              </View>
              <Text style={[styles.masteryPercent, { color: getMasteryColor(avgLevel) }]}>{avgLevel}%</Text>
            </View>
          );
        })}
      </View>

      {/* Recent Achievements */}
      <View style={[styles.section, { backgroundColor: colors.surface }]}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Recent Achievements</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          {achievements.filter(a => a.unlockedAt).slice(0, 5).map(achievement => (
            <View key={achievement.id} style={[styles.achievementMini, { backgroundColor: achievement.color + '20' }]}>
              <View style={[styles.achievementIcon, { backgroundColor: achievement.color }]}>
                <Ionicons name={achievement.icon as any} size={20} color="#FFF" />
              </View>
              <Text style={[styles.achievementName, { color: colors.text }]}>{achievement.name}</Text>
            </View>
          ))}
        </ScrollView>
      </View>
    </ScrollView>
  );

  // ============================================================================
  // RENDER HEATMAP TAB
  // ============================================================================
  const renderHeatmap = () => {
    const cellSize = (SCREEN_WIDTH - 100) / 7;
    
    return (
      <ScrollView style={styles.tabContent}>
        <Text style={[styles.heatmapTitle, { color: colors.text }]}>Skill Heatmap</Text>
        <Text style={[styles.heatmapSubtitle, { color: colors.textMuted }]}>
          Darker colors indicate higher mastery
        </Text>
        
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <Svg width={SKILL_CATEGORIES.length * cellSize + 60} height={7 * cellSize + 40}>
            {/* Category Headers */}
            {SKILL_CATEGORIES.map((cat, i) => (
              <SvgText
                key={cat.name}
                x={i * cellSize + cellSize / 2 + 60}
                y={15}
                fontSize={9}
                fill={colors.textMuted}
                textAnchor="middle"
              >
                {cat.name.slice(0, 4)}
              </SvgText>
            ))}
            
            {/* Grid cells */}
            {SKILL_CATEGORIES.map((cat, catIndex) => (
              <G key={cat.name}>
                {cat.skills.slice(0, 6).map((skill, skillIndex) => {
                  const skillData = skills.find(s => s.skill === skill);
                  const level = skillData?.level || 0;
                  const color = getMasteryColor(level);
                  const opacity = 0.3 + (level / 100) * 0.7;
                  
                  return (
                    <G key={skill}>
                      <Rect
                        x={catIndex * cellSize + 60}
                        y={skillIndex * cellSize + 25}
                        width={cellSize - 4}
                        height={cellSize - 4}
                        rx={6}
                        fill={color}
                        opacity={opacity}
                      />
                      <SvgText
                        x={catIndex * cellSize + cellSize / 2 + 60}
                        y={skillIndex * cellSize + cellSize / 2 + 28}
                        fontSize={8}
                        fill="#FFF"
                        textAnchor="middle"
                      >
                        {level}
                      </SvgText>
                    </G>
                  );
                })}
              </G>
            ))}
            
            {/* Skill labels */}
            {SKILL_CATEGORIES[0].skills.slice(0, 6).map((skill, i) => (
              <SvgText
                key={skill}
                x={55}
                y={i * cellSize + cellSize / 2 + 28}
                fontSize={9}
                fill={colors.textMuted}
                textAnchor="end"
              >
                {skill.slice(0, 8)}
              </SvgText>
            ))}
          </Svg>
        </ScrollView>
        
        {/* Legend */}
        <View style={styles.legend}>
          <Text style={[styles.legendLabel, { color: colors.textMuted }]}>Mastery Level:</Text>
          {[0, 25, 50, 75, 100].map(level => (
            <View key={level} style={styles.legendItem}>
              <View style={[styles.legendColor, { backgroundColor: getMasteryColor(level), opacity: 0.3 + (level / 100) * 0.7 }]} />
              <Text style={[styles.legendText, { color: colors.textMuted }]}>{level}%</Text>
            </View>
          ))}
        </View>
      </ScrollView>
    );
  };

  // ============================================================================
  // RENDER GAPS TAB
  // ============================================================================
  const renderGaps = () => (
    <ScrollView style={styles.tabContent}>
      <View style={[styles.gapHeader, { backgroundColor: colors.surfaceAlt }]}>
        <Ionicons name="bulb" size={24} color="#F59E0B" />
        <View style={styles.gapHeaderText}>
          <Text style={[styles.gapHeaderTitle, { color: colors.text }]}>AI-Predicted Knowledge Gaps</Text>
          <Text style={[styles.gapHeaderSubtitle, { color: colors.textMuted }]}>
            Areas that need more practice based on your learning patterns
          </Text>
        </View>
      </View>
      
      {knowledgeGaps.length === 0 ? (
        <View style={[styles.emptyGaps, { backgroundColor: colors.surface }]}>
          <Ionicons name="checkmark-circle" size={48} color="#10B981" />
          <Text style={[styles.emptyGapsTitle, { color: colors.text }]}>No Gaps Detected!</Text>
          <Text style={[styles.emptyGapsSubtitle, { color: colors.textMuted }]}>
            Your knowledge is well-rounded. Keep practicing!
          </Text>
        </View>
      ) : (
        knowledgeGaps.map((gap, index) => (
          <View key={index} style={[styles.gapCard, { backgroundColor: colors.surface }]}>
            <View style={styles.gapCardHeader}>
              <View style={[styles.gapPriority, { backgroundColor: index === 0 ? '#EF4444' : '#F59E0B' }]}>
                <Text style={styles.gapPriorityText}>#{index + 1}</Text>
              </View>
              <View style={styles.gapSkillInfo}>
                <Text style={[styles.gapSkillName, { color: colors.text }]}>{gap.skill}</Text>
                <Text style={[styles.gapPrerequisite, { color: colors.textMuted }]}>
                  Prerequisite: {gap.prerequisite}
                </Text>
              </View>
              <View style={[styles.confidenceBadge, { backgroundColor: '#10B98120' }]}>
                <Text style={[styles.confidenceText, { color: '#10B981' }]}>
                  {Math.round(gap.confidence * 100)}%
                </Text>
              </View>
            </View>
            <Text style={[styles.gapRecommendation, { color: colors.textSecondary }]}>
              💡 {gap.recommendation}
            </Text>
            <TouchableOpacity style={[styles.practiceButton, { backgroundColor: '#6366F1' }]}>
              <Ionicons name="play" size={16} color="#FFF" />
              <Text style={styles.practiceButtonText}>Practice Now</Text>
            </TouchableOpacity>
          </View>
        ))
      )}
    </ScrollView>
  );

  // ============================================================================
  // RENDER ACHIEVEMENTS TAB
  // ============================================================================
  const renderAchievements = () => (
    <ScrollView style={styles.tabContent}>
      {/* Unlocked */}
      <Text style={[styles.achievementSection, { color: colors.text }]}>Unlocked</Text>
      <View style={styles.achievementsGrid}>
        {achievements.filter(a => a.unlockedAt).map(achievement => (
          <View key={achievement.id} style={[styles.achievementCard, { backgroundColor: achievement.color + '20', borderColor: achievement.color }]}>
            <View style={[styles.achievementIconLarge, { backgroundColor: achievement.color }]}>
              <Ionicons name={achievement.icon as any} size={28} color="#FFF" />
            </View>
            <Text style={[styles.achievementCardName, { color: colors.text }]}>{achievement.name}</Text>
            <Text style={[styles.achievementCardDesc, { color: colors.textMuted }]}>{achievement.description}</Text>
            <View style={[styles.unlockedBadge, { backgroundColor: '#10B981' }]}>
              <Ionicons name="checkmark" size={12} color="#FFF" />
              <Text style={styles.unlockedText}>Unlocked</Text>
            </View>
          </View>
        ))}
      </View>
      
      {/* In Progress */}
      <Text style={[styles.achievementSection, { color: colors.text }]}>In Progress</Text>
      <View style={styles.achievementsGrid}>
        {achievements.filter(a => !a.unlockedAt && a.progress !== undefined).map(achievement => (
          <View key={achievement.id} style={[styles.achievementCard, { backgroundColor: colors.surfaceAlt, borderColor: colors.border }]}>
            <View style={[styles.achievementIconLarge, { backgroundColor: colors.surface }]}>
              <Ionicons name={achievement.icon as any} size={28} color={colors.textMuted} />
            </View>
            <Text style={[styles.achievementCardName, { color: colors.text }]}>{achievement.name}</Text>
            <Text style={[styles.achievementCardDesc, { color: colors.textMuted }]}>{achievement.description}</Text>
            <View style={[styles.progressSection, { backgroundColor: colors.surface }]}>
              <View style={[styles.progressBarSmall]}>
                <View style={[styles.progressFillSmall, { 
                  width: `${((achievement.progress || 0) / (achievement.maxProgress || 1)) * 100}%`, 
                  backgroundColor: achievement.color 
                }]} />
              </View>
              <Text style={[styles.progressText, { color: colors.textMuted }]}>
                {achievement.progress}/{achievement.maxProgress}
              </Text>
            </View>
          </View>
        ))}
      </View>
      
      {/* Locked */}
      <Text style={[styles.achievementSection, { color: colors.text }]}>Locked</Text>
      <View style={styles.achievementsGrid}>
        {achievements.filter(a => !a.unlockedAt && a.progress === undefined).map(achievement => (
          <View key={achievement.id} style={[styles.achievementCard, { backgroundColor: colors.surfaceAlt, borderColor: colors.border, opacity: 0.6 }]}>
            <View style={[styles.achievementIconLarge, { backgroundColor: colors.surface }]}>
              <Ionicons name="lock-closed" size={28} color={colors.textMuted} />
            </View>
            <Text style={[styles.achievementCardName, { color: colors.textMuted }]}>{achievement.name}</Text>
            <Text style={[styles.achievementCardDesc, { color: colors.textMuted }]}>{achievement.description}</Text>
          </View>
        ))}
      </View>
    </ScrollView>
  );

  // ============================================================================
  // RENDER
  // ============================================================================
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={[styles.overlay, { backgroundColor: 'rgba(0,0,0,0.5)' }]}>
        <View style={[styles.container, { backgroundColor: colors.background }]}>
          {/* Header */}
          <View style={[styles.header, { backgroundColor: colors.surface, borderBottomColor: colors.border }]}>
            <View style={styles.headerTitle}>
              <Ionicons name="analytics" size={22} color="#6366F1" />
              <Text style={[styles.headerText, { color: colors.text }]}>Learning Intelligence</Text>
            </View>
            <TouchableOpacity onPress={onClose}>
              <Ionicons name="close" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>
          
          {/* Tabs */}
          <View style={[styles.tabs, { backgroundColor: colors.surfaceAlt }]}>
            {(['overview', 'heatmap', 'gaps', 'achievements'] as const).map(tab => (
              <TouchableOpacity
                key={tab}
                style={[styles.tab, { 
                  backgroundColor: activeTab === tab ? '#6366F120' : 'transparent',
                  borderBottomColor: activeTab === tab ? '#6366F1' : 'transparent',
                }]}
                onPress={() => setActiveTab(tab)}
              >
                <Ionicons 
                  name={tab === 'overview' ? 'stats-chart' : 
                        tab === 'heatmap' ? 'grid' : 
                        tab === 'gaps' ? 'bulb' : 'trophy'}
                  size={16}
                  color={activeTab === tab ? '#6366F1' : colors.textMuted}
                />
                <Text style={[styles.tabText, { color: activeTab === tab ? '#6366F1' : colors.textMuted }]}>
                  {tab.charAt(0).toUpperCase() + tab.slice(1)}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
          
          {/* Content */}
          {activeTab === 'overview' && renderOverview()}
          {activeTab === 'heatmap' && renderHeatmap()}
          {activeTab === 'gaps' && renderGaps()}
          {activeTab === 'achievements' && renderAchievements()}
        </View>
      </View>
    </Modal>
  );
}

// ============================================================================
// STYLES
// ============================================================================
const styles = StyleSheet.create({
  overlay: { flex: 1, justifyContent: 'flex-end' },
  container: { height: '92%', borderTopLeftRadius: 24, borderTopRightRadius: 24 },
  
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1 },
  headerTitle: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  headerText: { fontSize: 18, fontWeight: '700' },
  
  tabs: { flexDirection: 'row', padding: 8 },
  tab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, gap: 6, borderBottomWidth: 2 },
  tabText: { fontSize: 12, fontWeight: '600' },
  
  tabContent: { flex: 1, padding: 16 },
  
  // Stats Grid
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 16 },
  statCard: { width: '47%', padding: 16, borderRadius: 16, alignItems: 'center' },
  statValue: { fontSize: 28, fontWeight: '800', marginTop: 8 },
  statLabel: { fontSize: 12, marginTop: 4 },
  
  // Section
  section: { padding: 16, borderRadius: 16, marginBottom: 16 },
  sectionTitle: { fontSize: 16, fontWeight: '700', marginBottom: 12 },
  
  // Mastery
  masteryRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 10 },
  masteryCategory: { width: 100, fontSize: 13, fontWeight: '500' },
  masteryBar: { flex: 1, height: 8, borderRadius: 4, marginHorizontal: 10, overflow: 'hidden' },
  masteryFill: { height: '100%', borderRadius: 4 },
  masteryPercent: { width: 40, fontSize: 12, fontWeight: '600', textAlign: 'right' },
  
  // Achievement Mini
  achievementMini: { width: 100, padding: 12, borderRadius: 12, alignItems: 'center', marginRight: 10 },
  achievementIcon: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  achievementName: { fontSize: 11, fontWeight: '600', marginTop: 8, textAlign: 'center' },
  
  // Heatmap
  heatmapTitle: { fontSize: 18, fontWeight: '700', marginBottom: 4 },
  heatmapSubtitle: { fontSize: 13, marginBottom: 16 },
  legend: { flexDirection: 'row', alignItems: 'center', marginTop: 16, gap: 8 },
  legendLabel: { fontSize: 12, marginRight: 8 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  legendColor: { width: 16, height: 16, borderRadius: 4 },
  legendText: { fontSize: 10 },
  
  // Gaps
  gapHeader: { flexDirection: 'row', padding: 16, borderRadius: 12, marginBottom: 16, gap: 12, alignItems: 'center' },
  gapHeaderText: { flex: 1 },
  gapHeaderTitle: { fontSize: 16, fontWeight: '700' },
  gapHeaderSubtitle: { fontSize: 12, marginTop: 4 },
  emptyGaps: { padding: 40, borderRadius: 16, alignItems: 'center' },
  emptyGapsTitle: { fontSize: 18, fontWeight: '700', marginTop: 12 },
  emptyGapsSubtitle: { fontSize: 13, marginTop: 4, textAlign: 'center' },
  gapCard: { padding: 16, borderRadius: 16, marginBottom: 12 },
  gapCardHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 12 },
  gapPriority: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  gapPriorityText: { color: '#FFF', fontSize: 12, fontWeight: '700' },
  gapSkillInfo: { flex: 1, marginLeft: 12 },
  gapSkillName: { fontSize: 15, fontWeight: '600' },
  gapPrerequisite: { fontSize: 12, marginTop: 2 },
  confidenceBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  confidenceText: { fontSize: 12, fontWeight: '600' },
  gapRecommendation: { fontSize: 13, lineHeight: 20, marginBottom: 12 },
  practiceButton: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: 12, borderRadius: 10, gap: 8 },
  practiceButtonText: { color: '#FFF', fontSize: 14, fontWeight: '600' },
  
  // Achievements
  achievementSection: { fontSize: 16, fontWeight: '700', marginBottom: 12, marginTop: 8 },
  achievementsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 16 },
  achievementCard: { width: '47%', padding: 14, borderRadius: 16, borderWidth: 1, alignItems: 'center' },
  achievementIconLarge: { width: 56, height: 56, borderRadius: 28, alignItems: 'center', justifyContent: 'center' },
  achievementCardName: { fontSize: 14, fontWeight: '600', marginTop: 10, textAlign: 'center' },
  achievementCardDesc: { fontSize: 11, marginTop: 4, textAlign: 'center' },
  unlockedBadge: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, marginTop: 10, gap: 4 },
  unlockedText: { color: '#FFF', fontSize: 11, fontWeight: '600' },
  progressSection: { width: '100%', padding: 8, borderRadius: 8, marginTop: 10 },
  progressBarSmall: { height: 6, borderRadius: 3, backgroundColor: 'rgba(0,0,0,0.1)', overflow: 'hidden' },
  progressFillSmall: { height: '100%', borderRadius: 3 },
  progressText: { fontSize: 11, textAlign: 'center', marginTop: 4 },
});

export default LearningDashboard;
