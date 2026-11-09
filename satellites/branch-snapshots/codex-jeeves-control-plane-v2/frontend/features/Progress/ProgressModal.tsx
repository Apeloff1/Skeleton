/**
 * Progress Modal v16.0
 * Shows user's overall learning progress overview
 */

import React, { useState, useEffect } from 'react';
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

interface ProgressModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
}

export const ProgressModal: React.FC<ProgressModalProps> = ({
  visible, onClose, colors
}) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (visible) loadProgress();
  }, [visible]);

  const loadProgress = async () => {
    setLoading(true);
    try {
      const res = await apiFetch(`${API_BASE}/api/class-progress/user/default_user/overview`);
      if (res.ok) {
        setData(await res.json());
      }
    } catch {
      setData({
        total_completions: 0, unique_classes: 0, unique_languages: 0,
        languages_studied: [], total_xp: 0, level: 1,
        achievements_count: 0, repeated_classes: [],
      });
    }
    setLoading(false);
  };

  const statCards = data ? [
    { label: 'Total Completions', value: data.total_completions, icon: 'book', color: '#3B82F6' },
    { label: 'Unique Classes', value: data.unique_classes, icon: 'layers', color: '#8B5CF6' },
    { label: 'Languages Studied', value: data.unique_languages, icon: 'globe', color: '#10B981' },
    { label: 'Total XP', value: data.total_xp, icon: 'star', color: '#F59E0B' },
    { label: 'Level', value: data.level, icon: 'trending-up', color: '#EC4899' },
    { label: 'Achievements', value: data.achievements_count, icon: 'trophy', color: '#EF4444' },
  ] : [];

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={[styles.overlay, { backgroundColor: colors.background }]}>
        <View style={[styles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={onClose} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color={colors.text} />
          </TouchableOpacity>
          <Text style={[styles.headerTitle, { color: colors.text }]}>My Progress</Text>
          <View style={{ width: 32 }} />
        </View>

        {loading ? (
          <View style={styles.loadingView}>
            <ActivityIndicator size="large" color={colors.primary} />
          </View>
        ) : (
          <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
            {/* Level Header */}
            <View style={[styles.levelCard, { backgroundColor: colors.primary + '15', borderColor: colors.primary + '30' }]}>
              <View style={[styles.levelCircle, { backgroundColor: colors.primary }]}>
                <Text style={styles.levelNumber}>{data?.level || 1}</Text>
              </View>
              <View style={styles.levelInfo}>
                <Text style={[styles.levelTitle, { color: colors.text }]}>Level {data?.level || 1}</Text>
                <Text style={[styles.levelXp, { color: colors.textMuted }]}>{data?.total_xp || 0} XP earned</Text>
              </View>
            </View>

            {/* Stats Grid */}
            <View style={styles.statsGrid}>
              {statCards.map((stat, idx) => (
                <View key={idx} style={[styles.statCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                  <View style={[styles.statIcon, { backgroundColor: stat.color + '15' }]}>
                    <Ionicons name={stat.icon as any} size={20} color={stat.color} />
                  </View>
                  <Text style={[styles.statValue, { color: colors.text }]}>{stat.value}</Text>
                  <Text style={[styles.statLabel, { color: colors.textMuted }]}>{stat.label}</Text>
                </View>
              ))}
            </View>

            {/* Languages Studied */}
            {data?.languages_studied && data.languages_studied.length > 0 && (
              <>
                <Text style={[styles.sectionTitle, { color: colors.text }]}>Languages Studied</Text>
                <View style={styles.tagRow}>
                  {data.languages_studied.map((lang: string, idx: number) => (
                    <View key={idx} style={[styles.langTag, { backgroundColor: '#10B98120' }]}>
                      <Text style={styles.langTagText}>{lang}</Text>
                    </View>
                  ))}
                </View>
              </>
            )}

            {/* Most Repeated Classes */}
            {data?.repeated_classes && data.repeated_classes.length > 0 && (
              <>
                <Text style={[styles.sectionTitle, { color: colors.text }]}>Most Repeated Classes</Text>
                {data.repeated_classes.map((cls: any, idx: number) => (
                  <View key={idx} style={[styles.repeatItem, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                    <View style={[styles.repeatRank, { backgroundColor: idx === 0 ? '#F59E0B20' : colors.background }]}>
                      <Text style={[styles.repeatRankText, { color: idx === 0 ? '#F59E0B' : colors.textMuted }]}>#{idx + 1}</Text>
                    </View>
                    <View style={styles.repeatInfo}>
                      <Text style={[styles.repeatName, { color: colors.text }]}>{cls.class_name}</Text>
                      <Text style={[styles.repeatCount, { color: colors.textMuted }]}>
                        Completed {cls.times_completed}x
                      </Text>
                    </View>
                    <Ionicons name="refresh-circle" size={20} color="#8B5CF6" />
                  </View>
                ))}
              </>
            )}

            <View style={{ height: 40 }} />
          </ScrollView>
        )}
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
  headerTitle: { flex: 1, fontSize: 18, fontWeight: '700', textAlign: 'center' },
  loadingView: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  content: { flex: 1, paddingHorizontal: 16 },
  levelCard: {
    flexDirection: 'row', alignItems: 'center', padding: 16,
    borderRadius: 16, marginTop: 16, borderWidth: 1, gap: 14,
  },
  levelCircle: {
    width: 56, height: 56, borderRadius: 28, justifyContent: 'center', alignItems: 'center',
  },
  levelNumber: { color: '#FFF', fontSize: 24, fontWeight: '800' },
  levelInfo: { flex: 1 },
  levelTitle: { fontSize: 20, fontWeight: '700' },
  levelXp: { fontSize: 14, marginTop: 2 },
  statsGrid: {
    flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 16,
  },
  statCard: {
    width: '47%', padding: 14, borderRadius: 14, borderWidth: 1, alignItems: 'center',
  },
  statIcon: {
    width: 40, height: 40, borderRadius: 12, justifyContent: 'center', alignItems: 'center', marginBottom: 8,
  },
  statValue: { fontSize: 24, fontWeight: '800' },
  statLabel: { fontSize: 12, marginTop: 4 },
  sectionTitle: { fontSize: 16, fontWeight: '700', marginTop: 20, marginBottom: 10 },
  tagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  langTag: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 10 },
  langTagText: { color: '#10B981', fontSize: 13, fontWeight: '600' },
  repeatItem: {
    flexDirection: 'row', alignItems: 'center', padding: 12,
    borderRadius: 12, marginBottom: 8, borderWidth: 1, gap: 10,
  },
  repeatRank: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  repeatRankText: { fontSize: 14, fontWeight: '700' },
  repeatInfo: { flex: 1 },
  repeatName: { fontSize: 14, fontWeight: '600' },
  repeatCount: { fontSize: 12, marginTop: 2 },
});
