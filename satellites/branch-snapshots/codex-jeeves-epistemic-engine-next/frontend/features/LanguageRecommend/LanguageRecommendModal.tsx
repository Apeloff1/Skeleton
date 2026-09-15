/**
 * Language Recommend Modal v16.0
 * Jeeves recommends the best programming language for your goals
 */

import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  Modal, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';

import { apiFetch } from '../../utils/apiController';
const API_BASE = (() => {
  if (typeof window !== 'undefined' && (window as any).location?.origin && !(window as any).location.origin.startsWith('file:')) {
    return (window as any).location.origin.replace(/\/+$/, '');
  }
  return (Constants.expoConfig?.extra?.EXPO_PUBLIC_BACKEND_URL as string)
    || process.env.EXPO_PUBLIC_BACKEND_URL || '';
})();

interface LanguageRecommendModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
}

const GOAL_OPTIONS = [
  { id: 'web', label: 'Web Development', icon: 'globe', color: '#3B82F6' },
  { id: 'mobile', label: 'Mobile Apps', icon: 'phone-portrait', color: '#8B5CF6' },
  { id: 'game', label: 'Game Development', icon: 'game-controller', color: '#EC4899' },
  { id: 'data', label: 'Data Science', icon: 'analytics', color: '#10B981' },
  { id: 'ai', label: 'AI / Machine Learning', icon: 'hardware-chip', color: '#F59E0B' },
  { id: 'systems', label: 'Systems Programming', icon: 'terminal', color: '#EF4444' },
  { id: 'blockchain', label: 'Blockchain / Web3', icon: 'link', color: '#6366F1' },
  { id: 'devops', label: 'DevOps / Cloud', icon: 'cloud', color: '#2563EB' },
  { id: 'embedded', label: 'Embedded / IoT', icon: 'hardware-chip', color: '#84CC16' },
  { id: 'functional', label: 'Functional Programming', icon: 'infinite', color: '#A855F7' },
  { id: 'enterprise', label: 'Enterprise Software', icon: 'business', color: '#3B82F6' },
  { id: 'beginner', label: "I'm a Beginner!", icon: 'school', color: '#22C55E' },
];

export const LanguageRecommendModal: React.FC<LanguageRecommendModalProps> = ({
  visible, onClose, colors
}) => {
  const [selectedGoal, setSelectedGoal] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handleSelectGoal = async (goalId: string) => {
    setSelectedGoal(goalId);
    setLoading(true);
    try {
      const res = await apiFetch(`${API_BASE}/api/jeeves-languages/recommend?goal=${goalId}`);
      if (res.ok) {
        setRecommendations(await res.json());
      }
    } catch {
      setRecommendations({
        goal: goalId,
        recommendations: [{ id: 'python', name: 'Python', reason: 'Great all-rounder', greeting: 'Start with Python!' }],
        jeeves_advice: 'I recommend starting with Python, an excellent choice for any path.',
      });
    }
    setLoading(false);
  };

  const handleReset = () => {
    setSelectedGoal(null);
    setRecommendations(null);
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={[styles.overlay, { backgroundColor: colors.background }]}>
        <View style={[styles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={onClose} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerCenter}>
            <Text style={[styles.headerTitle, { color: colors.text }]}>Language Advisor</Text>
            <Text style={[styles.headerSub, { color: colors.textMuted }]}>Powered by Jeeves</Text>
          </View>
          {selectedGoal && (
            <TouchableOpacity onPress={handleReset}>
              <Text style={{ color: colors.primary, fontWeight: '600' }}>Reset</Text>
            </TouchableOpacity>
          )}
        </View>

        <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
          {!selectedGoal ? (
            <>
              <Text style={[styles.prompt, { color: colors.text }]}>
                What do you want to build?
              </Text>
              <Text style={[styles.promptSub, { color: colors.textMuted }]}>
                I&apos;ll recommend the best language for your goals.
              </Text>
              <View style={styles.goalGrid}>
                {GOAL_OPTIONS.map(goal => (
                  <TouchableOpacity
                    key={goal.id}
                    style={[styles.goalCard, { backgroundColor: goal.color + '10', borderColor: goal.color + '30' }]}
                    onPress={() => handleSelectGoal(goal.id)}
                  >
                    <View style={[styles.goalIcon, { backgroundColor: goal.color + '20' }]}>
                      <Ionicons name={goal.icon as any} size={22} color={goal.color} />
                    </View>
                    <Text style={[styles.goalLabel, { color: colors.text }]}>{goal.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </>
          ) : loading ? (
            <View style={styles.loadingView}>
              <ActivityIndicator size="large" color={colors.primary} />
              <Text style={[styles.loadingText, { color: colors.textMuted }]}>Jeeves is thinking...</Text>
            </View>
          ) : recommendations ? (
            <>
              {/* Jeeves Advice */}
              <View style={[styles.adviceCard, { backgroundColor: colors.primary + '15', borderColor: colors.primary + '30' }]}>
                <Ionicons name="chatbubbles" size={20} color={colors.primary} />
                <Text style={[styles.adviceText, { color: colors.text }]}>
                  {recommendations.jeeves_advice}
                </Text>
              </View>

              <Text style={[styles.sectionTitle, { color: colors.text }]}>Recommended Languages</Text>
              {recommendations.recommendations?.map((rec: any, idx: number) => (
                <View
                  key={rec.id}
                  style={[
                    styles.recCard,
                    {
                      backgroundColor: idx === 0 ? '#F59E0B10' : colors.surface,
                      borderColor: idx === 0 ? '#F59E0B40' : colors.border,
                    }
                  ]}
                >
                  <View style={styles.recHeader}>
                    <View style={[styles.recRank, { backgroundColor: idx === 0 ? '#F59E0B20' : colors.background }]}>
                      <Text style={[styles.recRankText, { color: idx === 0 ? '#F59E0B' : colors.textMuted }]}>#{idx + 1}</Text>
                    </View>
                    <View style={styles.recInfo}>
                      <Text style={[styles.recName, { color: colors.text }]}>{rec.name}</Text>
                      <Text style={[styles.recReason, { color: colors.textMuted }]}>{rec.reason}</Text>
                    </View>
                  </View>
                  {rec.greeting && (
                    <Text style={[styles.recGreeting, { color: colors.textMuted }]}>{rec.greeting}</Text>
                  )}
                </View>
              ))}
            </>
          ) : null}

          <View style={{ height: 40 }} />
        </ScrollView>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: { flex: 1 },
  header: {
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16,
    paddingVertical: 14, borderBottomWidth: 1,
  },
  backBtn: { padding: 4 },
  headerCenter: { flex: 1, marginLeft: 12 },
  headerTitle: { fontSize: 18, fontWeight: '700' },
  headerSub: { fontSize: 12, marginTop: 2 },
  content: { flex: 1, paddingHorizontal: 16 },
  prompt: { fontSize: 22, fontWeight: '800', marginTop: 24 },
  promptSub: { fontSize: 14, marginTop: 6, marginBottom: 20 },
  goalGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  goalCard: {
    width: '47%', padding: 16, borderRadius: 14, borderWidth: 1,
    alignItems: 'center', gap: 10,
  },
  goalIcon: { width: 44, height: 44, borderRadius: 14, justifyContent: 'center', alignItems: 'center' },
  goalLabel: { fontSize: 13, fontWeight: '600', textAlign: 'center' },
  loadingView: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingTop: 80, gap: 12 },
  loadingText: { fontSize: 14 },
  adviceCard: {
    flexDirection: 'row', alignItems: 'flex-start', padding: 14, borderRadius: 12,
    marginTop: 16, gap: 10, borderWidth: 1,
  },
  adviceText: { flex: 1, fontSize: 14, lineHeight: 20 },
  sectionTitle: { fontSize: 16, fontWeight: '700', marginTop: 20, marginBottom: 10 },
  recCard: {
    padding: 14, borderRadius: 14, marginBottom: 10, borderWidth: 1,
  },
  recHeader: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  recRank: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  recRankText: { fontSize: 14, fontWeight: '700' },
  recInfo: { flex: 1 },
  recName: { fontSize: 16, fontWeight: '700' },
  recReason: { fontSize: 13, marginTop: 2 },
  recGreeting: { fontSize: 13, marginTop: 8, fontStyle: 'italic' },
});
