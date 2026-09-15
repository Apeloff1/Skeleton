/**
 * Language Academy — 451+ programming language classes browser
 */
import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Modal, TextInput, FlatList, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const CAT_COLORS: Record<string, string> = {
  mainstream: '#3B82F6', emerging: '#10B981', niche: '#F59E0B',
  esoteric: '#EC4899', historic: '#8B5CF6', data_markup: '#2563EB',
};

interface Props { visible: boolean; onClose: () => void; }

export const LanguageAcademyModal: React.FC<Props> = ({ visible, onClose }) => {
  const [languages, setLanguages] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedCat, setSelectedCat] = useState<string|null>(null);
  const [selectedLang, setSelectedLang] = useState<any>(null);
  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const LIMIT = 50;

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (visible) { loadStats(); loadLanguages(true); } }, [visible]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (visible) loadLanguages(true); }, [selectedCat]);

  const loadStats = async () => {
    try { const r = await apiFetch(`${API}/api/languages-academy/stats`); if (r.ok) setStats(await r.json()); } catch {}
  };

  const loadLanguages = async (fresh = false) => {
    if (fresh) setLoading(true);
    const s = fresh ? 0 : skip;
    try {
      let url = `${API}/api/languages-academy/all?limit=${LIMIT}&skip=${s}`;
      if (selectedCat) url += `&category=${selectedCat}`;
      const r = await apiFetch(url);
      if (r.ok) {
        const d = await r.json();
        if (fresh) setLanguages(d.languages); else setLanguages(p => [...p, ...d.languages]);
        setSkip(s + d.languages.length);
        setHasMore(d.languages.length === LIMIT);
      }
    } catch {}
    setLoading(false);
  };

  const searchLangs = async (q: string) => {
    if (!q.trim()) { loadLanguages(true); return; }
    setLoading(true);
    try {
      const r = await apiFetch(`${API}/api/languages-academy/search?q=${encodeURIComponent(q)}&limit=50`);
      if (r.ok) { const d = await r.json(); setLanguages(d.results); setHasMore(false); }
    } catch {}
    setLoading(false);
  };

  const loadDetail = async (id: string) => {
    try {
      const r = await apiFetch(`${API}/api/languages-academy/${id}`);
      if (r.ok) { const d = await r.json(); setSelectedLang(d.language); }
    } catch {}
  };

  const filtered = search ? languages.filter(l => l.name.toLowerCase().includes(search.toLowerCase())) : languages;

  const renderLang = ({ item }: { item: any }) => {
    const catColor = CAT_COLORS[item.category] || '#94A3B8';
    return (
      <TouchableOpacity style={[st.langCard, { borderLeftColor: catColor, borderLeftWidth: 3 }]} onPress={() => loadDetail(item.id)}>
        <View style={st.langTop}>
          <Text style={st.langName}>{item.name}</Text>
          {item.executable_in_playground && <Ionicons name="play-circle" size={16} color="#22C55E" />}
        </View>
        <Text style={st.langDesc} numberOfLines={2}>{item.description}</Text>
        <View style={st.langMeta}>
          <View style={[st.catBadge, { backgroundColor: catColor + '20' }]}>
            <Text style={[st.catText, { color: catColor }]}>{item.category}</Text>
          </View>
          <Text style={st.langYear}>{item.year_created}</Text>
          <Text style={st.langDiff}>{item.difficulty}</Text>
          <Text style={st.langHours}>{item.estimated_hours}h</Text>
        </View>
      </TouchableOpacity>
    );
  };

  if (selectedLang) {
    return (
      <Modal visible={visible} animationType="slide" onRequestClose={() => setSelectedLang(null)}>
        <View style={st.container}>
          <View style={st.header}>
            <TouchableOpacity onPress={() => setSelectedLang(null)} style={st.hBtn}>
              <Ionicons name="arrow-back" size={24} color="#F8FAFC" />
            </TouchableOpacity>
            <Text style={st.hTitle} numberOfLines={1}>{selectedLang.name}</Text>
            <View style={st.hBtn} />
          </View>
          <FlatList
            data={selectedLang.chapters || []}
            keyExtractor={(_, i) => String(i)}
            contentContainerStyle={st.detailContent}
            ListHeaderComponent={() => (
              <View>
                <Text style={st.detailDesc}>{selectedLang.description}</Text>
                <View style={st.detailMeta}>
                  <Text style={st.metaText}>Created: {selectedLang.year_created}</Text>
                  <Text style={st.metaText}>By: {selectedLang.creator}</Text>
                  <Text style={st.metaText}>Paradigm: {selectedLang.paradigm}</Text>
                  <Text style={st.metaText}>Typing: {selectedLang.typing}</Text>
                  <Text style={st.metaText}>Difficulty: {selectedLang.difficulty}</Text>
                  <Text style={st.metaText}>Hours: {selectedLang.estimated_hours}h</Text>
                  {selectedLang.executable_in_playground && (
                    <View style={st.execBadge}><Ionicons name="play-circle" size={14} color="#22C55E" /><Text style={st.execText}>Executable in Playground</Text></View>
                  )}
                </View>
                <Text style={st.chapTitle}>CURRICULUM ({(selectedLang.chapters || []).length} chapters)</Text>
              </View>
            )}
            renderItem={({ item, index }) => (
              <View style={st.chapCard}>
                <Text style={st.chapNum}>Chapter {index + 1}</Text>
                <Text style={st.chapName}>{item.title}</Text>
                {(item.lessons || []).map((l: string, i: number) => (
                  <View key={i} style={st.lessonRow}>
                    <Ionicons name="checkmark-circle-outline" size={14} color="#64748B" />
                    <Text style={st.lessonText}>{l}</Text>
                  </View>
                ))}
              </View>
            )}
          />
        </View>
      </Modal>
    );
  }

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={st.container}>
        <View style={st.header}>
          <TouchableOpacity testID="la-close" onPress={onClose} style={st.hBtn}>
            <Ionicons name="close" size={24} color="#F8FAFC" />
          </TouchableOpacity>
          <View style={{ flex: 1, alignItems: 'center' }}>
            <Text style={st.hTitle}>Language Academy</Text>
            <Text style={st.hSub}>{stats?.total || '...'} Languages</Text>
          </View>
          <View style={st.hBtn} />
        </View>

        <View style={st.searchRow}>
          <Ionicons name="search" size={18} color="#64748B" />
          <TextInput style={st.searchInput} placeholder="Search languages..." placeholderTextColor="#64748B" value={search}
            onChangeText={t => { setSearch(t); if (t.length > 1) searchLangs(t); else if (!t) loadLanguages(true); }} />
        </View>

        <FlatList
          horizontal
          data={[null, ...Object.keys(CAT_COLORS)]}
          keyExtractor={(item) => item || 'all'}
          showsHorizontalScrollIndicator={false}
          style={st.filterBar}
          renderItem={({ item }) => (
            <TouchableOpacity
              style={[st.filterChip, (item === selectedCat || (!item && !selectedCat)) && st.filterActive]}
              onPress={() => setSelectedCat(item)}
            >
              {item && <View style={[st.filterDot, { backgroundColor: CAT_COLORS[item] }]} />}
              <Text style={[st.filterText, (item === selectedCat || (!item && !selectedCat)) && st.filterTextActive]}>
                {item ? item.replace(/_/g,' ') : 'All'}
              </Text>
            </TouchableOpacity>
          )}
        />

        {loading ? (
          <View style={st.loadWrap}><ActivityIndicator size="large" color="#3B82F6" /></View>
        ) : (
          <FlatList
            testID="la-list"
            data={filtered}
            renderItem={renderLang}
            keyExtractor={item => item.id}
            contentContainerStyle={st.listContent}
            onEndReached={() => { if (hasMore && !search) loadLanguages(false); }}
            onEndReachedThreshold={0.3}
            ListEmptyComponent={<Text style={st.emptyText}>No languages found</Text>}
            initialNumToRender={20}
          />
        )}
      </View>
    </Modal>
  );
};

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F172A' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, backgroundColor: '#1E293B', borderBottomWidth: 1, borderBottomColor: '#334155' },
  hBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  hTitle: { fontSize: 18, fontWeight: '700', color: '#F8FAFC' },
  hSub: { fontSize: 12, color: '#94A3B8', marginTop: 2 },
  searchRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1E293B', marginHorizontal: 12, marginTop: 10, borderRadius: 10, paddingHorizontal: 12, gap: 8 },
  searchInput: { flex: 1, color: '#F8FAFC', fontSize: 14, paddingVertical: 10 },
  filterBar: { maxHeight: 48, paddingHorizontal: 12, paddingVertical: 6 },
  filterChip: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, borderWidth: 1, borderColor: '#334155', marginRight: 8, gap: 5 },
  filterActive: { backgroundColor: '#3B82F620', borderColor: '#3B82F6' },
  filterDot: { width: 8, height: 8, borderRadius: 4 },
  filterText: { fontSize: 12, fontWeight: '600', color: '#94A3B8', textTransform: 'capitalize' },
  filterTextActive: { color: '#3B82F6' },
  loadWrap: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  listContent: { paddingHorizontal: 12, paddingTop: 4, paddingBottom: 40 },
  langCard: { backgroundColor: '#1E293B', borderRadius: 12, padding: 14, marginBottom: 8 },
  langTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  langName: { fontSize: 16, fontWeight: '700', color: '#F8FAFC' },
  langDesc: { fontSize: 12, color: '#94A3B8', marginTop: 4, lineHeight: 16 },
  langMeta: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 },
  catBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 },
  catText: { fontSize: 10, fontWeight: '800', textTransform: 'uppercase' },
  langYear: { fontSize: 11, color: '#64748B' },
  langDiff: { fontSize: 11, color: '#64748B', textTransform: 'capitalize' },
  langHours: { fontSize: 11, color: '#F59E0B', fontWeight: '700' },
  emptyText: { textAlign: 'center', color: '#64748B', fontSize: 14, padding: 40 },
  // Detail view
  detailContent: { paddingHorizontal: 16, paddingBottom: 40 },
  detailDesc: { fontSize: 14, color: '#F8FAFC', lineHeight: 22, marginTop: 16 },
  detailMeta: { backgroundColor: '#1E293B', borderRadius: 12, padding: 14, marginTop: 12, gap: 4 },
  metaText: { fontSize: 12, color: '#94A3B8' },
  execBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4 },
  execText: { fontSize: 12, color: '#22C55E', fontWeight: '600' },
  chapTitle: { fontSize: 11, fontWeight: '800', color: '#64748B', letterSpacing: 1.5, marginTop: 20, marginBottom: 10 },
  chapCard: { backgroundColor: '#1E293B', borderRadius: 12, padding: 14, marginBottom: 8 },
  chapNum: { fontSize: 10, fontWeight: '800', color: '#F59E0B', letterSpacing: 1 },
  chapName: { fontSize: 15, fontWeight: '700', color: '#F8FAFC', marginTop: 4 },
  lessonRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 6 },
  lessonText: { fontSize: 12, color: '#94A3B8' },
});
