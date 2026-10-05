/**
 * Gamification Dashboard — XP, Levels, Skill Tree, Rank Progression
 */
import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, Modal, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const RANK_COLORS: Record<string, string> = {
  Novice: '#94A3B8', Initiate: '#8B5CF6', Apprentice: '#3B82F6',
  Journeyman: '#10B981', Adept: '#F59E0B', Expert: '#EC4899',
  Master: '#EF4444', Grandmaster: '#FF6B35', Transcendent: '#FFD700',
};

interface Props { visible: boolean; onClose: () => void; }

export const GamificationModal: React.FC<Props> = ({ visible, onClose }) => {
  const [profile, setProfile] = useState<any>(null);
  const [xpTable, setXpTable] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<'profile'|'skills'|'ranks'>('profile');

  useEffect(() => {
    if (visible) loadData();
  }, [visible]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [pRes, xRes] = await Promise.all([
        apiFetch(`${API}/api/gamification/profile/default_user`),
        apiFetch(`${API}/api/gamification/xp-table`),
      ]);
      if (pRes.ok) setProfile(await pRes.json());
      if (xRes.ok) setXpTable(await xRes.json());
    } catch {}
    setLoading(false);
  };

  const rankColor = RANK_COLORS[profile?.rank] || '#94A3B8';

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={st.container}>
        <View style={st.header}>
          <TouchableOpacity testID="gam-close" onPress={onClose} style={st.hBtn}>
            <Ionicons name="close" size={24} color="#F8FAFC" />
          </TouchableOpacity>
          <Text style={st.hTitle}>Gamification</Text>
          <View style={st.hBtn} />
        </View>

        {loading ? (
          <View style={st.loadWrap}><ActivityIndicator size="large" color="#F59E0B" /></View>
        ) : (
          <ScrollView style={st.scroll} showsVerticalScrollIndicator={false}>
            {/* XP Card */}
            <View style={[st.xpCard, { borderColor: rankColor }]}>
              <View style={st.xpTop}>
                <View>
                  <Text style={[st.rankBadge, { color: rankColor }]}>{profile?.rank || 'Novice'}</Text>
                  <Text style={st.levelText}>Level {profile?.level || 1}</Text>
                </View>
                <View style={st.xpRight}>
                  <Text style={st.xpBig}>{(profile?.total_xp || 0).toLocaleString()}</Text>
                  <Text style={st.xpLabel}>Total XP</Text>
                </View>
              </View>
              <View style={st.progressBarBg}>
                <View style={[st.progressBarFill, { width: `${profile?.progress_pct || 0}%`, backgroundColor: rankColor }]} />
              </View>
              <Text style={st.progressText}>{profile?.xp_to_next?.toLocaleString() || 0} XP to next level</Text>
            </View>

            {/* Stats Row */}
            <View style={st.statsRow}>
              <View style={st.statItem}>
                <Text style={st.statNum}>{profile?.activities_count || 0}</Text>
                <Text style={st.statLabel}>Activities</Text>
              </View>
              <View style={st.statItem}>
                <Text style={st.statNum}>{profile?.domain_count || 0}</Text>
                <Text style={st.statLabel}>Domains</Text>
              </View>
              <View style={st.statItem}>
                <Text style={st.statNum}>{profile?.level || 1}</Text>
                <Text style={st.statLabel}>Level</Text>
              </View>
            </View>

            {/* View Tabs */}
            <View style={st.tabs}>
              {(['profile','skills','ranks'] as const).map(t => (
                <TouchableOpacity key={t} style={[st.tab, view===t && st.tabActive]} onPress={() => setView(t)}>
                  <Text style={[st.tabText, view===t && st.tabTextActive]}>{t.charAt(0).toUpperCase()+t.slice(1)}</Text>
                </TouchableOpacity>
              ))}
            </View>

            {view === 'skills' && (
              <>
                <Text style={st.sectionTitle}>SKILL TREE</Text>
                {(profile?.skill_tree || []).length === 0 ? (
                  <Text style={st.emptyText}>Complete activities to unlock skill domains!</Text>
                ) : (
                  (profile?.skill_tree || []).map((skill: any) => (
                    <View key={skill.domain} style={st.skillRow}>
                      <View style={st.skillInfo}>
                        <Text style={st.skillName}>{skill.domain.replace(/_/g,' ')}</Text>
                        <Text style={st.skillMeta}>Lv.{skill.level} • {skill.rank} • {skill.xp.toLocaleString()} XP</Text>
                      </View>
                      <View style={st.skillBarBg}>
                        <View style={[st.skillBarFill, { width: `${Math.min(100,skill.mastery_pct)}%`, backgroundColor: RANK_COLORS[skill.rank] || '#8B5CF6' }]} />
                      </View>
                    </View>
                  ))
                )}
              </>
            )}

            {view === 'ranks' && xpTable && (
              <>
                <Text style={st.sectionTitle}>RANK PROGRESSION</Text>
                {(xpTable.ranks || []).map((rank: any) => {
                  const isCurrentOrBelow = (profile?.level || 1) >= rank.min_level;
                  const color = RANK_COLORS[rank.name] || '#94A3B8';
                  return (
                    <View key={rank.name} style={[st.rankRow, isCurrentOrBelow && { borderLeftColor: color, borderLeftWidth: 3 }]}>
                      <View style={[st.rankIcon, { backgroundColor: color + '20' }]}>
                        <Ionicons name={isCurrentOrBelow ? 'checkmark-circle' : 'lock-closed'} size={20} color={color} />
                      </View>
                      <View style={st.rankInfo}>
                        <Text style={[st.rankName, { color: isCurrentOrBelow ? color : '#64748B' }]}>{rank.name}</Text>
                        <Text style={st.rankLevel}>Level {rank.min_level}+</Text>
                      </View>
                    </View>
                  );
                })}

                <Text style={st.sectionTitle}>XP REWARD TABLE</Text>
                {Object.entries(xpTable.xp_table || {}).map(([activity, xp]) => (
                  <View key={activity} style={st.xpRow}>
                    <Text style={st.xpActivity}>{activity.replace(/_/g,' ')}</Text>
                    <Text style={st.xpReward}>+{xp as number} XP</Text>
                  </View>
                ))}
              </>
            )}

            {view === 'profile' && (
              <>
                <Text style={st.sectionTitle}>QUICK ACTIONS</Text>
                <Text style={st.infoText}>
                  Every quiz, book, pomodoro session, code execution, and daily challenge earns XP.
                  Level up across {profile?.domain_count || 0} skill domains. Reach Transcendent rank at Level 100!
                </Text>
                <View style={st.tipCard}>
                  <Ionicons name="bulb" size={20} color="#F59E0B" />
                  <Text style={st.tipText}>Complete a daily challenge for +25 XP. Perfect score: +75 XP!</Text>
                </View>
                <View style={st.tipCard}>
                  <Ionicons name="flame" size={20} color="#EF4444" />
                  <Text style={st.tipText}>Maintain streaks: +10 XP/day, +100 XP/week, +500 XP/month</Text>
                </View>
                <View style={st.tipCard}>
                  <Ionicons name="code-slash" size={20} color="#3B82F6" />
                  <Text style={st.tipText}>Execute code in the playground: +10 XP per run, +15 for clean runs</Text>
                </View>
              </>
            )}

            <View style={{ height: 40 }} />
          </ScrollView>
        )}
      </View>
    </Modal>
  );
};

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F172A' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, backgroundColor: '#1E293B', borderBottomWidth: 1, borderBottomColor: '#334155' },
  hBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  hTitle: { flex: 1, fontSize: 18, fontWeight: '700', color: '#F8FAFC', textAlign: 'center' },
  loadWrap: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  scroll: { flex: 1, paddingHorizontal: 16 },
  xpCard: { backgroundColor: '#1E293B', borderRadius: 16, padding: 20, marginTop: 16, borderWidth: 2 },
  xpTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  rankBadge: { fontSize: 22, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1 },
  levelText: { fontSize: 14, color: '#94A3B8', marginTop: 4 },
  xpRight: { alignItems: 'flex-end' },
  xpBig: { fontSize: 32, fontWeight: '800', color: '#F59E0B' },
  xpLabel: { fontSize: 12, color: '#94A3B8' },
  progressBarBg: { height: 10, borderRadius: 5, backgroundColor: '#0F172A', marginTop: 16, overflow: 'hidden' },
  progressBarFill: { height: '100%', borderRadius: 5 },
  progressText: { fontSize: 12, color: '#64748B', marginTop: 6, textAlign: 'right' },
  statsRow: { flexDirection: 'row', gap: 12, marginTop: 16 },
  statItem: { flex: 1, backgroundColor: '#1E293B', borderRadius: 12, padding: 16, alignItems: 'center' },
  statNum: { fontSize: 22, fontWeight: '800', color: '#F8FAFC' },
  statLabel: { fontSize: 11, color: '#64748B', marginTop: 4, textTransform: 'uppercase', letterSpacing: 0.5 },
  tabs: { flexDirection: 'row', gap: 8, marginTop: 16 },
  tab: { flex: 1, paddingVertical: 10, borderRadius: 10, alignItems: 'center', backgroundColor: '#1E293B' },
  tabActive: { backgroundColor: '#F59E0B20' },
  tabText: { fontSize: 13, fontWeight: '600', color: '#64748B' },
  tabTextActive: { color: '#F59E0B' },
  sectionTitle: { fontSize: 11, fontWeight: '800', color: '#64748B', letterSpacing: 1.5, marginTop: 20, marginBottom: 10 },
  emptyText: { color: '#64748B', fontSize: 13, textAlign: 'center', paddingVertical: 20 },
  skillRow: { backgroundColor: '#1E293B', borderRadius: 10, padding: 14, marginBottom: 8 },
  skillInfo: { marginBottom: 8 },
  skillName: { fontSize: 14, fontWeight: '700', color: '#F8FAFC', textTransform: 'capitalize' },
  skillMeta: { fontSize: 11, color: '#94A3B8', marginTop: 2 },
  skillBarBg: { height: 6, borderRadius: 3, backgroundColor: '#0F172A', overflow: 'hidden' },
  skillBarFill: { height: '100%', borderRadius: 3 },
  rankRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1E293B', borderRadius: 10, padding: 12, marginBottom: 6 },
  rankIcon: { width: 40, height: 40, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  rankInfo: { marginLeft: 12 },
  rankName: { fontSize: 15, fontWeight: '700' },
  rankLevel: { fontSize: 11, color: '#64748B', marginTop: 2 },
  xpRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, paddingHorizontal: 12, backgroundColor: '#1E293B', borderRadius: 8, marginBottom: 4 },
  xpActivity: { fontSize: 13, color: '#F8FAFC', textTransform: 'capitalize' },
  xpReward: { fontSize: 13, fontWeight: '700', color: '#F59E0B' },
  infoText: { fontSize: 13, color: '#94A3B8', lineHeight: 20, marginBottom: 12 },
  tipCard: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#1E293B', borderRadius: 10, padding: 14, marginBottom: 8 },
  tipText: { flex: 1, fontSize: 13, color: '#F8FAFC', lineHeight: 18 },
});
