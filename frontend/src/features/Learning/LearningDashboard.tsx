// ============================================================================
// CODEDOCK QUANTUM NEXUS - Learning Intelligence Dashboard
// Mastery heatmaps, knowledge-gap predictions, achievement tracking
// ============================================================================

import React, { useState, useMemo, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Modal, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { API_BASE } from '../../utils/apiBase';
import { apiFetch } from '../../utils/apiController';

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
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<'overview' | 'heatmap' | 'gaps' | 'achievements'>('overview');
  const [skills, setSkills] = useState<SkillLevel[]>([]);
  const [knowledgeGaps, setKnowledgeGaps] = useState<KnowledgeGap[]>([]);
  const achievements: Achievement[] = [];
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    let active = true;
    setLoading(true);
    setLoadError(null);
    Promise.all([
      apiFetch(`${API_BASE}/api/learning/mastery`),
      apiFetch(`${API_BASE}/api/learning/predictions`),
    ]).then(async ([masteryResponse, predictionsResponse]) => {
      if (!masteryResponse.ok || !predictionsResponse.ok) throw new Error('Learning intelligence service unavailable');
      const mastery = await masteryResponse.json();
      const predictions = await predictionsResponse.json();
      if (!active) return;
      setSkills((Array.isArray(mastery.heatmap) ? mastery.heatmap : []).map((entry: any) => ({
        skill: String(entry.concept || 'Basics'),
        category: String(entry.language || 'General'),
        level: Math.max(0, Math.min(100, Number(entry.mastery) || 0)),
        practiceCount: Math.max(0, Number(entry.practice_count) || 0),
        trend: 'stable' as const,
      })));
      setKnowledgeGaps((Array.isArray(predictions.predictions) ? predictions.predictions : []).map((entry: any) => ({
        skill: String(entry.concept || 'General'),
        prerequisite: 'Recorded fundamentals',
        confidence: Math.max(0, Math.min(1, (Number(entry.confidence) || 0) / 100)),
        recommendation: String(entry.recommendation || 'Continue focused practice'),
      })));
    }).catch((error: unknown) => {
      if (active) setLoadError(error instanceof Error ? error.message : 'Unable to load learning intelligence');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [visible]);

  const stats = useMemo<LearningStats>(() => {
    const exercises = skills.reduce((total, skill) => total + skill.practiceCount, 0);
    const weighted = skills.reduce((total, skill) => total + skill.level * skill.practiceCount, 0);
    return {
      totalPracticeMinutes: 0,
      totalExercisesCompleted: exercises,
      averageAccuracy: exercises ? Math.round(weighted / exercises) : 0,
      languagesPracticed: Array.from(new Set(skills.map(skill => skill.category))),
      conceptsMastered: skills.filter(skill => skill.level >= 80).length,
      streak: { current: 0, longest: 0, lastActiveDate: new Date(0) },
    };
  }, [skills]);

  const categories = useMemo(() => Array.from(new Set(skills.map(skill => skill.category))), [skills]);

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
        {categories.map(category => {
          const catSkills = skills.filter(s => s.category === category);
          const avgLevel = catSkills.length > 0 
            ? Math.round(catSkills.reduce((sum, s) => sum + s.level, 0) / catSkills.length) 
            : 0;
          
          return (
            <View key={category} style={styles.masteryRow}>
              <Text style={[styles.masteryCategory, { color: colors.text }]}>{category}</Text>
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
    return (
      <ScrollView style={styles.tabContent}>
        <Text style={[styles.heatmapTitle, { color: colors.text }]}>Skill Heatmap</Text>
        <Text style={[styles.heatmapSubtitle, { color: colors.textMuted }]}>
          Darker colors indicate higher mastery
        </Text>
        
        {skills.length === 0 ? (
          <View style={[styles.emptyGaps, { backgroundColor: colors.surface }]}>
            <Ionicons name="analytics-outline" size={42} color={colors.textMuted} />
            <Text style={[styles.emptyGapsTitle, { color: colors.text }]}>No recorded practice yet</Text>
            <Text style={[styles.emptyGapsSubtitle, { color: colors.textMuted }]}>Complete tracked exercises to build a mastery heatmap.</Text>
          </View>
        ) : skills.map(skill => (
          <View key={`${skill.category}:${skill.skill}`} style={[styles.masteryRow, { backgroundColor: colors.surface, padding: 12, borderRadius: 10 }]}>
            <View style={{ width: 110 }}>
              <Text style={[styles.masteryCategory, { color: colors.text }]}>{skill.skill}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>{skill.category} · {skill.practiceCount} attempts</Text>
            </View>
            <View style={[styles.masteryBar, { backgroundColor: colors.surfaceAlt }]}>
              <View style={[styles.masteryFill, { width: `${skill.level}%`, backgroundColor: getMasteryColor(skill.level) }]} />
            </View>
            <Text style={[styles.masteryPercent, { color: getMasteryColor(skill.level) }]}>{skill.level}%</Text>
          </View>
        ))}
        
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
          <Ionicons name="analytics-outline" size={48} color={colors.textMuted} />
          <Text style={[styles.emptyGapsTitle, { color: colors.text }]}>No supported gap evidence</Text>
          <Text style={[styles.emptyGapsSubtitle, { color: colors.textMuted }]}>
            Gap recommendations appear after recorded unsuccessful practice attempts.
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
            <TouchableOpacity style={[styles.practiceButton, { backgroundColor: '#6366F1' }]} onPress={() => { onClose(); router.push('/bible'); }}>
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
      {achievements.length === 0 && (
        <View style={[styles.emptyGaps, { backgroundColor: colors.surface }]}>
          <Ionicons name="trophy-outline" size={48} color={colors.textMuted} />
          <Text style={[styles.emptyGapsTitle, { color: colors.text }]}>No verified achievements</Text>
          <Text style={[styles.emptyGapsSubtitle, { color: colors.textMuted }]}>Achievements appear when the activity ledger records their completion.</Text>
        </View>
      )}
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
          {loading && <ActivityIndicator style={{ marginTop: 24 }} color="#6366F1" />}
          {loadError && <Text style={{ color: '#EF4444', paddingHorizontal: 16, paddingTop: 12 }}>{loadError}</Text>}
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
