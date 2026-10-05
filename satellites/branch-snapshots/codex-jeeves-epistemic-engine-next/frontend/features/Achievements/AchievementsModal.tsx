/**
 * Achievements Modal — ULTRASCALE Edition
 * Displays 10,000 achievements with category filters, rarity tiers, search, pagination
 * Wired to /api/academy/achievements with full stats dashboard
 */
import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  Modal, ActivityIndicator, TextInput, FlatList,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const RARITY_COLORS: Record<string, string> = {
  common: '#94A3B8',
  uncommon: '#8B5CF6',
  rare: '#F59E0B',
  epic: '#EC4899',
  legendary: '#EF4444',
};
const RARITY_ORDER = ['legendary','epic','rare','uncommon','common'];

const ICON_MAP: Record<string, keyof typeof Ionicons.glyphMap> = {
  bulb:'bulb-outline', ribbon:'ribbon-outline', flame:'flame-outline', calendar:'calendar-outline',
  fitness:'fitness-outline', book:'book-outline', 'document-text':'document-text-outline',
  speedometer:'speedometer-outline', layers:'layers-outline', 'shield-checkmark':'shield-checkmark-outline',
  analytics:'analytics-outline', repeat:'repeat-outline', time:'time-outline', timer:'timer-outline',
  flash:'flash-outline', school:'school-outline', map:'map-outline', trophy:'trophy-outline',
  bug:'bug-outline', build:'build-outline', 'code-slash':'code-slash-outline', construct:'construct-outline',
  hammer:'hammer-outline', bookmark:'bookmark-outline', create:'create-outline', 'share-social':'share-social-outline',
  globe:'globe-outline', library:'library-outline', 'code-working':'code-working-outline', star:'star-outline',
  headset:'headset-outline', 'musical-notes':'musical-notes-outline', stopwatch:'stopwatch-outline',
  alarm:'alarm-outline', medal:'medal-outline', 'eye-off':'eye-off-outline', diamond:'diamond-outline',
  rocket:'rocket-outline', hourglass:'hourglass-outline', albums:'albums-outline', 'git-merge':'git-merge-outline',
  'git-network':'git-network-outline', 'git-compare':'git-compare-outline', 'checkmark-circle':'checkmark-circle-outline',
  'checkmark-done':'checkmark-done-outline', documents:'documents-outline', 'star-half':'star-half-outline',
  sunny:'sunny-outline', rainy:'rainy-outline', leaf:'leaf-outline', snow:'snow-outline',
};

interface Props { visible: boolean; onClose: () => void; colors: any; }
interface AchItem { id:string; name:string; description:string; category:string; rarity:string; icon?:string; points?:number; threshold?:number; type?:string; domain?:string; }
interface Stats { total:number; by_category:Record<string,number>; by_rarity:Record<string,number>; }

export const AchievementsModal: React.FC<Props> = ({ visible, onClose, colors }) => {
  const [achievements, setAchievements] = useState<AchItem[]>([]);
  const [stats, setStats] = useState<Stats|null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string|null>(null);
  const [selectedRarity, setSelectedRarity] = useState<string|null>(null);
  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [view, setView] = useState<'browse'|'stats'>('browse');
  const LIMIT = 50;

  useEffect(() => {
    if (visible) {
      loadStats();
      loadAchievements(true);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  useEffect(() => {
    if (visible) loadAchievements(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCategory, selectedRarity]);

  const loadStats = async () => {
    try {
      const res = await apiFetch(`${API}/api/academy/achievements/stats`);
      if (res.ok) setStats(await res.json());
    } catch {}
  };

  const loadAchievements = async (fresh = false) => {
    if (fresh) { setLoading(true); setSkip(0); }
    else setLoadingMore(true);
    const newSkip = fresh ? 0 : skip;
    try {
      let url = `${API}/api/academy/achievements?limit=${LIMIT}&skip=${newSkip}`;
      if (selectedCategory) url += `&category=${selectedCategory}`;
      if (selectedRarity) url += `&rarity=${selectedRarity}`;
      const res = await apiFetch(url);
      if (res.ok) {
        const data = await res.json();
        const items = data.achievements || [];
        if (fresh) setAchievements(items);
        else setAchievements(prev => [...prev, ...items]);
        setSkip(newSkip + items.length);
        setHasMore(items.length === LIMIT);
      }
    } catch {}
    setLoading(false);
    setLoadingMore(false);
  };

  const filtered = search
    ? achievements.filter(a => a.name.toLowerCase().includes(search.toLowerCase()) || a.description.toLowerCase().includes(search.toLowerCase()))
    : achievements;

  const getIcon = (icon?: string): keyof typeof Ionicons.glyphMap => {
    if (!icon) return 'ribbon-outline';
    return ICON_MAP[icon] || 'ribbon-outline';
  };

  const topCategories = stats ? Object.entries(stats.by_category).sort((a,b) => b[1]-a[1]).slice(0,12) : [];

  const renderAchievement = ({ item: ach }: { item: AchItem }) => {
    const rarColor = RARITY_COLORS[ach.rarity] || '#94A3B8';
    return (
      <View testID={`ach-${ach.id}`} style={[st.achCard, { borderLeftColor: rarColor, borderLeftWidth: 3 }]}>
        <View style={[st.achIcon, { backgroundColor: rarColor + '18' }]}>
          <Ionicons name={getIcon(ach.icon)} size={22} color={rarColor} />
        </View>
        <View style={st.achInfo}>
          <Text style={st.achName} numberOfLines={1}>{ach.name}</Text>
          <Text style={st.achDesc} numberOfLines={2}>{ach.description}</Text>
          <View style={st.achMeta}>
            <View style={[st.rarBadge, { backgroundColor: rarColor + '20' }]}>
              <Text style={[st.rarText, { color: rarColor }]}>{ach.rarity?.toUpperCase()}</Text>
            </View>
            {ach.points ? <Text style={st.achPts}>{ach.points} pts</Text> : null}
            {ach.category ? <Text style={st.achCat}>{ach.category.replace(/_/g,' ')}</Text> : null}
          </View>
        </View>
      </View>
    );
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={st.container}>
        {/* Header */}
        <View style={st.header}>
          <TouchableOpacity testID="ach-close" onPress={onClose} style={st.hdrBtn}>
            <Ionicons name="close" size={24} color="#F8FAFC" />
          </TouchableOpacity>
          <View style={st.hdrCenter}>
            <Text style={st.hdrTitle}>Achievements</Text>
            <Text style={st.hdrSub}>{stats?.total?.toLocaleString() || '...'} Total</Text>
          </View>
          <TouchableOpacity testID="ach-toggle-view" onPress={() => setView(v => v === 'browse' ? 'stats' : 'browse')} style={st.hdrBtn}>
            <Ionicons name={view === 'browse' ? 'stats-chart' : 'list'} size={22} color="#F59E0B" />
          </TouchableOpacity>
        </View>

        {view === 'stats' && stats ? (
          <ScrollView style={st.statsView} showsVerticalScrollIndicator={false}>
            <Text style={st.statsTitle}>ACHIEVEMENT STATISTICS</Text>
            <View style={st.statsBig}>
              <Text style={st.statsBigNum}>{stats.total.toLocaleString()}</Text>
              <Text style={st.statsBigLabel}>Total Achievements</Text>
            </View>

            <Text style={st.sectionLabel}>BY RARITY</Text>
            {RARITY_ORDER.map(r => {
              const count = stats.by_rarity[r] || 0;
              const pct = Math.round(count / stats.total * 100);
              return (
                <TouchableOpacity key={r} style={st.rarRow} onPress={() => { setSelectedRarity(r === selectedRarity ? null : r); setView('browse'); }}>
                  <View style={[st.rarDot, { backgroundColor: RARITY_COLORS[r] }]} />
                  <Text style={st.rarLabel}>{r.toUpperCase()}</Text>
                  <View style={st.rarBarBg}>
                    <View style={[st.rarBarFill, { width: `${pct}%`, backgroundColor: RARITY_COLORS[r] }]} />
                  </View>
                  <Text style={st.rarCount}>{count.toLocaleString()}</Text>
                </TouchableOpacity>
              );
            })}

            <Text style={st.sectionLabel}>TOP CATEGORIES</Text>
            {topCategories.map(([cat, count]) => (
              <TouchableOpacity key={cat} style={st.catRow} onPress={() => { setSelectedCategory(cat === selectedCategory ? null : cat); setView('browse'); }}>
                <Text style={st.catName} numberOfLines={1}>{cat.replace(/_/g,' ')}</Text>
                <Text style={st.catCount}>{count}</Text>
              </TouchableOpacity>
            ))}
            <View style={{ height: 40 }} />
          </ScrollView>
        ) : (
          <>
            {/* Search & Filters */}
            <View style={st.searchRow}>
              <Ionicons name="search" size={18} color="#64748B" />
              <TextInput
                testID="ach-search"
                style={st.searchInput}
                placeholder="Search achievements..."
                placeholderTextColor="#64748B"
                value={search}
                onChangeText={setSearch}
              />
              {search ? (
                <TouchableOpacity onPress={() => setSearch('')}>
                  <Ionicons name="close-circle" size={18} color="#64748B" />
                </TouchableOpacity>
              ) : null}
            </View>

            {/* Rarity Filter */}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={st.filterRow}>
              <TouchableOpacity
                testID="ach-filter-all"
                style={[st.filterChip, !selectedRarity && st.filterActive]}
                onPress={() => setSelectedRarity(null)}
              >
                <Text style={[st.filterText, !selectedRarity && st.filterTextActive]}>All</Text>
              </TouchableOpacity>
              {RARITY_ORDER.map(r => (
                <TouchableOpacity
                  key={r}
                  testID={`ach-filter-${r}`}
                  style={[st.filterChip, selectedRarity === r && { backgroundColor: RARITY_COLORS[r] + '25', borderColor: RARITY_COLORS[r] }]}
                  onPress={() => setSelectedRarity(selectedRarity === r ? null : r)}
                >
                  <View style={[st.filterDot, { backgroundColor: RARITY_COLORS[r] }]} />
                  <Text style={[st.filterText, selectedRarity === r && { color: RARITY_COLORS[r] }]}>{r}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>

            {/* Category filter chips */}
            {selectedCategory && (
              <View style={st.activeCatRow}>
                <Ionicons name="funnel" size={14} color="#F59E0B" />
                <Text style={st.activeCatText}>{selectedCategory.replace(/_/g,' ')}</Text>
                <TouchableOpacity onPress={() => setSelectedCategory(null)}>
                  <Ionicons name="close-circle" size={16} color="#EF4444" />
                </TouchableOpacity>
              </View>
            )}

            {loading ? (
              <View style={st.loadWrap}>
                <ActivityIndicator size="large" color="#8B5CF6" />
                <Text style={st.loadText}>Loading achievements...</Text>
              </View>
            ) : (
              <FlatList
                testID="ach-list"
                data={filtered}
                renderItem={renderAchievement}
                keyExtractor={item => item.id}
                contentContainerStyle={st.listContent}
                onEndReached={() => { if (hasMore && !loadingMore && !search) loadAchievements(false); }}
                onEndReachedThreshold={0.3}
                ListFooterComponent={
                  loadingMore ? <ActivityIndicator color="#8B5CF6" style={{ padding: 16 }} /> :
                  !hasMore ? <Text style={st.endText}>All achievements loaded</Text> : null
                }
                ListEmptyComponent={<Text style={st.emptyText}>No achievements found</Text>}
                initialNumToRender={20}
                maxToRenderPerBatch={20}
                windowSize={10}
              />
            )}
          </>
        )}
      </View>
    </Modal>
  );
};

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F172A' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, backgroundColor: '#1E293B', borderBottomWidth: 1, borderBottomColor: '#334155' },
  hdrBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  hdrCenter: { flex: 1, alignItems: 'center' },
  hdrTitle: { fontSize: 18, fontWeight: '700', color: '#F8FAFC' },
  hdrSub: { fontSize: 12, color: '#94A3B8', marginTop: 2 },
  searchRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1E293B', marginHorizontal: 12, marginTop: 10, borderRadius: 10, paddingHorizontal: 12, gap: 8 },
  searchInput: { flex: 1, color: '#F8FAFC', fontSize: 14, paddingVertical: 10 },
  filterRow: { paddingHorizontal: 12, paddingVertical: 8, maxHeight: 48 },
  filterChip: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, borderWidth: 1, borderColor: '#334155', marginRight: 8, gap: 5 },
  filterActive: { backgroundColor: '#8B5CF625', borderColor: '#8B5CF6' },
  filterText: { fontSize: 12, fontWeight: '600', color: '#94A3B8', textTransform: 'capitalize' },
  filterTextActive: { color: '#8B5CF6' },
  filterDot: { width: 8, height: 8, borderRadius: 4 },
  activeCatRow: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 6 },
  activeCatText: { fontSize: 12, color: '#F59E0B', fontWeight: '600', textTransform: 'capitalize' },
  listContent: { paddingHorizontal: 12, paddingTop: 4, paddingBottom: 40 },
  achCard: { flexDirection: 'row', backgroundColor: '#1E293B', borderRadius: 12, padding: 12, marginBottom: 8 },
  achIcon: { width: 44, height: 44, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
  achInfo: { flex: 1, marginLeft: 10 },
  achName: { fontSize: 14, fontWeight: '700', color: '#F8FAFC' },
  achDesc: { fontSize: 12, color: '#94A3B8', marginTop: 2, lineHeight: 16 },
  achMeta: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 6 },
  rarBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 },
  rarText: { fontSize: 9, fontWeight: '800', letterSpacing: 0.5 },
  achPts: { fontSize: 11, fontWeight: '700', color: '#F59E0B' },
  achCat: { fontSize: 10, color: '#64748B', textTransform: 'capitalize' },
  loadWrap: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 12 },
  loadText: { color: '#94A3B8', fontSize: 14 },
  endText: { textAlign: 'center', color: '#64748B', fontSize: 12, padding: 16 },
  emptyText: { textAlign: 'center', color: '#64748B', fontSize: 14, padding: 40 },
  // Stats view
  statsView: { flex: 1, paddingHorizontal: 16 },
  statsTitle: { fontSize: 11, fontWeight: '800', color: '#64748B', letterSpacing: 1.5, marginTop: 16, marginBottom: 12 },
  statsBig: { alignItems: 'center', paddingVertical: 20, backgroundColor: '#1E293B', borderRadius: 16, marginBottom: 16 },
  statsBigNum: { fontSize: 42, fontWeight: '800', color: '#F59E0B' },
  statsBigLabel: { fontSize: 14, color: '#94A3B8', marginTop: 4 },
  sectionLabel: { fontSize: 11, fontWeight: '800', color: '#64748B', letterSpacing: 1.5, marginTop: 16, marginBottom: 10 },
  rarRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 },
  rarDot: { width: 12, height: 12, borderRadius: 6 },
  rarLabel: { fontSize: 11, fontWeight: '800', color: '#F8FAFC', width: 80, letterSpacing: 0.5 },
  rarBarBg: { flex: 1, height: 8, backgroundColor: '#1E293B', borderRadius: 4, overflow: 'hidden' },
  rarBarFill: { height: '100%', borderRadius: 4 },
  rarCount: { fontSize: 12, fontWeight: '700', color: '#94A3B8', width: 50, textAlign: 'right' },
  catRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10, paddingHorizontal: 12, backgroundColor: '#1E293B', borderRadius: 10, marginBottom: 6 },
  catName: { fontSize: 13, fontWeight: '600', color: '#F8FAFC', flex: 1, textTransform: 'capitalize' },
  catCount: { fontSize: 13, fontWeight: '700', color: '#F59E0B' },
});
