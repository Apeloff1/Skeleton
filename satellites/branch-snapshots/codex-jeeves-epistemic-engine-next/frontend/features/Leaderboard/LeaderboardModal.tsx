/**
 * Hyperscale Leaderboard Hub — 10 boards, time ranges, tier system
 */
import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Modal, ScrollView, ActivityIndicator, FlatList } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const TIME_RANGES = [
  { id: 'all_time', label: 'All Time' },
  { id: 'monthly', label: 'Monthly' },
  { id: 'weekly', label: 'Weekly' },
  { id: 'daily', label: 'Today' },
];

interface Props { visible: boolean; onClose: () => void; colors?: any; }

export const LeaderboardModal: React.FC<Props> = ({ visible, onClose }) => {
  const [boards, setBoards] = useState<any[]>([]);
  const [selectedBoard, setSelectedBoard] = useState<string | null>(null);
  const [timeRange, setTimeRange] = useState('all_time');
  const [entries, setEntries] = useState<any[]>([]);
  const [boardInfo, setBoardInfo] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState<'hub' | 'board' | 'profile'>('hub');
  const [userRankings, setUserRankings] = useState<any[]>([]);

  useEffect(() => {
    if (visible) loadBoards();
  }, [visible]);

  const loadBoards = async () => {
    setLoading(true);
    try {
      const [bRes, sRes] = await Promise.all([
        apiFetch(`${API}/api/leaderboards/boards`),
        apiFetch(`${API}/api/leaderboards/stats`),
      ]);
      if (bRes.ok) { const d = await bRes.json(); setBoards(d.boards || []); }
      if (sRes.ok) { setStats(await sRes.json()); }
    } catch {}
    setLoading(false);
  };

  const loadBoard = async (boardId: string, range = 'all_time') => {
    setLoading(true);
    setSelectedBoard(boardId);
    setTimeRange(range);
    setPhase('board');
    try {
      const r = await apiFetch(`${API}/api/leaderboards/board/${boardId}?time_range=${range}&limit=50`);
      if (r.ok) {
        const d = await r.json();
        setEntries(d.entries || []);
        setBoardInfo(d.board);
      }
    } catch {}
    setLoading(false);
  };

  const loadProfile = async () => {
    setLoading(true);
    setPhase('profile');
    try {
      const r = await apiFetch(`${API}/api/leaderboards/user/default_user`);
      if (r.ok) {
        const d = await r.json();
        setUserRankings(d.rankings || []);
      }
    } catch {}
    setLoading(false);
  };

  const goBack = () => {
    if (phase === 'board' || phase === 'profile') setPhase('hub');
    else onClose();
  };

  const getRankStyle = (rank: number) => {
    if (rank === 1) return { bg: '#F59E0B20', border: '#F59E0B', text: '#F59E0B' };
    if (rank === 2) return { bg: '#94A3B820', border: '#94A3B8', text: '#94A3B8' };
    if (rank === 3) return { bg: '#CD7F3220', border: '#CD7F32', text: '#CD7F32' };
    return { bg: '#1E293B', border: '#334155', text: '#64748B' };
  };

  const getMetricLabel = (board: any, entry: any): string => {
    switch (board?.id) {
      case 'xp_champions': return `${(entry.total_xp || 0).toLocaleString()} XP`;
      case 'rosetta_masters': return `${(entry.challenge_score || 0).toLocaleString()} pts`;
      case 'code_warriors': return `${(entry.executions || 0).toLocaleString()} runs`;
      case 'quiz_champions': return `${(entry.quiz_score || 0).toLocaleString()} pts`;
      case 'streak_kings': return `${entry.streak_days || 0}d streak`;
      case 'polyglots': return `${entry.languages_count || 0} langs`;
      case 'achievement_hunters': return `${entry.achievements || 0} unlocked`;
      case 'daily_heroes': return `${(entry.daily_score || 0).toLocaleString()} pts`;
      case 'speed_coders': return `${entry.avg_time_ms || 0}ms avg`;
      case 'bug_crushers': return `${(entry.bugs_fixed || 0).toLocaleString()} fixed`;
      default: return '';
    }
  };

  const getSubMetric = (board: any, entry: any): string => {
    switch (board?.id) {
      case 'xp_champions': return `Lvl ${entry.level || 1} • ${entry.activities || 0} activities`;
      case 'rosetta_masters': return `${entry.challenges_completed || 0} challenges • ${entry.perfect_scores || 0} perfect`;
      case 'code_warriors': return `${entry.successful || 0} success • ${entry.languages_used || 0} langs`;
      case 'quiz_champions': return `${entry.quizzes_taken || 0} quizzes • ${Math.round((entry.accuracy || 0) * 100)}% acc`;
      case 'streak_kings': return `Best: ${entry.longest_streak || 0}d • ${entry.total_active_days || 0} active`;
      case 'polyglots': return `${entry.classes_completed || 0} classes`;
      case 'achievement_hunters': return `${entry.rare_achievements || 0} rare • ${entry.legendary_achievements || 0} legendary`;
      case 'daily_heroes': return `${entry.challenges_completed || 0} days • ${entry.perfect_days || 0} perfect`;
      case 'speed_coders': return `Fastest: ${entry.fastest_time_ms || 0}ms • ${entry.total_runs || 0} runs`;
      case 'bug_crushers': return `${entry.critical_bugs || 0} critical • ${Math.round((entry.fix_rate || 0) * 100)}% rate`;
      default: return '';
    }
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={goBack}>
      <View style={st.container}>
        {/* Header */}
        <View style={st.header}>
          <TouchableOpacity testID="lb-back" onPress={goBack} style={st.hBtn}>
            <Ionicons name={phase === 'hub' ? 'close' : 'arrow-back'} size={24} color="#F8FAFC" />
          </TouchableOpacity>
          <Text style={st.hTitle}>
            {phase === 'hub' ? 'Leaderboards' : phase === 'profile' ? 'My Rankings' : boardInfo?.name || 'Board'}
          </Text>
          <TouchableOpacity testID="lb-profile" onPress={loadProfile} style={st.hBtn}>
            <Ionicons name="person-circle" size={24} color="#F59E0B" />
          </TouchableOpacity>
        </View>

        {loading ? (
          <View style={st.loadingView}><ActivityIndicator size="large" color="#F59E0B" /></View>
        ) : phase === 'hub' ? (
          <ScrollView style={st.scroll} showsVerticalScrollIndicator={false}>
            {/* Stats Banner */}
            {stats && (
              <View style={st.statsBanner}>
                <View style={st.statItem}>
                  <Text style={st.statNum}>{(stats.unique_users || 0).toLocaleString()}</Text>
                  <Text style={st.statLabel}>Players</Text>
                </View>
                <View style={st.statDivider} />
                <View style={st.statItem}>
                  <Text style={st.statNum}>{stats.total_boards || 0}</Text>
                  <Text style={st.statLabel}>Boards</Text>
                </View>
                <View style={st.statDivider} />
                <View style={st.statItem}>
                  <Text style={st.statNum}>{(stats.total_entries || 0).toLocaleString()}</Text>
                  <Text style={st.statLabel}>Rankings</Text>
                </View>
              </View>
            )}

            <Text style={st.sectionLabel}>LEADERBOARDS</Text>

            {boards.map((b) => (
              <TouchableOpacity
                key={b.id}
                testID={`lb-board-${b.id}`}
                style={[st.boardCard, { borderLeftColor: b.color }]}
                onPress={() => loadBoard(b.id)}
              >
                <View style={[st.boardIcon, { backgroundColor: b.color + '20' }]}>
                  <Ionicons name={b.icon as any} size={22} color={b.color} />
                </View>
                <View style={st.boardInfo}>
                  <Text style={st.boardName}>{b.name}</Text>
                  <Text style={st.boardDesc}>{b.description}</Text>
                </View>
                <View style={st.boardMeta}>
                  <Text style={[st.boardCount, { color: b.color }]}>{b.total_entries?.toLocaleString()}</Text>
                  <Ionicons name="chevron-forward" size={16} color="#475569" />
                </View>
              </TouchableOpacity>
            ))}
            <View style={{ height: 40 }} />
          </ScrollView>
        ) : phase === 'board' ? (
          <View style={{ flex: 1 }}>
            {/* Time Range Selector */}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={st.timeRow} contentContainerStyle={{ paddingHorizontal: 16, gap: 8 }}>
              {TIME_RANGES.map((tr) => (
                <TouchableOpacity
                  key={tr.id}
                  style={[st.timeBtn, timeRange === tr.id && { backgroundColor: (boardInfo?.color || '#F59E0B') + '20', borderColor: boardInfo?.color || '#F59E0B' }]}
                  onPress={() => loadBoard(selectedBoard!, tr.id)}
                >
                  <Text style={[st.timeText, timeRange === tr.id && { color: boardInfo?.color || '#F59E0B' }]}>{tr.label}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>

            {/* Top 3 Podium */}
            {entries.length >= 3 && (
              <View style={st.podium}>
                {[entries[1], entries[0], entries[2]].map((e, i) => {
                  const rank = i === 1 ? 1 : i === 0 ? 2 : 3;
                  const rs = getRankStyle(rank);
                  const heights = [100, 130, 80];
                  return (
                    <View key={e.user_id} style={[st.podiumSlot, { height: heights[i] }]}>  
                      <View style={[st.podiumAvatar, { backgroundColor: e.avatar_color || rs.text, borderColor: rs.text, borderWidth: rank === 1 ? 3 : 1 }]}>
                        <Text style={st.podiumInitial}>{(e.username || '?')[0]}</Text>
                      </View>
                      <Text style={[st.podiumName, { color: rs.text }]} numberOfLines={1}>{e.username}</Text>
                      <Text style={st.podiumScore}>{getMetricLabel(boardInfo, e)}</Text>
                      <View style={[st.podiumBar, { backgroundColor: rs.text + '30', height: heights[i] - 60 }]}>
                        <Text style={[st.podiumRank, { color: rs.text }]}>#{rank}</Text>
                      </View>
                    </View>
                  );
                })}
              </View>
            )}

            {/* Full List */}
            <FlatList
              data={entries.slice(3)}
              keyExtractor={(item) => item.user_id}
              style={st.entryList}
              renderItem={({ item: e }) => {
                const rs = getRankStyle(e.rank);
                const isYou = e.user_id === 'default_user';
                return (
                  <View style={[st.entryRow, isYou && st.youRow, { borderLeftColor: isYou ? '#F59E0B' : 'transparent' }]}>
                    <Text style={[st.entryRank, { color: rs.text }]}>#{e.rank}</Text>
                    <View style={[st.entryAvatar, { backgroundColor: e.avatar_color || '#475569' }]}>
                      <Text style={st.entryInitial}>{(e.username || '?')[0]}</Text>
                    </View>
                    <View style={st.entryInfo}>
                      <Text style={[st.entryName, isYou && { color: '#F59E0B' }]}>{isYou ? 'You' : e.username}</Text>
                      <Text style={st.entrySub}>{getSubMetric(boardInfo, e)}</Text>
                    </View>
                    <View style={st.entryRight}>
                      <Text style={[st.entryScore, { color: boardInfo?.color || '#F59E0B' }]}>{getMetricLabel(boardInfo, e)}</Text>
                      <Text style={[st.entryTier, { color: e.tier?.color || '#64748B' }]}>{e.tier?.name || ''}</Text>
                    </View>
                  </View>
                );
              }}
              ListEmptyComponent={<Text style={st.emptyText}>No entries for this time range</Text>}
            />
          </View>
        ) : phase === 'profile' ? (
          <ScrollView style={st.scroll} showsVerticalScrollIndicator={false}>
            <View style={st.profileHeader}>
              <View style={[st.profileAvatar, { backgroundColor: '#F59E0B' }]}>
                <Text style={st.profileInitial}>Y</Text>
              </View>
              <Text style={st.profileName}>Your Rankings</Text>
              <Text style={st.profileSub}>Ranked in {userRankings.length} boards</Text>
            </View>

            {userRankings.map((r) => (
              <TouchableOpacity key={r.board.id} style={[st.rankCard, { borderLeftColor: r.board.color }]} onPress={() => loadBoard(r.board.id)}>
                <View style={[st.rankIcon, { backgroundColor: r.board.color + '20' }]}>
                  <Ionicons name={r.board.icon as any} size={18} color={r.board.color} />
                </View>
                <View style={st.rankInfo}>
                  <Text style={st.rankName}>{r.board.name}</Text>
                  <Text style={st.rankMetric}>{getMetricLabel(r.board, r.entry)}</Text>
                </View>
                <View style={st.rankRight}>
                  <Text style={[st.rankPos, { color: r.board.color }]}>#{r.entry.rank}</Text>
                  <Text style={[st.rankTier, { color: r.entry.tier?.color || '#64748B' }]}>{r.entry.tier?.name}</Text>
                </View>
              </TouchableOpacity>
            ))}
            {userRankings.length === 0 && <Text style={st.emptyText}>Complete activities to appear on leaderboards!</Text>}
            <View style={{ height: 40 }} />
          </ScrollView>
        ) : null}
      </View>
    </Modal>
  );
};

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F172A' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, backgroundColor: '#1E293B', borderBottomWidth: 1, borderBottomColor: '#334155' },
  hBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  hTitle: { flex: 1, fontSize: 18, fontWeight: '700', color: '#F8FAFC', textAlign: 'center' },
  loadingView: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  scroll: { flex: 1, paddingHorizontal: 16 },
  // Stats Banner
  statsBanner: { flexDirection: 'row', backgroundColor: '#1E293B', borderRadius: 16, padding: 20, marginTop: 16, alignItems: 'center' },
  statItem: { flex: 1, alignItems: 'center' },
  statNum: { fontSize: 24, fontWeight: '800', color: '#F8FAFC' },
  statLabel: { fontSize: 11, color: '#64748B', marginTop: 2, textTransform: 'uppercase', letterSpacing: 1 },
  statDivider: { width: 1, height: 30, backgroundColor: '#334155' },
  // Section
  sectionLabel: { fontSize: 11, fontWeight: '800', color: '#64748B', letterSpacing: 1.5, marginTop: 20, marginBottom: 10 },
  // Board Cards
  boardCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1E293B', borderRadius: 14, padding: 14, marginBottom: 10, borderLeftWidth: 3, gap: 12 },
  boardIcon: { width: 44, height: 44, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
  boardInfo: { flex: 1 },
  boardName: { fontSize: 15, fontWeight: '700', color: '#F8FAFC' },
  boardDesc: { fontSize: 11, color: '#94A3B8', marginTop: 2 },
  boardMeta: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  boardCount: { fontSize: 13, fontWeight: '700' },
  // Time Range
  timeRow: { maxHeight: 48, marginTop: 8 },
  timeBtn: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20, borderWidth: 1.5, borderColor: '#334155', backgroundColor: '#1E293B' },
  timeText: { fontSize: 12, fontWeight: '700', color: '#94A3B8' },
  // Podium
  podium: { flexDirection: 'row', justifyContent: 'center', alignItems: 'flex-end', gap: 8, paddingHorizontal: 16, paddingTop: 16, paddingBottom: 8 },
  podiumSlot: { alignItems: 'center', width: 100 },
  podiumAvatar: { width: 40, height: 40, borderRadius: 20, justifyContent: 'center', alignItems: 'center' },
  podiumInitial: { fontSize: 16, fontWeight: '800', color: '#FFF' },
  podiumName: { fontSize: 11, fontWeight: '700', color: '#F8FAFC', marginTop: 4 },
  podiumScore: { fontSize: 10, color: '#94A3B8', marginTop: 1 },
  podiumBar: { width: '100%', borderRadius: 8, justifyContent: 'center', alignItems: 'center', marginTop: 4, backgroundColor: '#1E293B' },
  podiumRank: { fontSize: 16, fontWeight: '800' },
  // Entry List
  entryList: { flex: 1, paddingHorizontal: 16 },
  entryRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1E293B', borderRadius: 12, padding: 12, marginBottom: 6, gap: 10, borderLeftWidth: 3 },
  youRow: { backgroundColor: '#F59E0B10' },
  entryRank: { width: 36, fontSize: 14, fontWeight: '800', textAlign: 'center' },
  entryAvatar: { width: 36, height: 36, borderRadius: 18, justifyContent: 'center', alignItems: 'center' },
  entryInitial: { fontSize: 14, fontWeight: '800', color: '#FFF' },
  entryInfo: { flex: 1 },
  entryName: { fontSize: 14, fontWeight: '600', color: '#F8FAFC' },
  entrySub: { fontSize: 10, color: '#64748B', marginTop: 1 },
  entryRight: { alignItems: 'flex-end' },
  entryScore: { fontSize: 14, fontWeight: '800' },
  entryTier: { fontSize: 9, fontWeight: '700', marginTop: 1 },
  emptyText: { textAlign: 'center', color: '#64748B', fontSize: 14, paddingVertical: 30 },
  // Profile
  profileHeader: { alignItems: 'center', paddingVertical: 24 },
  profileAvatar: { width: 64, height: 64, borderRadius: 32, justifyContent: 'center', alignItems: 'center' },
  profileInitial: { fontSize: 28, fontWeight: '800', color: '#FFF' },
  profileName: { fontSize: 22, fontWeight: '800', color: '#F8FAFC', marginTop: 10 },
  profileSub: { fontSize: 13, color: '#94A3B8', marginTop: 2 },
  // Rank Cards
  rankCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1E293B', borderRadius: 14, padding: 14, marginBottom: 8, borderLeftWidth: 3, gap: 12 },
  rankIcon: { width: 38, height: 38, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  rankInfo: { flex: 1 },
  rankName: { fontSize: 14, fontWeight: '700', color: '#F8FAFC' },
  rankMetric: { fontSize: 11, color: '#94A3B8', marginTop: 1 },
  rankRight: { alignItems: 'flex-end' },
  rankPos: { fontSize: 18, fontWeight: '800' },
  rankTier: { fontSize: 9, fontWeight: '700', marginTop: 1 },
});
