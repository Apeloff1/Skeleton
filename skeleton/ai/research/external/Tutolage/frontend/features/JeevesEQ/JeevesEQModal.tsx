/**
 * Jeeves EQ Modal v11.8 - Emotional Intelligence Dashboard
 * 
 * Features:
 * - Emotional state visualization
 * - Pomodoro timer UI
 * - Wellness reminders
 * - Psychology profile dashboard
 * - Growth mindset messages
 * - Cognitive load monitor
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  Modal, Dimensions, ActivityIndicator, Animated,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const API_URL = Constants.expoConfig?.extra?.EXPO_BACKEND_URL || '';

interface JeevesEQModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  userId?: string;
}

type TabType = 'overview' | 'pomodoro' | 'wellness' | 'insights';

const EMOTION_COLORS: Record<string, string> = {
  confident: '#10B981',
  curious: '#3B82F6',
  engaged: '#8B5CF6',
  neutral: '#6B7280',
  confused: '#F59E0B',
  frustrated: '#EF4444',
  anxious: '#EC4899',
  overwhelmed: '#DC2626',
  bored: '#9CA3AF',
  discouraged: '#7C3AED',
};

const EMOTION_ICONS: Record<string, string> = {
  confident: 'happy',
  curious: 'help-circle',
  engaged: 'rocket',
  neutral: 'remove',
  confused: 'help',
  frustrated: 'sad',
  anxious: 'alert-circle',
  overwhelmed: 'thunderstorm',
  bored: 'bed',
  discouraged: 'trending-down',
};

export const JeevesEQModal: React.FC<JeevesEQModalProps> = ({
  visible, onClose, colors, userId = 'user_001'
}) => {
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [loading, setLoading] = useState(false);
  const [eqInfo, setEqInfo] = useState<any>(null);
  const [emotionalState, setEmotionalState] = useState<any>(null);
  const [psychologyProfile, setPsychologyProfile] = useState<any>(null);
  const [cognitiveLoad, setCognitiveLoad] = useState<any>(null);
  const [wellnessReminder, setWellnessReminder] = useState<any>(null);
  const [therapeuticResponse, setTherapeuticResponse] = useState<string | null>(null);
  
  // Pomodoro state
  const [pomodoroActive, setPomodoroActive] = useState(false);
  const [pomodoroType, setPomodoroType] = useState<'work' | 'short_break' | 'long_break'>('work');
  const [pomodoroTime, setPomodoroTime] = useState(25 * 60); // 25 minutes in seconds
  const [sessionsCompleted, setSessionsCompleted] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  
  const pulseAnim = useRef(new Animated.Value(1)).current;

  // Fetch EQ info and data
  const fetchEQData = useCallback(async () => {
    setLoading(true);
    try {
      const [infoRes, profileRes, loadRes, reminderRes] = await Promise.all([
        fetch(`${API_URL}/api/jeeves-eq/info`),
        fetch(`${API_URL}/api/jeeves-eq/psychology-profile/${userId}`),
        fetch(`${API_URL}/api/jeeves-eq/cognitive-load-check?user_id=${userId}&session_duration_minutes=30&new_concepts_introduced=2&error_count=3&last_break_minutes_ago=25`),
        fetch(`${API_URL}/api/jeeves-eq/wellness-reminder`)
      ]);
      
      if (infoRes.ok) setEqInfo(await infoRes.json());
      if (profileRes.ok) setPsychologyProfile(await profileRes.json());
      if (loadRes.ok) setCognitiveLoad(await loadRes.json());
      if (reminderRes.ok) setWellnessReminder(await reminderRes.json());
    } catch (err) {
      console.error('Error fetching EQ data:', err);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  // Detect emotional state
  const detectEmotion = useCallback(async (recentActions: any[]) => {
    try {
      const res = await fetch(`${API_URL}/api/jeeves-eq/detect-emotion?user_id=${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, recent_actions: recentActions })
      });
      if (res.ok) {
        const data = await res.json();
        setEmotionalState(data.emotional_state);
        
        // If intervention needed, get therapeutic response
        if (data.immediate_intervention_needed) {
          await getTherapeuticResponse(data.emotional_state.primary, data.emotional_state.intensity);
        }
      }
    } catch (err) {
      console.error(err);
    }
  }, [userId]);

  // Get therapeutic response
  const getTherapeuticResponse = async (emotion: string, intensity: number) => {
    try {
      const res = await fetch(
        `${API_URL}/api/jeeves-eq/therapeutic-response?user_id=${userId}&emotional_state=${emotion}&intensity=${intensity}`,
        { method: 'POST' }
      );
      if (res.ok) {
        const data = await res.json();
        setTherapeuticResponse(data.response);
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    if (visible) {
      fetchEQData();
      // Simulate detecting emotion with mock recent actions
      detectEmotion([
        { action_type: 'challenge_completed' },
        { action_type: 'lesson_completed' },
        { action_type: 'quiz_completed' }
      ]);
    }
  }, [visible, fetchEQData, detectEmotion]);

  // Pulse animation for emotional state
  useEffect(() => {
    const startPulse = () => {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, {
            toValue: 1.1,
            duration: 1000,
            useNativeDriver: true,
          }),
          Animated.timing(pulseAnim, {
            toValue: 1,
            duration: 1000,
            useNativeDriver: true,
          }),
        ])
      ).start();
    };
    startPulse();
    return () => pulseAnim.stopAnimation();
  }, [pulseAnim]);

  // Pomodoro timer
  useEffect(() => {
    if (pomodoroActive && pomodoroTime > 0) {
      timerRef.current = setTimeout(() => {
        setPomodoroTime(prev => prev - 1);
      }, 1000);
    } else if (pomodoroActive && pomodoroTime === 0) {
      // Timer completed
      setPomodoroActive(false);
      if (pomodoroType === 'work') {
        setSessionsCompleted(prev => prev + 1);
      }
    }
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [pomodoroActive, pomodoroTime, pomodoroType]);

  const startPomodoro = (type: 'work' | 'short_break' | 'long_break') => {
    const times = { work: 25 * 60, short_break: 5 * 60, long_break: 15 * 60 };
    setPomodoroType(type);
    setPomodoroTime(times[type]);
    setPomodoroActive(true);
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const renderTabs = () => (
    <View style={styles.tabBar}>
      {[
        { id: 'overview', label: 'Overview', icon: 'heart' },
        { id: 'pomodoro', label: 'Focus', icon: 'timer' },
        { id: 'wellness', label: 'Wellness', icon: 'leaf' },
        { id: 'insights', label: 'Insights', icon: 'analytics' },
      ].map(tab => (
        <TouchableOpacity
          key={tab.id}
          style={[
            styles.tab,
            activeTab === tab.id && { backgroundColor: colors.primary + '20', borderBottomColor: colors.primary, borderBottomWidth: 2 }
          ]}
          onPress={() => setActiveTab(tab.id as TabType)}
        >
          <Ionicons 
            name={tab.icon as any} 
            size={20} 
            color={activeTab === tab.id ? colors.primary : colors.textMuted} 
          />
          <Text style={[styles.tabText, { color: activeTab === tab.id ? colors.primary : colors.textMuted }]}>
            {tab.label}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );

  const renderOverview = () => {
    const emotion = emotionalState?.primary || 'neutral';
    const intensity = emotionalState?.intensity || 0.5;

    return (
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {/* Emotional State Card */}
        <View style={[styles.emotionCard, { backgroundColor: EMOTION_COLORS[emotion] + '20' }]}>
          <Animated.View style={[
            styles.emotionIconContainer, 
            { backgroundColor: EMOTION_COLORS[emotion], transform: [{ scale: pulseAnim }] }
          ]}>
            <Ionicons name={(EMOTION_ICONS[emotion] || 'help') as any} size={40} color="#FFF" />
          </Animated.View>
          <Text style={[styles.emotionLabel, { color: colors.text }]}>Current State</Text>
          <Text style={[styles.emotionName, { color: EMOTION_COLORS[emotion] }]}>
            {emotion.charAt(0).toUpperCase() + emotion.slice(1)}
          </Text>
          <View style={styles.intensityBar}>
            <View style={[styles.intensityFill, { width: `${intensity * 100}%`, backgroundColor: EMOTION_COLORS[emotion] }]} />
          </View>
          <Text style={[styles.intensityLabel, { color: colors.textMuted }]}>
            Intensity: {Math.round(intensity * 100)}%
          </Text>
        </View>

        {/* Therapeutic Response (if any) */}
        {therapeuticResponse && (
          <View style={[styles.therapeuticCard, { backgroundColor: colors.surface }]}>
            <View style={styles.therapeuticHeader}>
              <Ionicons name="chatbubble-ellipses" size={24} color={colors.primary} />
              <Text style={[styles.therapeuticTitle, { color: colors.text }]}>Jeeves Says...</Text>
            </View>
            <Text style={[styles.therapeuticText, { color: colors.textMuted }]}>
              {therapeuticResponse}
            </Text>
          </View>
        )}

        {/* Quick Stats */}
        <View style={styles.statsGrid}>
          <View style={[styles.statCard, { backgroundColor: colors.surface }]}>
            <Ionicons name="analytics" size={24} color="#8B5CF6" />
            <Text style={[styles.statValue, { color: colors.text }]}>
              {cognitiveLoad?.cognitive_load_level || 'Low'}
            </Text>
            <Text style={[styles.statLabel, { color: colors.textMuted }]}>Cognitive Load</Text>
          </View>
          <View style={[styles.statCard, { backgroundColor: colors.surface }]}>
            <Ionicons name="trending-up" size={24} color="#10B981" />
            <Text style={[styles.statValue, { color: colors.text }]}>
              {Math.round((psychologyProfile?.profile?.growth_mindset_score || 0.5) * 100)}%
            </Text>
            <Text style={[styles.statLabel, { color: colors.textMuted }]}>Growth Mindset</Text>
          </View>
          <View style={[styles.statCard, { backgroundColor: colors.surface }]}>
            <Ionicons name="shield-checkmark" size={24} color="#3B82F6" />
            <Text style={[styles.statValue, { color: colors.text }]}>
              {Math.round((psychologyProfile?.profile?.resilience_score || 0.5) * 100)}%
            </Text>
            <Text style={[styles.statLabel, { color: colors.textMuted }]}>Resilience</Text>
          </View>
        </View>

        {/* Psychology Profile Summary */}
        {psychologyProfile?.profile && (
          <View style={[styles.profileCard, { backgroundColor: colors.surface }]}>
            <Text style={[styles.cardTitle, { color: colors.text }]}>🧠 Your Learning Profile</Text>
            <View style={styles.profileRow}>
              <Text style={[styles.profileLabel, { color: colors.textMuted }]}>Motivation Type</Text>
              <Text style={[styles.profileValue, { color: colors.primary }]}>
                {psychologyProfile.profile.motivation_type}
              </Text>
            </View>
            <View style={styles.profileRow}>
              <Text style={[styles.profileLabel, { color: colors.textMuted }]}>Cognitive Style</Text>
              <Text style={[styles.profileValue, { color: colors.primary }]}>
                {psychologyProfile.profile.cognitive_style}
              </Text>
            </View>
            <View style={styles.profileRow}>
              <Text style={[styles.profileLabel, { color: colors.textMuted }]}>Stress Tolerance</Text>
              <Text style={[styles.profileValue, { color: colors.primary }]}>
                {psychologyProfile.profile.stress_tolerance}
              </Text>
            </View>
          </View>
        )}

        {/* Recommendations */}
        {psychologyProfile?.recommendations?.length > 0 && (
          <View style={[styles.recommendationsCard, { backgroundColor: colors.surface }]}>
            <Text style={[styles.cardTitle, { color: colors.text }]}>💡 Personalized Tips</Text>
            {psychologyProfile.recommendations.map((rec: any, i: number) => (
              <View key={i} style={styles.recommendationItem}>
                <Text style={[styles.recommendationTitle, { color: colors.text }]}>{rec.title}</Text>
                {rec.suggestions?.slice(0, 2).map((s: string, j: number) => (
                  <View key={j} style={styles.suggestionRow}>
                    <Ionicons name="checkmark" size={14} color="#10B981" />
                    <Text style={[styles.suggestionText, { color: colors.textMuted }]}>{s}</Text>
                  </View>
                ))}
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    );
  };

  const renderPomodoro = () => (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
      {/* Timer Display */}
      <View style={[styles.pomodoroCard, { backgroundColor: colors.surface }]}>
        <Text style={[styles.pomodoroTypeLabel, { color: colors.textMuted }]}>
          {pomodoroType === 'work' ? '🎯 Focus Time' : pomodoroType === 'short_break' ? '☕ Short Break' : '🌴 Long Break'}
        </Text>
        <Text style={[styles.pomodoroTimer, { color: colors.primary }]}>
          {formatTime(pomodoroTime)}
        </Text>
        <View style={styles.pomodoroControls}>
          {!pomodoroActive ? (
            <TouchableOpacity
              style={[styles.pomodoroButton, { backgroundColor: colors.primary }]}
              onPress={() => startPomodoro(pomodoroType)}
            >
              <Ionicons name="play" size={24} color="#FFF" />
              <Text style={styles.pomodoroButtonText}>Start</Text>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity
              style={[styles.pomodoroButton, { backgroundColor: '#EF4444' }]}
              onPress={() => setPomodoroActive(false)}
            >
              <Ionicons name="pause" size={24} color="#FFF" />
              <Text style={styles.pomodoroButtonText}>Pause</Text>
            </TouchableOpacity>
          )}
        </View>
        <Text style={[styles.sessionsLabel, { color: colors.textMuted }]}>
          Sessions completed today: {sessionsCompleted}
        </Text>
      </View>

      {/* Quick Actions */}
      <View style={styles.quickActions}>
        <TouchableOpacity
          style={[styles.quickAction, { backgroundColor: colors.primary + '20' }]}
          onPress={() => startPomodoro('work')}
        >
          <Ionicons name="rocket" size={20} color={colors.primary} />
          <Text style={[styles.quickActionText, { color: colors.primary }]}>25 min Focus</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.quickAction, { backgroundColor: '#10B981' + '20' }]}
          onPress={() => startPomodoro('short_break')}
        >
          <Ionicons name="cafe" size={20} color="#10B981" />
          <Text style={[styles.quickActionText, { color: '#10B981' }]}>5 min Break</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.quickAction, { backgroundColor: '#F59E0B' + '20' }]}
          onPress={() => startPomodoro('long_break')}
        >
          <Ionicons name="walk" size={20} color="#F59E0B" />
          <Text style={[styles.quickActionText, { color: '#F59E0B' }]}>15 min Break</Text>
        </TouchableOpacity>
      </View>

      {/* Pomodoro Benefits */}
      <View style={[styles.benefitsCard, { backgroundColor: colors.surface }]}>
        <Text style={[styles.cardTitle, { color: colors.text }]}>🍅 Why Pomodoro Works</Text>
        {[
          'Prevents mental fatigue',
          'Improves focus and concentration',
          'Creates healthy work boundaries',
          'Helps track productivity'
        ].map((benefit, i) => (
          <View key={i} style={styles.benefitRow}>
            <Ionicons name="checkmark-circle" size={16} color="#10B981" />
            <Text style={[styles.benefitText, { color: colors.textMuted }]}>{benefit}</Text>
          </View>
        ))}
      </View>
    </ScrollView>
  );

  const renderWellness = () => (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
      {/* Wellness Reminder */}
      {wellnessReminder && (
        <View style={[styles.wellnessCard, { backgroundColor: '#10B981' + '20' }]}>
          <Ionicons name="leaf" size={32} color="#10B981" />
          <Text style={[styles.wellnessType, { color: '#10B981' }]}>
            {wellnessReminder.type?.toUpperCase()}
          </Text>
          <Text style={[styles.wellnessMessage, { color: colors.text }]}>
            {wellnessReminder.message}
          </Text>
        </View>
      )}

      {/* Wellness Tips */}
      <Text style={[styles.sectionTitle, { color: colors.text }]}>Daily Wellness Tips</Text>
      {[
        { icon: 'eye', title: '20-20-20 Rule', desc: 'Every 20 min, look at something 20 feet away for 20 seconds' },
        { icon: 'water', title: 'Stay Hydrated', desc: 'Drink water regularly to maintain focus and energy' },
        { icon: 'body', title: 'Posture Check', desc: 'Sit up straight, relax your shoulders, feet flat on floor' },
        { icon: 'hand-left', title: 'Wrist Stretches', desc: 'Stretch your wrists and fingers every hour' },
        { icon: 'walk', title: 'Movement Breaks', desc: 'Take a short walk every 90 minutes' },
        { icon: 'moon', title: 'Sleep Well', desc: 'Aim for 7-9 hours of quality sleep' },
      ].map((tip, i) => (
        <View key={i} style={[styles.tipCard, { backgroundColor: colors.surface }]}>
          <View style={[styles.tipIcon, { backgroundColor: colors.primary + '20' }]}>
            <Ionicons name={tip.icon as any} size={20} color={colors.primary} />
          </View>
          <View style={styles.tipContent}>
            <Text style={[styles.tipTitle, { color: colors.text }]}>{tip.title}</Text>
            <Text style={[styles.tipDesc, { color: colors.textMuted }]}>{tip.desc}</Text>
          </View>
        </View>
      ))}
    </ScrollView>
  );

  const renderInsights = () => (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
      {/* Cognitive Load */}
      {cognitiveLoad && (
        <View style={[styles.insightCard, { backgroundColor: colors.surface }]}>
          <Text style={[styles.cardTitle, { color: colors.text }]}>🧠 Cognitive Load Analysis</Text>
          <View style={styles.loadMeter}>
            <View style={[
              styles.loadMeterFill, 
              { 
                width: `${(cognitiveLoad.load_score || 0) * 100}%`,
                backgroundColor: cognitiveLoad.cognitive_load_level === 'high' ? '#EF4444' : 
                               cognitiveLoad.cognitive_load_level === 'medium' ? '#F59E0B' : '#10B981'
              }
            ]} />
          </View>
          <Text style={[styles.loadLabel, { color: colors.textMuted }]}>
            Load Level: {cognitiveLoad.cognitive_load_level}
          </Text>
          {cognitiveLoad.break_recommended && (
            <View style={[styles.breakAlert, { backgroundColor: '#F59E0B' + '20' }]}>
              <Ionicons name="warning" size={16} color="#F59E0B" />
              <Text style={[styles.breakAlertText, { color: '#F59E0B' }]}>
                Break recommended!
              </Text>
            </View>
          )}
        </View>
      )}

      {/* Emotional Trends */}
      {psychologyProfile?.emotional_trends && Object.keys(psychologyProfile.emotional_trends).length > 0 && (
        <View style={[styles.insightCard, { backgroundColor: colors.surface }]}>
          <Text style={[styles.cardTitle, { color: colors.text }]}>📊 Emotional Trends</Text>
          {Object.entries(psychologyProfile.emotional_trends).map(([emotion, count]: [string, any]) => (
            <View key={emotion} style={styles.trendRow}>
              <View style={[styles.trendDot, { backgroundColor: EMOTION_COLORS[emotion] || colors.primary }]} />
              <Text style={[styles.trendLabel, { color: colors.text }]}>{emotion}</Text>
              <Text style={[styles.trendCount, { color: colors.textMuted }]}>{count}x</Text>
            </View>
          ))}
        </View>
      )}

      {/* EQ Capabilities */}
      {eqInfo && (
        <View style={[styles.insightCard, { backgroundColor: colors.surface }]}>
          <Text style={[styles.cardTitle, { color: colors.text }]}>✨ Jeeves EQ Capabilities</Text>
          {eqInfo.capabilities?.slice(0, 6).map((cap: string, i: number) => (
            <View key={i} style={styles.capabilityRow}>
              <Ionicons name="checkmark-circle" size={16} color="#10B981" />
              <Text style={[styles.capabilityText, { color: colors.textMuted }]}>{cap}</Text>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );

  const renderContent = () => {
    if (loading) {
      return (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={[styles.loadingText, { color: colors.textMuted }]}>Loading EQ data...</Text>
        </View>
      );
    }

    switch (activeTab) {
      case 'overview': return renderOverview();
      case 'pomodoro': return renderPomodoro();
      case 'wellness': return renderWellness();
      case 'insights': return renderInsights();
      default: return null;
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent>
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        {/* Header */}
        <View style={[styles.header, { backgroundColor: colors.surface, borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={onClose} style={styles.closeButton}>
            <Ionicons name="close" size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerCenter}>
            <Text style={[styles.headerTitle, { color: colors.text }]}>🧠 Jeeves EQ</Text>
            <Text style={[styles.headerSubtitle, { color: colors.textMuted }]}>
              Emotional Intelligence Dashboard
            </Text>
          </View>
          <View style={{ width: 32 }} />
        </View>

        {/* Tabs */}
        {renderTabs()}

        {/* Content */}
        {renderContent()}
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    marginTop: 40,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
  },
  closeButton: {
    padding: 4,
  },
  headerCenter: {
    alignItems: 'center',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  headerSubtitle: {
    fontSize: 12,
  },
  tabBar: {
    flexDirection: 'row',
    paddingHorizontal: 8,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.1)',
  },
  tab: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 12,
    gap: 4,
  },
  tabText: {
    fontSize: 11,
    fontWeight: '600',
  },
  content: {
    flex: 1,
    padding: 16,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 12,
  },
  loadingText: {
    fontSize: 14,
  },
  emotionCard: {
    borderRadius: 20,
    padding: 24,
    alignItems: 'center',
    marginBottom: 20,
  },
  emotionIconContainer: {
    width: 80,
    height: 80,
    borderRadius: 40,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  emotionLabel: {
    fontSize: 12,
    marginBottom: 4,
  },
  emotionName: {
    fontSize: 24,
    fontWeight: '800',
    marginBottom: 16,
  },
  intensityBar: {
    width: '80%',
    height: 8,
    borderRadius: 4,
    backgroundColor: 'rgba(255,255,255,0.2)',
    overflow: 'hidden',
  },
  intensityFill: {
    height: '100%',
    borderRadius: 4,
  },
  intensityLabel: {
    fontSize: 12,
    marginTop: 8,
  },
  therapeuticCard: {
    borderRadius: 16,
    padding: 20,
    marginBottom: 20,
  },
  therapeuticHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
  },
  therapeuticTitle: {
    fontSize: 16,
    fontWeight: '700',
  },
  therapeuticText: {
    fontSize: 14,
    lineHeight: 22,
  },
  statsGrid: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 20,
  },
  statCard: {
    flex: 1,
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 18,
    fontWeight: '800',
    marginTop: 8,
  },
  statLabel: {
    fontSize: 10,
    marginTop: 4,
    textAlign: 'center',
  },
  profileCard: {
    borderRadius: 16,
    padding: 20,
    marginBottom: 16,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 16,
  },
  profileRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.1)',
  },
  profileLabel: {
    fontSize: 14,
  },
  profileValue: {
    fontSize: 14,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  recommendationsCard: {
    borderRadius: 16,
    padding: 20,
    marginBottom: 16,
  },
  recommendationItem: {
    marginBottom: 16,
  },
  recommendationTitle: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },
  suggestionRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    marginBottom: 4,
  },
  suggestionText: {
    fontSize: 13,
    flex: 1,
  },
  pomodoroCard: {
    borderRadius: 20,
    padding: 32,
    alignItems: 'center',
    marginBottom: 20,
  },
  pomodoroTypeLabel: {
    fontSize: 16,
    marginBottom: 8,
  },
  pomodoroTimer: {
    fontSize: 64,
    fontWeight: '800',
    fontVariant: ['tabular-nums'],
  },
  pomodoroControls: {
    marginTop: 24,
  },
  pomodoroButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 32,
    paddingVertical: 14,
    borderRadius: 30,
    gap: 8,
  },
  pomodoroButtonText: {
    color: '#FFF',
    fontSize: 18,
    fontWeight: '700',
  },
  sessionsLabel: {
    fontSize: 12,
    marginTop: 16,
  },
  quickActions: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 20,
  },
  quickAction: {
    flex: 1,
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
    gap: 8,
  },
  quickActionText: {
    fontSize: 11,
    fontWeight: '600',
  },
  benefitsCard: {
    borderRadius: 16,
    padding: 20,
  },
  benefitRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },
  benefitText: {
    fontSize: 13,
  },
  wellnessCard: {
    borderRadius: 20,
    padding: 24,
    alignItems: 'center',
    marginBottom: 20,
  },
  wellnessType: {
    fontSize: 12,
    fontWeight: '700',
    marginTop: 12,
  },
  wellnessMessage: {
    fontSize: 16,
    textAlign: 'center',
    marginTop: 8,
    lineHeight: 24,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 12,
  },
  tipCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
    marginBottom: 10,
  },
  tipIcon: {
    width: 44,
    height: 44,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  tipContent: {
    flex: 1,
  },
  tipTitle: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 4,
  },
  tipDesc: {
    fontSize: 12,
  },
  insightCard: {
    borderRadius: 16,
    padding: 20,
    marginBottom: 16,
  },
  loadMeter: {
    height: 12,
    borderRadius: 6,
    backgroundColor: 'rgba(255,255,255,0.1)',
    overflow: 'hidden',
    marginBottom: 8,
  },
  loadMeterFill: {
    height: '100%',
    borderRadius: 6,
  },
  loadLabel: {
    fontSize: 12,
    textAlign: 'center',
  },
  breakAlert: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    padding: 12,
    borderRadius: 10,
    marginTop: 12,
  },
  breakAlertText: {
    fontSize: 14,
    fontWeight: '600',
  },
  trendRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
  },
  trendDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    marginRight: 12,
  },
  trendLabel: {
    flex: 1,
    fontSize: 14,
    textTransform: 'capitalize',
  },
  trendCount: {
    fontSize: 14,
    fontWeight: '600',
  },
  capabilityRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },
  capabilityText: {
    fontSize: 13,
    flex: 1,
  },
});

export default JeevesEQModal;
