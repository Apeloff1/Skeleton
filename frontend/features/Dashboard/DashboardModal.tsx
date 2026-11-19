/**
 * Dashboard Visualization Modal v12.0
 * 
 * Comprehensive dashboard showing:
 * - Learning progress and streaks
 * - AI usage analytics
 * - Emotional wellness tracking
 * - Personalized recommendations
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
import { synergyService, DashboardData } from '../../services/synergy';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

interface DashboardModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  userId?: string;
}

// Stat Card Component
const StatCard: React.FC<{
  icon: string;
  iconColor: string;
  label: string;
  value: string | number;
  subtitle?: string;
  colors: any;
}> = ({ icon, iconColor, label, value, subtitle, colors }) => (
  <View style={[styles.statCard, { backgroundColor: colors.surfaceAlt }]}>
    <View style={[styles.statIconContainer, { backgroundColor: iconColor + '20' }]}>
      <Ionicons name={icon as any} size={24} color={iconColor} />
    </View>
    <Text style={[styles.statValue, { color: colors.text }]}>{value}</Text>
    <Text style={[styles.statLabel, { color: colors.textMuted }]}>{label}</Text>
    {subtitle && (
      <Text style={[styles.statSubtitle, { color: iconColor }]}>{subtitle}</Text>
    )}
  </View>
);

// Progress Ring Component
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const ProgressRing: React.FC<{
  progress: number;
  size: number;
  strokeWidth: number;
  color: string;
  bgColor: string;
  children?: React.ReactNode;
}> = ({ progress, size, strokeWidth, color, bgColor, children }) => {

  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <View
        style={{
          position: 'absolute',
          width: size,
          height: size,
          borderRadius: size / 2,
          borderWidth: strokeWidth,
          borderColor: bgColor,
        }}
      />
      <View
        style={{
          position: 'absolute',
          width: size,
          height: size,
          borderRadius: size / 2,
          borderWidth: strokeWidth,
          borderColor: color,
          borderTopColor: 'transparent',
          borderRightColor: progress > 25 ? color : 'transparent',
          borderBottomColor: progress > 50 ? color : 'transparent',
          borderLeftColor: progress > 75 ? color : 'transparent',
          transform: [{ rotate: '-90deg' }],
        }}
      />
      {children}
    </View>
  );
};

// Activity Chart (Simple bar representation)
const ActivityChart: React.FC<{
  data: Record<string, number>;
  colors: any;
}> = ({ data, colors }) => {
  const maxValue = Math.max(...Object.values(data), 1);
  const entries = Object.entries(data).slice(0, 5);

  return (
    <View style={styles.chartContainer}>
      {entries.map(([type, count]) => (
        <View key={type} style={styles.chartBar}>
          <View
            style={[
              styles.chartBarFill,
              {
                backgroundColor: colors.primary,
                height: `${(count / maxValue) * 100}%`,
              },
            ]}
          />
          <Text style={[styles.chartBarLabel, { color: colors.textMuted }]}>
            {type.slice(0, 4)}
          </Text>
          <Text style={[styles.chartBarValue, { color: colors.text }]}>
            {count}
          </Text>
        </View>
      ))}
    </View>
  );
};

// Emotion Indicator
const EmotionIndicator: React.FC<{
  emotion: string;
  stressLevel: number;
  colors: any;
}> = ({ emotion, stressLevel, colors }) => {
  const emotionEmojis: Record<string, string> = {
    neutral: '😊',
    happy: '😄',
    focused: '🎯',
    frustrated: '😤',
    confused: '🤔',
    tired: '😴',
    confident: '💪',
    excited: '🚀',
  };

  const stressColor = stressLevel < 0.3 ? '#10B981' : stressLevel < 0.6 ? '#F59E0B' : '#EF4444';

  return (
    <View style={[styles.emotionContainer, { backgroundColor: colors.surfaceAlt }]}>
      <Text style={styles.emotionEmoji}>{emotionEmojis[emotion] || '😊'}</Text>
      <View style={styles.emotionInfo}>
        <Text style={[styles.emotionLabel, { color: colors.text }]}>
          Current State: {emotion.charAt(0).toUpperCase() + emotion.slice(1)}
        </Text>
        <View style={styles.stressBar}>
          <View
            style={[
              styles.stressBarFill,
              { width: `${stressLevel * 100}%`, backgroundColor: stressColor },
            ]}
          />
        </View>
        <Text style={[styles.stressLabel, { color: colors.textMuted }]}>
          Stress Level: {Math.round(stressLevel * 100)}%
        </Text>
      </View>
    </View>
  );
};

// Main Dashboard Modal
export const DashboardModal: React.FC<DashboardModalProps> = ({
  visible,
  onClose,
  colors,
  userId = 'default_user',
}) => {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [data, setData] = useState<DashboardData | null>(null);
  const [timeRange, setTimeRange] = useState(7);

  const loadDashboard = useCallback(async () => {
    try {
      const dashboardData = await synergyService.getDashboard(userId, timeRange);
      setData(dashboardData);
    } catch (error) {
      console.error('Failed to load dashboard:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [userId, timeRange]);

  useEffect(() => {
    if (visible) {
      setLoading(true);
      loadDashboard();
    }
  }, [visible, loadDashboard]);

  const onRefresh = () => {
    setRefreshing(true);
    loadDashboard();
  };

  const formatTime = (minutes: number): string => {
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={[styles.modalContainer, { backgroundColor: 'rgba(0,0,0,0.5)' }]}>
        <View style={[styles.modalContent, { backgroundColor: colors.background }]}>
          {/* Header */}
          <View style={[styles.header, { borderBottomColor: colors.border }]}>
            <View style={styles.headerLeft}>
              <Ionicons name="stats-chart" size={24} color={colors.primary} />
              <Text style={[styles.headerTitle, { color: colors.text }]}>
                Dashboard
              </Text>
            </View>
            <View style={styles.headerRight}>
              {/* Time range selector */}
              <View style={styles.timeSelector}>
                {[7, 14, 30].map((days) => (
                  <TouchableOpacity
                    key={days}
                    style={[
                      styles.timeSelectorButton,
                      timeRange === days && { backgroundColor: colors.primary + '30' },
                    ]}
                    onPress={() => setTimeRange(days)}
                  >
                    <Text
                      style={[
                        styles.timeSelectorText,
                        { color: timeRange === days ? colors.primary : colors.textMuted },
                      ]}
                    >
                      {days}d
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
              <TouchableOpacity onPress={onClose} style={styles.closeButton}>
                <Ionicons name="close" size={24} color={colors.text} />
              </TouchableOpacity>
            </View>
          </View>

          {/* Content */}
          {loading ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color={colors.primary} />
              <Text style={[styles.loadingText, { color: colors.textMuted }]}>
                Loading your stats...
              </Text>
            </View>
          ) : data ? (
            <ScrollView
              style={styles.scrollContent}
              showsVerticalScrollIndicator={false}
              refreshControl={
                <RefreshControl
                  refreshing={refreshing}
                  onRefresh={onRefresh}
                  tintColor={colors.primary}
                />
              }
            >
              {/* Learning Stats */}
              <Text style={[styles.sectionTitle, { color: colors.text }]}>
                📚 Learning Progress
              </Text>
              <View style={styles.statsGrid}>
                <StatCard
                  icon="time"
                  iconColor="#8B5CF6"
                  label="Study Time"
                  value={formatTime(data.learning.total_study_minutes)}
                  colors={colors}
                />
                <StatCard
                  icon="checkmark-circle"
                  iconColor="#10B981"
                  label="Completed"
                  value={data.learning.modules_completed}
                  subtitle="modules"
                  colors={colors}
                />
                <StatCard
                  icon="flame"
                  iconColor="#F59E0B"
                  label="Streak"
                  value={data.learning.current_streak}
                  subtitle="days"
                  colors={colors}
                />
                <StatCard
                  icon="star"
                  iconColor="#FFD700"
                  label="XP Earned"
                  value={data.learning.xp_earned}
                  colors={colors}
                />
              </View>

              {/* AI Usage */}
              <Text style={[styles.sectionTitle, { color: colors.text }]}>
                🤖 AI Interactions
              </Text>
              <View style={[styles.aiSection, { backgroundColor: colors.surfaceAlt }]}>
                <View style={styles.aiStats}>
                  <View style={styles.aiStatItem}>
                    <Text style={[styles.aiStatValue, { color: colors.primary }]}>
                      {data.ai_usage.total_interactions}
                    </Text>
                    <Text style={[styles.aiStatLabel, { color: colors.textMuted }]}>
                      Total
                    </Text>
                  </View>
                  <View style={styles.aiStatItem}>
                    <Text style={[styles.aiStatValue, { color: colors.success }]}>
                      {data.ai_usage.avg_per_day.toFixed(1)}
                    </Text>
                    <Text style={[styles.aiStatLabel, { color: colors.textMuted }]}>
                      Per Day
                    </Text>
                  </View>
                </View>
                {Object.keys(data.ai_usage.by_type).length > 0 && (
                  <ActivityChart data={data.ai_usage.by_type} colors={colors} />
                )}
              </View>

              {/* Emotional Wellness */}
              <Text style={[styles.sectionTitle, { color: colors.text }]}>
                💚 Wellness
              </Text>
              <EmotionIndicator
                emotion={data.emotional_wellness.current_state}
                stressLevel={data.emotional_wellness.avg_stress_level}
                colors={colors}
              />
              <View style={[styles.pomodoroCard, { backgroundColor: colors.surfaceAlt }]}>
                <Ionicons name="timer" size={24} color="#EF4444" />
                <View style={styles.pomodoroInfo}>
                  <Text style={[styles.pomodoroValue, { color: colors.text }]}>
                    {data.emotional_wellness.pomodoro_sessions}
                  </Text>
                  <Text style={[styles.pomodoroLabel, { color: colors.textMuted }]}>
                    Pomodoro Sessions
                  </Text>
                </View>
              </View>

              {/* Recommendations */}
              {data.recommendations && data.recommendations.length > 0 && (
                <>
                  <Text style={[styles.sectionTitle, { color: colors.text }]}>
                    💡 Recommended Next
                  </Text>
                  {data.recommendations.slice(0, 3).map((rec, index) => (
                    <View
                      key={index}
                      style={[styles.recommendationCard, { backgroundColor: colors.surfaceAlt }]}
                    >
                      <View style={[styles.recIcon, { backgroundColor: colors.primary + '20' }]}>
                        <Ionicons name="book" size={20} color={colors.primary} />
                      </View>
                      <View style={styles.recInfo}>
                        <Text style={[styles.recTitle, { color: colors.text }]}>
                          {rec.title || rec.module_id || 'Continue Learning'}
                        </Text>
                        <Text style={[styles.recSubtitle, { color: colors.textMuted }]}>
                          {rec.description || 'Based on your progress'}
                        </Text>
                      </View>
                      <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                    </View>
                  ))}
                </>
              )}

              <View style={{ height: 40 }} />
            </ScrollView>
          ) : (
            <View style={styles.errorContainer}>
              <Ionicons name="alert-circle" size={48} color={colors.error} />
              <Text style={[styles.errorText, { color: colors.text }]}>
                Failed to load dashboard
              </Text>
              <TouchableOpacity
                style={[styles.retryButton, { backgroundColor: colors.primary }]}
                onPress={loadDashboard}
              >
                <Text style={styles.retryText}>Retry</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  modalContainer: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  modalContent: {
    height: '90%',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: '700',
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  timeSelector: {
    flexDirection: 'row',
    borderRadius: 8,
    overflow: 'hidden',
  },
  timeSelectorButton: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  timeSelectorText: {
    fontSize: 12,
    fontWeight: '600',
  },
  closeButton: {
    padding: 4,
  },
  scrollContent: {
    flex: 1,
    padding: 16,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 16,
  },
  loadingText: {
    fontSize: 14,
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 16,
  },
  errorText: {
    fontSize: 16,
  },
  retryButton: {
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
  },
  retryText: {
    color: '#fff',
    fontWeight: '600',
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    marginTop: 16,
    marginBottom: 12,
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  statCard: {
    width: (SCREEN_WIDTH - 56) / 2,
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
  },
  statIconContainer: {
    width: 48,
    height: 48,
    borderRadius: 24,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
  },
  statValue: {
    fontSize: 24,
    fontWeight: '700',
  },
  statLabel: {
    fontSize: 12,
    marginTop: 4,
  },
  statSubtitle: {
    fontSize: 10,
    fontWeight: '600',
  },
  aiSection: {
    borderRadius: 12,
    padding: 16,
  },
  aiStats: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    marginBottom: 16,
  },
  aiStatItem: {
    alignItems: 'center',
  },
  aiStatValue: {
    fontSize: 28,
    fontWeight: '700',
  },
  aiStatLabel: {
    fontSize: 12,
  },
  chartContainer: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    height: 100,
    alignItems: 'flex-end',
  },
  chartBar: {
    alignItems: 'center',
    width: 50,
  },
  chartBarFill: {
    width: 30,
    borderRadius: 4,
    minHeight: 4,
  },
  chartBarLabel: {
    fontSize: 10,
    marginTop: 4,
  },
  chartBarValue: {
    fontSize: 12,
    fontWeight: '600',
  },
  emotionContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
    gap: 16,
  },
  emotionEmoji: {
    fontSize: 48,
  },
  emotionInfo: {
    flex: 1,
  },
  emotionLabel: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },
  stressBar: {
    height: 8,
    backgroundColor: 'rgba(0,0,0,0.1)',
    borderRadius: 4,
    overflow: 'hidden',
  },
  stressBarFill: {
    height: '100%',
    borderRadius: 4,
  },
  stressLabel: {
    fontSize: 12,
    marginTop: 4,
  },
  pomodoroCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
    marginTop: 12,
    gap: 16,
  },
  pomodoroInfo: {
    flex: 1,
  },
  pomodoroValue: {
    fontSize: 24,
    fontWeight: '700',
  },
  pomodoroLabel: {
    fontSize: 12,
  },
  recommendationCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderRadius: 12,
    marginBottom: 8,
    gap: 12,
  },
  recIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
  },
  recInfo: {
    flex: 1,
  },
  recTitle: {
    fontSize: 14,
    fontWeight: '600',
  },
  recSubtitle: {
    fontSize: 12,
  },
});

export default DashboardModal;
