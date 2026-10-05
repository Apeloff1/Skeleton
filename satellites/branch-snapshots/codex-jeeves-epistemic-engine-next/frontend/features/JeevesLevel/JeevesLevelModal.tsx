/**
 * Jeeves Level System UI — XP Tracker (1,000,000 cap)
 * Shows Jeeves' level, XP progress, interactions, vault learning stats
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

interface JeevesLevelModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
}

interface LevelData {
  level: number;
  xp: number;
  xp_to_next: number;
  total_interactions: number;
  matrices_parsed: number;
  vault_items_learned: number;
  idle_parse_count: number;
  level_cap: number;
}

interface MatrixStats {
  total_matrices: number;
  total_agents: number;
  total_active: number;
  total_dormant: number;
  per_agent: Record<string, number>;
}

export const JeevesLevelModal: React.FC<JeevesLevelModalProps> = ({ visible, onClose, colors }) => {
  const [levelData, setLevelData] = useState<LevelData | null>(null);
  const [matrixStats, setMatrixStats] = useState<MatrixStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (visible) loadData();
  }, [visible]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [lvlRes, matRes] = await Promise.all([
        apiFetch(`${API_BASE}/api/agents/jeeves/level`),
        apiFetch(`${API_BASE}/api/agents/matrices/global`),
      ]);
      if (lvlRes.ok) setLevelData(await lvlRes.json());
      if (matRes.ok) setMatrixStats(await matRes.json());
    } catch {}
    setLoading(false);
  };

  const triggerLearn = async () => {
    try {
      await apiFetch(`${API_BASE}/api/agents/jeeves/learn-vault`, { method: 'POST' });
      await loadData();
    } catch {}
  };

  const triggerParse = async () => {
    try {
      await apiFetch(`${API_BASE}/api/agents/jeeves/parse-idle`, { method: 'POST' });
      await loadData();
    } catch {}
  };

  if (!visible) return null;

  const xpProgress = levelData ? (levelData.xp / Math.max(1, levelData.xp_to_next)) * 100 : 0;
  const levelProgress = levelData ? (levelData.level / 1000000) * 100 : 0;

  // Rank title based on level
  const getRank = (level: number) => {
    if (level >= 900000) return { title: 'Transcendent', color: '#FF6B6B', icon: 'star' };
    if (level >= 500000) return { title: 'Legendary', color: '#F59E0B', icon: 'trophy' };
    if (level >= 100000) return { title: 'Mythic', color: '#A78BFA', icon: 'diamond' };
    if (level >= 50000) return { title: 'Master', color: '#EC4899', icon: 'ribbon' };
    if (level >= 10000) return { title: 'Expert', color: '#3B82F6', icon: 'medal' };
    if (level >= 1000) return { title: 'Veteran', color: '#10B981', icon: 'shield' };
    if (level >= 100) return { title: 'Adept', color: '#2563EB', icon: 'flash' };
    if (level >= 10) return { title: 'Apprentice', color: '#8B5CF6', icon: 'school' };
    return { title: 'Novice', color: '#6B7280', icon: 'book' };
  };

  const rank = getRank(levelData?.level || 1);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={[styles.overlay, { backgroundColor: colors.background }]}>
        {/* Header */}
        <View style={[styles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={onClose} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerCenter}>
            <Text style={[styles.headerTitle, { color: colors.text }]}>Jeeves Level System</Text>
            <Text style={[styles.headerSub, { color: colors.textMuted }]}>1,000,000 Level Cap</Text>
          </View>
        </View>

        {loading ? (
          <View style={styles.loadingView}>
            <ActivityIndicator size="large" color="#8B5CF6" />
          </View>
        ) : (
          <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
            {/* Level Hero Card */}
            <View style={[styles.heroCard, { backgroundColor: rank.color + '10', borderColor: rank.color + '30' }]}>
              <View style={[styles.levelCircle, { backgroundColor: rank.color }]}>
                <Text style={styles.levelNum}>{levelData?.level || 1}</Text>
              </View>
              <View style={[styles.rankBadge, { backgroundColor: rank.color + '20' }]}>
                <Ionicons name={rank.icon as any} size={14} color={rank.color} />
                <Text style={[styles.rankText, { color: rank.color }]}>{rank.title}</Text>
              </View>
              
              {/* XP Bar */}
              <View style={styles.xpSection}>
                <Text style={[styles.xpLabel, { color: colors.textMuted }]}>XP to Next Level</Text>
                <View style={[styles.xpBar, { backgroundColor: colors.border }]}>
                  <View style={[styles.xpFill, { width: `${Math.min(100, xpProgress)}%`, backgroundColor: rank.color }]} />
                </View>
                <Text style={[styles.xpText, { color: colors.text }]}>
                  {levelData?.xp || 0} / {levelData?.xp_to_next || 100} XP
                </Text>
              </View>

              {/* Overall Progress to Cap */}
              <View style={styles.xpSection}>
                <Text style={[styles.xpLabel, { color: colors.textMuted }]}>Progress to Cap (1,000,000)</Text>
                <View style={[styles.xpBar, { backgroundColor: colors.border }]}>
                  <View style={[styles.xpFill, { width: `${Math.max(0.5, levelProgress)}%`, backgroundColor: '#22C55E' }]} />
                </View>
                <Text style={[styles.xpText, { color: colors.text }]}>
                  {((levelData?.level || 0) / 10000).toFixed(2)}% complete
                </Text>
              </View>
            </View>

            {/* Stats Grid */}
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Statistics</Text>
            <View style={styles.statsGrid}>
              <View style={[styles.statCard, { backgroundColor: '#3B82F610', borderColor: '#3B82F630' }]}>
                <Ionicons name="chatbubbles" size={20} color="#3B82F6" />
                <Text style={[styles.statNum, { color: colors.text }]}>{levelData?.total_interactions || 0}</Text>
                <Text style={[styles.statLabel, { color: colors.textMuted }]}>Interactions</Text>
              </View>
              <View style={[styles.statCard, { backgroundColor: '#8B5CF610', borderColor: '#8B5CF630' }]}>
                <Ionicons name="grid" size={20} color="#8B5CF6" />
                <Text style={[styles.statNum, { color: colors.text }]}>{levelData?.matrices_parsed || 0}</Text>
                <Text style={[styles.statLabel, { color: colors.textMuted }]}>Matrices Parsed</Text>
              </View>
              <View style={[styles.statCard, { backgroundColor: '#22C55E10', borderColor: '#22C55E30' }]}>
                <Ionicons name="book" size={20} color="#22C55E" />
                <Text style={[styles.statNum, { color: colors.text }]}>{levelData?.vault_items_learned || 0}</Text>
                <Text style={[styles.statLabel, { color: colors.textMuted }]}>Vault Learned</Text>
              </View>
              <View style={[styles.statCard, { backgroundColor: '#F59E0B10', borderColor: '#F59E0B30' }]}>
                <Ionicons name="scan" size={20} color="#F59E0B" />
                <Text style={[styles.statNum, { color: colors.text }]}>{levelData?.idle_parse_count || 0}</Text>
                <Text style={[styles.statLabel, { color: colors.textMuted }]}>Idle Parses</Text>
              </View>
            </View>

            {/* Matrix Stats */}
            {matrixStats && (
              <>
                <Text style={[styles.sectionTitle, { color: colors.text }]}>Matrix Network</Text>
                <View style={[styles.matrixCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                  <View style={styles.matrixRow}>
                    <Text style={[styles.matrixLabel, { color: colors.textMuted }]}>Total Matrices</Text>
                    <Text style={[styles.matrixValue, { color: '#8B5CF6' }]}>{matrixStats.total_matrices.toLocaleString()}</Text>
                  </View>
                  <View style={styles.matrixRow}>
                    <Text style={[styles.matrixLabel, { color: colors.textMuted }]}>Active</Text>
                    <Text style={[styles.matrixValue, { color: '#22C55E' }]}>{matrixStats.total_active.toLocaleString()}</Text>
                  </View>
                  <View style={styles.matrixRow}>
                    <Text style={[styles.matrixLabel, { color: colors.textMuted }]}>Dormant</Text>
                    <Text style={[styles.matrixValue, { color: '#6B7280' }]}>{matrixStats.total_dormant.toLocaleString()}</Text>
                  </View>
                  <View style={styles.matrixRow}>
                    <Text style={[styles.matrixLabel, { color: colors.textMuted }]}>Agents</Text>
                    <Text style={[styles.matrixValue, { color: '#3B82F6' }]}>{matrixStats.total_agents}</Text>
                  </View>
                </View>
              </>
            )}

            {/* Actions */}
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Actions</Text>
            <TouchableOpacity style={[styles.actionBtn, { backgroundColor: '#8B5CF6' }]} onPress={triggerLearn}>
              <Ionicons name="book" size={18} color="#FFF" />
              <Text style={styles.actionBtnText}>Jeeves: Learn from Vault</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[styles.actionBtn, { backgroundColor: '#3B82F6', marginTop: 8 }]} onPress={triggerParse}>
              <Ionicons name="scan" size={18} color="#FFF" />
              <Text style={styles.actionBtnText}>Jeeves: Parse Idle Code</Text>
            </TouchableOpacity>

            <View style={{ height: 40 }} />
          </ScrollView>
        )}
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1 },
  backBtn: { padding: 4 },
  headerCenter: { flex: 1, marginLeft: 12 },
  headerTitle: { fontSize: 18, fontWeight: '700' },
  headerSub: { fontSize: 11, marginTop: 2 },
  loadingView: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  content: { flex: 1, paddingHorizontal: 16 },
  heroCard: { alignItems: 'center', padding: 24, borderRadius: 20, marginTop: 16, borderWidth: 1, gap: 12 },
  levelCircle: { width: 80, height: 80, borderRadius: 40, justifyContent: 'center', alignItems: 'center' },
  levelNum: { color: '#FFF', fontSize: 24, fontWeight: '900' },
  rankBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 6, borderRadius: 10 },
  rankText: { fontSize: 14, fontWeight: '800' },
  xpSection: { width: '100%', gap: 4, marginTop: 4 },
  xpLabel: { fontSize: 11, textAlign: 'center' },
  xpBar: { height: 10, borderRadius: 5, overflow: 'hidden' },
  xpFill: { height: '100%', borderRadius: 5 },
  xpText: { fontSize: 13, fontWeight: '700', textAlign: 'center' },
  sectionTitle: { fontSize: 16, fontWeight: '700', marginTop: 20, marginBottom: 10 },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  statCard: { width: '48%', alignItems: 'center', padding: 14, borderRadius: 14, borderWidth: 1, gap: 6 },
  statNum: { fontSize: 20, fontWeight: '800' },
  statLabel: { fontSize: 11 },
  matrixCard: { borderRadius: 14, borderWidth: 1, overflow: 'hidden' },
  matrixRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 0.5, borderBottomColor: 'rgba(255,255,255,0.05)' },
  matrixLabel: { fontSize: 14 },
  matrixValue: { fontSize: 16, fontWeight: '800' },
  actionBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, padding: 14, borderRadius: 12 },
  actionBtnText: { color: '#FFF', fontSize: 14, fontWeight: '700' },
});
