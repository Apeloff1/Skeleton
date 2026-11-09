import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Modal, ActivityIndicator,
  SafeAreaView, TextInput, ScrollView, FlatList, RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSettings } from '../../state/settingsStore';
import { ttsSpeak, ttsStop } from '../Academy/tts';
import { jeevesSpeak, isJeevesEnabled } from '../Academy/jeevesTts';
import { ReadingVisualizer } from '../ReadingLibrary/ReadingVisualizer';
import { API_BASE } from '../../utils/apiBase';

import { apiFetch } from '../../utils/apiController';
const API = API_BASE;

interface Props {
  visible: boolean;
  onClose: () => void;
  colors?: any;
  initialSearch?: string;
}

type TabKey = 'tracks' | 'books' | 'bibles' | 'classes' | 'library' | 'subjects' | 'quizzes' | 'knowledge' | 'projects' | 'assessments' | 'challenges' | 'vault';

interface TabDef {
  key: TabKey;
  label: string;
  icon: string;
  color: string;
  endpoint: (page: number, search: string) => string;
  listKey: string;         // property on response that holds the array
  countKey?: string;       // property that holds the count
  pagesKey?: string;       // property that holds total pages
}

const TABS: TabDef[] = [
  { key: 'tracks',      label: 'Tracks',      icon: 'git-branch',       color: '#3B82F6',
    endpoint: (p, s) => `/api/academy/tracks?page=${p}&limit=50${s ? `&category=${encodeURIComponent(s)}` : ''}`,
    listKey: 'tracks', countKey: 'total_count', pagesKey: 'pages' },
  { key: 'books',       label: 'Books',       icon: 'book',             color: '#F97316',
    endpoint: (p, s) => `/api/academy/reading-library?page=${p}&limit=50${s ? `&category=${encodeURIComponent(s)}` : ''}`,
    listKey: 'books', countKey: 'total', pagesKey: 'pages' },
  { key: 'bibles',      label: 'Bibles',      icon: 'library',          color: '#6366F1',
    endpoint: (p, s) => `/api/academy/bibles?page=${p}&limit=50${s ? `&category=${encodeURIComponent(s)}` : ''}`,
    listKey: 'bibles', countKey: 'total_count', pagesKey: 'pages' },
  { key: 'classes',     label: 'Classes',     icon: 'school',           color: '#10B981',
    endpoint: (p, s) => `/api/academy/subjects?page=${p}&limit=50${s ? `&category=${encodeURIComponent(s)}` : ''}`,
    listKey: 'subjects', countKey: 'total_count', pagesKey: 'pages' },
  { key: 'library',     label: 'My Library',  icon: 'bookmarks',        color: '#EC4899',
    endpoint: () => `/api/academy/class-progress/default_user?limit=100`,
    listKey: 'items', countKey: 'count', pagesKey: undefined },
  { key: 'subjects',    label: 'Subjects',    icon: 'library',          color: '#10B981',
    endpoint: (p, s) => `/api/academy/subjects?page=${p}&limit=50${s ? `&search=${encodeURIComponent(s)}` : ''}`,
    listKey: 'subjects', countKey: 'total_count', pagesKey: 'pages' },
  { key: 'quizzes',     label: 'Quizzes',     icon: 'help-circle',      color: '#F59E0B',
    endpoint: (p, s) => `/api/academy/quizzes?skip=${(p - 1) * 50}&page_size=50${s ? `&domain=${encodeURIComponent(s)}` : ''}`,
    listKey: 'quizzes', countKey: 'total' },
  { key: 'knowledge',   label: 'Knowledge',   icon: 'planet',           color: '#8B5CF6',
    endpoint: (_p, _s) => `/api/academy/knowledge-dbs`,
    listKey: 'domains', countKey: 'total' },
  { key: 'projects',    label: 'Projects',    icon: 'hammer',           color: '#EC4899',
    endpoint: (p, s) => `/api/academy/projects?page=${p}&limit=50${s ? `&difficulty=${encodeURIComponent(s)}` : ''}`,
    listKey: 'projects', countKey: 'total_count', pagesKey: 'pages' },
  { key: 'assessments', label: 'Assessments', icon: 'ribbon',           color: '#3B82F6',
    endpoint: (p, s) => `/api/academy/assessments?page=${p}&limit=50${s ? `&track_id=${encodeURIComponent(s)}` : ''}`,
    listKey: 'assessments', countKey: 'total_count', pagesKey: 'pages' },
  { key: 'challenges',  label: 'Challenges',  icon: 'trophy',           color: '#EF4444',
    endpoint: (p, s) => `/api/academy/challenges?page=${p}&limit=50${s ? `&difficulty=${encodeURIComponent(s)}` : ''}`,
    listKey: 'challenges', countKey: 'total_count', pagesKey: 'pages' },
  { key: 'vault',       label: 'Vault',       icon: 'lock-closed',      color: '#3B82F6',
    endpoint: (_p, s) => `/api/academy/vault?${s ? `category=${encodeURIComponent(s)}&` : ''}limit=100`,
    listKey: 'entries', countKey: 'total' },
];

export function MegaAcademyModal({ visible, onClose, initialSearch }: Props) {
  const [activeTab, setActiveTab] = useState<TabKey>('tracks');
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [search, setSearch] = useState(initialSearch || '');
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [selected, setSelected] = useState<any | null>(null);
  // Bookflix horizontal-scroll mode toggle (only shown for reading tabs)
  const [viewMode, setViewMode] = useState<'grid' | 'flix'>('grid');
  // Continue-Reading card data (last item the user was reading)
  const [continueItem, setContinueItem] = useState<any | null>(null);
  const [continueMeta, setContinueMeta] = useState<any | null>(null);

  // Load the user's last-open reading position once
  useEffect(() => {
    if (!visible) return;
    apiFetch(`${API}/api/academy/class-progress/default_user/continue`)
      .then((r) => r.json())
      .then((data) => {
        if (data?.continue) {
          setContinueItem(data.continue);
          setContinueMeta(data.meta || null);
        }
      })
      .catch(() => {});
  }, [visible]);
  // Reading Visualizer state — supports books / bibles / tracks
  const [reader, setReader] = useState<
    { type: 'book' | 'bible' | 'track'; id: string; title: string; totalChapters: number; chapterIdx: number } | null
  >(null);

  // Open the Reading Visualizer for the tapped card based on active tab
  const openReader = useCallback((item: any) => {
    if (activeTab === 'books') {
      const tot = (item.chapters || []).length || item.total_chapters || 10;
      setReader({ type: 'book', id: item.id, title: item.title, totalChapters: tot, chapterIdx: 0 });
    } else if (activeTab === 'bibles') {
      const tot = (item.sections || []).reduce(
        (n: number, s: any) => n + (s.articles?.length || 0),
        0,
      ) || item.total_articles || 8;
      setReader({ type: 'bible', id: item.id, title: item.name, totalChapters: Math.max(tot, 1), chapterIdx: 0 });
    } else if (activeTab === 'tracks') {
      const hours = Number(item.total_hours || 8);
      const tot = Math.min(Math.max(Math.floor(hours / 2), 6), 12);
      setReader({ type: 'track', id: item.id, title: item.name, totalChapters: tot, chapterIdx: 0 });
    } else if (activeTab === 'classes') {
      setReader({ type: 'subject' as any, id: item.id, title: item.title, totalChapters: 1, chapterIdx: 0 });
    } else {
      setSelected(item);
    }
  }, [activeTab]);

  const tab = useMemo(() => TABS.find(t => t.key === activeTab)!, [activeTab]);

  /** Fetch a page of the active tab's data. */
  const load = useCallback(async (p = 1, append = false, overrideSearch?: string) => {
    try {
      setLoading(true);
      const s = overrideSearch ?? search;
      const url = API + tab.endpoint(p, s);
      const res = await apiFetch(url);
      const data = await res.json();

      let list: any[] = [];
      if (tab.key === 'knowledge') {
        // knowledge-dbs returns { domains: { cs: [...], math: [...] } } — flatten
        const domains = data[tab.listKey] || {};
        list = Object.entries(domains).flatMap(([domain, arr]: [string, any]) =>
          (Array.isArray(arr) ? arr : []).map(x => ({ ...x, _domain: domain }))
        );
      } else if (tab.key === 'vault') {
        list = data[tab.listKey] || data.entries || [];
      } else {
        list = data[tab.listKey] || [];
      }

      setItems(prev => append ? [...prev, ...list] : list);

      const pages = tab.pagesKey ? data[tab.pagesKey] : undefined;
      if (pages !== undefined) {
        setHasMore(p < pages);
      } else if (tab.countKey) {
        setHasMore(p * 50 < (data[tab.countKey] || 0));
      } else {
        setHasMore(list.length >= 50);
      }
      setPage(p);
      if (tab.countKey && data[tab.countKey] !== undefined) {
        setCounts(prev => ({ ...prev, [tab.key]: data[tab.countKey as string] }));
      } else {
        setCounts(prev => ({ ...prev, [tab.key]: list.length }));
      }
    } catch (e) {
      console.error(`[${tab.key}] load failed`, e);
      if (!append) setItems([]);
      setHasMore(false);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [tab, search]);

  // On open or tab switch — reset & reload
  useEffect(() => {
    if (visible) {
      setItems([]);
      setPage(1);
      setHasMore(true);
      setSelected(null);
      load(1, false);
    }
  }, [visible, activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  // Prefetch counts for every tab on first open so the tab badges show totals
  useEffect(() => {
    if (!visible) return;
    TABS.forEach(async t => {
      if (counts[t.key] !== undefined) return;
      try {
        const url = API + t.endpoint(1, '');
        const res = await apiFetch(url);
        const data = await res.json();
        const n = t.countKey ? data[t.countKey] : (data[t.listKey]?.length || 0);
        setCounts(prev => ({ ...prev, [t.key]: n || 0 }));
      } catch {}
    });
  }, [visible]); // eslint-disable-line react-hooks/exhaustive-deps

  const onRefresh = () => {
    setRefreshing(true);
    setPage(1); setHasMore(true);
    load(1, false);
  };

  const onEndReached = () => {
    if (!loading && hasMore) load(page + 1, true);
  };

  const onSubmitSearch = () => {
    setPage(1); setHasMore(true);
    load(1, false);
  };

  // ─── Renderers ─────────────────────────────────────────────────────
  const renderItem = ({ item }: { item: any }) => {
    switch (activeTab) {
      case 'tracks':      return <Card title={item.name} subtitle={item.description} meta={[item.category, `${item.total_hours}h`, 'Read →']} icon={item.icon || 'git-branch'} color={item.color || tab.color} onPress={() => openReader(item)} />;
      case 'books':       return <Card title={item.title} subtitle={item.description || `By ${item.author}`} meta={[item.category, `${item.estimated_hours}h`, `${item.total_chapters} ch`]} icon="book" color={tab.color} onPress={() => openReader(item)} />;
      case 'bibles':      return <Card title={item.name} subtitle={item.description} meta={[item.category, `${item.total_hours}h`, `${item.total_articles || (item.sections || []).length} articles`]} icon={item.icon || 'library'} color={item.color || tab.color} onPress={() => openReader(item)} />;
      case 'classes':     return <Card title={item.title} subtitle={(item.content || '').slice(0,140) + '…'} meta={[item.category, `Class`, `${Math.max(3, Math.round((item.content||'').length/220))} min`]} icon="school" color={tab.color} onPress={() => openReader(item)} />;
      case 'library':     return <Card
                            title={item.item_id}
                            subtitle={`${item.item_type.toUpperCase()} • last ${new Date(item.updated_at || Date.now()).toLocaleDateString()}`}
                            meta={[`Ch ${(item.chapter_idx || 0) + 1}`, `${Math.round((item.scroll_ratio || 0) * 100)}%`, item.completed ? 'DONE' : 'IN PROGRESS']}
                            icon="bookmark"
                            color={tab.color}
                            onPress={() => {
                              if (item.item_type === 'book') setReader({ type: 'book', id: item.item_id, title: item.item_id, totalChapters: 12, chapterIdx: item.chapter_idx || 0 });
                              else if (item.item_type === 'bible') setReader({ type: 'bible', id: item.item_id, title: item.item_id, totalChapters: 8, chapterIdx: item.chapter_idx || 0 });
                              else if (item.item_type === 'track') setReader({ type: 'track', id: item.item_id, title: item.item_id, totalChapters: 12, chapterIdx: item.chapter_idx || 0 });
                              else if (item.item_type === 'subject') setReader({ type: 'subject' as any, id: item.item_id, title: item.item_id, totalChapters: 1, chapterIdx: 0 });
                            }}
                          />;
      case 'subjects':    return <Card title={item.title} subtitle={(item.content || '').replace(/\n/g, ' ').slice(0, 140)} meta={[item.track_id, `${item.estimated_minutes || 30}m`]} icon={tab.icon} color={tab.color} onPress={() => setSelected(item)} />;
      case 'quizzes':     return <Card title={item.question} subtitle={(item.options || []).slice(0, 4).map((o: string, i: number) => `${String.fromCharCode(65 + i)}. ${o}`).join('   ')} meta={[item.domain, item.topic, item.difficulty]} icon={tab.icon} color={tab.color} onPress={() => setSelected(item)} />;
      case 'knowledge':   return <Card title={item.name} subtitle={(item.topics || []).slice(0, 6).join(' • ')} meta={[item._domain, item.level, `${item.hours}h`]} icon={tab.icon} color={tab.color} onPress={() => setSelected(item)} />;
      case 'projects':    return <Card title={item.title} subtitle={item.description} meta={[item.difficulty, `${item.estimated_hours}h`]} icon={tab.icon} color={tab.color} onPress={() => setSelected(item)} />;
      case 'assessments': return <Card title={item.title || item.name || item.id} subtitle={item.description || `${item.questions?.length || 0} questions`} meta={[item.track_id, `${item.duration_minutes || 60}m`, `${(item.passing_score || 70)}%`]} icon={tab.icon} color={tab.color} onPress={() => setSelected(item)} />;
      case 'challenges':  return <Card title={item.title} subtitle={item.description} meta={[item.difficulty, item.category]} icon={tab.icon} color={tab.color} onPress={() => setSelected(item)} />;
      case 'vault':       return <Card title={item.title || item.name || item.id} subtitle={item.description || item.content?.slice(0, 120) || ''} meta={[item.category, item.domain].filter(Boolean)} icon={tab.icon} color={tab.color} onPress={() => setSelected(item)} />;
    }
  };

  const total = counts[activeTab];

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={s.container}>
        {/* Header */}
        <View style={s.header}>
          <TouchableOpacity testID="academy-close" onPress={onClose} style={s.headerBtn} hitSlop={{ top: 10, left: 10, right: 10, bottom: 10 }}>
            <Ionicons name="arrow-back" size={24} color="#F8FAFC" />
          </TouchableOpacity>
          <View style={s.headerTextContainer}>
            <Text style={s.headerTitle}>Global Mega-Academy</Text>
            <Text style={s.headerSub}>
              {TABS.reduce((sum, t) => sum + (counts[t.key] || 0), 0).toLocaleString()} total items across {TABS.length} categories
            </Text>
          </View>
          <View style={{ width: 44 }} />
        </View>

        {/* Tabs */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.tabsScroll} contentContainerStyle={s.tabsRow}>
          {TABS.map(t => {
            const active = t.key === activeTab;
            const badge = counts[t.key];
            return (
              <TouchableOpacity
                key={t.key}
                onPress={() => { setActiveTab(t.key); setSearch(''); }}
                style={[s.tab, active && { backgroundColor: t.color + '22', borderColor: t.color }]}
              >
                <Ionicons name={t.icon as any} size={16} color={active ? t.color : '#94A3B8'} style={{ marginRight: 6 }} />
                <Text style={[s.tabLabel, active && { color: t.color }]}>{t.label}</Text>
                {badge !== undefined && (
                  <View style={[s.tabBadge, active && { backgroundColor: t.color }]}>
                    <Text style={s.tabBadgeText}>{formatCount(badge)}</Text>
                  </View>
                )}
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        {/* Search */}
        <View style={s.searchBar}>
          <Ionicons name="search" size={18} color="#94A3B8" />
          <TextInput
            style={s.searchInput}
            placeholder={searchPlaceholder(activeTab)}
            placeholderTextColor="#64748B"
            value={search}
            onChangeText={setSearch}
            onSubmitEditing={onSubmitSearch}
            returnKeyType="search"
          />
          {search ? (
            <TouchableOpacity onPress={() => { setSearch(''); setPage(1); load(1, false, ''); }}>
              <Ionicons name="close-circle" size={18} color="#64748B" />
            </TouchableOpacity>
          ) : null}
        </View>

        {/* Continue Reading card — appears only when there's a saved position */}
        {continueItem && (
          <TouchableOpacity
            testID="continue-reading-card"
            style={s.continueCard}
            onPress={() => {
              const it = continueItem;
              const meta = continueMeta;
              if (it.item_type === 'book') {
                setReader({
                  type: 'book',
                  id: it.item_id,
                  title: meta?.title || 'Continue',
                  totalChapters: meta?.total_chapters || 10,
                  chapterIdx: it.chapter_idx || 0,
                });
              } else if (it.item_type === 'bible') {
                setReader({ type: 'bible', id: it.item_id, title: it.item_id, totalChapters: 8, chapterIdx: it.chapter_idx || 0 });
              } else if (it.item_type === 'track') {
                setReader({ type: 'track', id: it.item_id, title: it.item_id, totalChapters: 12, chapterIdx: it.chapter_idx || 0 });
              } else if (it.item_type === 'subject') {
                setReader({ type: 'subject' as any, id: it.item_id, title: it.item_id, totalChapters: 1, chapterIdx: 0 });
              }
            }}
          >
            <View style={s.continueIconWrap}>
              <Ionicons name="play-circle" size={28} color="#10B981" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.continueLabel}>Continue Reading</Text>
              <Text style={s.continueTitle} numberOfLines={1}>
                {continueMeta?.title || continueItem.item_id}
              </Text>
              <Text style={s.continueSub}>
                Chapter {(continueItem.chapter_idx || 0) + 1} • {Math.round((continueItem.scroll_ratio || 0) * 100)}% through
              </Text>
            </View>
            <Ionicons name="chevron-forward" size={22} color="#64748B" />
          </TouchableOpacity>
        )}

        {/* List */}
        {total !== undefined && (
          <View style={s.listMetaRow}>
            <Text style={s.countLabel}>
              Showing {items.length.toLocaleString()} of {total.toLocaleString()}
            </Text>
            {(activeTab === 'books' || activeTab === 'bibles' || activeTab === 'tracks') && (
              <TouchableOpacity
                testID="bookflix-toggle"
                onPress={() => setViewMode((m) => (m === 'grid' ? 'flix' : 'grid'))}
                style={s.flixToggle}
              >
                <Ionicons name={viewMode === 'grid' ? 'film-outline' : 'grid-outline'} size={14} color="#F8FAFC" />
                <Text style={s.flixToggleText}>{viewMode === 'grid' ? 'Bookflix' : 'Grid'}</Text>
              </TouchableOpacity>
            )}
          </View>
        )}

        {viewMode === 'flix' && (activeTab === 'books' || activeTab === 'bibles' || activeTab === 'tracks') ? (
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ paddingHorizontal: 16, paddingVertical: 14 }}
            testID="bookflix-scroller"
          >
            {[...items].sort((a: any, b: any) => {
              // Open-license books first
              const ao = a.is_open_license ? 0 : 1;
              const bo = b.is_open_license ? 0 : 1;
              return ao - bo;
            }).map((it: any, i: number) => (
              <TouchableOpacity
                key={String(it.id || `flix_${i}`)}
                style={s.flixCard}
                onPress={() => openReader(it)}
              >
                <View style={[s.flixCover, { backgroundColor: tab.color + '33', borderColor: tab.color }]}>
                  <Ionicons name={tab.icon as any} size={32} color={tab.color} />
                </View>
                <Text style={s.flixTitle} numberOfLines={2}>
                  {it.title || it.name}
                </Text>
                <Text style={s.flixSub} numberOfLines={1}>
                  {it.author || it.category || ''}
                </Text>
                {it.is_open_license && (
                  <View style={s.flixBadge}>
                    <Ionicons name="checkmark-circle" size={10} color="#10B981" />
                    <Text style={s.flixBadgeText}>Open</Text>
                  </View>
                )}
              </TouchableOpacity>
            ))}
            {loading && <ActivityIndicator color={tab.color} style={{ alignSelf: 'center', marginLeft: 20 }} />}
          </ScrollView>
        ) : (
        <FlatList
          data={items}
          keyExtractor={(it, i) => String(it.id || it._id || `${activeTab}_${i}`)}
          renderItem={renderItem}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3B82F6" />}
          onEndReached={onEndReached}
          onEndReachedThreshold={0.6}
          contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
          ListEmptyComponent={
            loading ? null : (
              <View style={s.emptyWrap}>
                <Ionicons name={tab.icon as any} size={48} color="#334155" />
                <Text style={s.emptyText}>No {activeTab} found</Text>
              </View>
            )
          }
          ListFooterComponent={
            loading ? (
              <View style={s.loader}>
                <ActivityIndicator color={tab.color} />
                <Text style={s.loaderText}>Loading…</Text>
              </View>
            ) : (!hasMore && items.length > 0) ? (
              <Text style={s.endText}>— End of {activeTab} —</Text>
            ) : null
          }
        />
        )}

        {/* Detail sheet */}
        <DetailSheet item={selected} tab={activeTab} onClose={() => setSelected(null)} color={tab.color} />

        {/* READING VISUALIZER — books, bibles, and tracks all open here */}
        {reader && (
          <ReadingVisualizer
            visible={!!reader}
            onClose={() => setReader(null)}
            itemType={reader.type}
            itemId={reader.id}
            itemTitle={reader.title}
            chapterIdx={reader.chapterIdx}
            totalChapters={reader.totalChapters}
            onChangeChapter={(newIdx) => setReader((r) => r ? { ...r, chapterIdx: newIdx } : null)}
            contentEndpoint={
              reader.type === 'bible'
                ? (id, idx) => `/api/academy/bible/${id}/chapter/${idx}/content`
                : reader.type === 'track'
                ? (id, idx) => `/api/academy/track/${id}/chapter/${idx}/content`
                : (reader.type as any) === 'subject'
                ? (id, idx) => `/api/academy/subject/${id}/chapter/${idx}/content`
                : undefined
            }
          />
        )}
      </SafeAreaView>
    </Modal>
  );
}

function searchPlaceholder(tab: TabKey): string {
  switch (tab) {
    case 'tracks':      return 'Filter by category (e.g. language, framework)...';
    case 'subjects':    return 'Search subjects...';
    case 'quizzes':     return 'Filter by domain (e.g. mobile_expanded, game_dev)...';
    case 'projects':    return 'Filter by difficulty (beginner/intermediate/advanced)...';
    case 'assessments': return 'Filter by track_id...';
    case 'challenges':  return 'Filter by difficulty...';
    case 'vault':       return 'Filter by category...';
    default: return 'Search...';
  }
}

function formatCount(n: number): string {
  if (n >= 10000) return `${(n / 1000).toFixed(1)}k`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return `${n}`;
}

// ─── Reusable card ────────────────────────────────────────────────────
function Card({ title, subtitle, meta, icon, color, onPress }: {
  title?: string; subtitle?: string; meta?: (string | undefined)[]; icon: string; color: string; onPress?: () => void;
}) {
  return (
    <TouchableOpacity style={[s.card, { borderLeftColor: color, borderLeftWidth: 4 }]} onPress={onPress} activeOpacity={0.7}>
      <View style={s.topRow}>
        <Ionicons name={icon as any} size={18} color={color} style={{ marginRight: 8 }} />
        <Text style={s.cardTitle} numberOfLines={2}>{title || '(untitled)'}</Text>
      </View>
      {subtitle ? <Text style={s.desc} numberOfLines={3}>{subtitle}</Text> : null}
      {meta && meta.filter(Boolean).length > 0 && (
        <View style={s.metaRow}>
          {meta.filter(Boolean).map((m, i) => (
            <View key={i} style={[s.badge, { backgroundColor: color + '20' }]}>
              <Text style={[s.badgeText, { color }]}>{String(m)}</Text>
            </View>
          ))}
        </View>
      )}
    </TouchableOpacity>
  );
}

// ─── Detail sheet ─────────────────────────────────────────────────────
function DetailSheet({ item, tab, onClose, color }: { item: any; tab: TabKey; onClose: () => void; color: string }) {
  const academy = useSettings(s => s.academy);
  const [playing, setPlaying] = useState(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { return () => { ttsStop(); setPlaying(false); }; }, [item?.id || item?._id]);
  if (!item) return null;

  const togglePlay = () => {
    if (playing) { ttsStop(); setPlaying(false); return; }
    const parts: string[] = [];
    if (item.title) parts.push(item.title);
    if (item.name) parts.push(item.name);
    if (item.question) parts.push(item.question);
    if (item.description) parts.push(item.description);
    if (item.content) parts.push(item.content);
    if (Array.isArray(item.options) && tab === 'quizzes') item.options.forEach((o: string, i: number) => parts.push(`Option ${String.fromCharCode(65 + i)}. ${o}`));
    if (Array.isArray(item.hints)) { parts.push('Hints:'); item.hints.forEach((h: string) => parts.push(h)); }
    if (Array.isArray(item.requirements)) { parts.push('Requirements:'); item.requirements.forEach((r: string) => parts.push(r)); }
    if (Array.isArray(item.constraints)) { parts.push('Constraints:'); item.constraints.forEach((c: string) => parts.push(c)); }
    if (Array.isArray(item.topics)) parts.push(`Topics: ${item.topics.join(', ')}`);
    const text = parts.filter(Boolean).join('. ');
    if (!text) return;
    setPlaying(true);
    // Use Jeeves persona flair when enabled (catchphrase + mannerism speed)
    if (isJeevesEnabled()) {
      const ctx = tab === 'quizzes' ? 'quiz_nudge'
                : tab === 'lessons' ? 'lesson'
                : tab === 'challenges' ? 'code_walkthrough'
                : 'lesson';
      jeevesSpeak(text, { context: ctx as any, readCode: academy.readCodeBlocks, onComplete: () => setPlaying(false) });
    } else {
      ttsSpeak(text, { readCode: academy.readCodeBlocks, onComplete: () => setPlaying(false) });
    }
  };

  // Settings-tuned reader typography
  const fs = academy.fontSize;
  const readerColor = academy.highContrast ? '#FFFFFF' : '#CBD5E1';

  return (
    <Modal visible={!!item} animationType="slide" transparent onRequestClose={onClose}>
      <View style={s.sheetBackdrop}>
        <View style={s.sheet}>
          <View style={s.sheetHeader}>
            <Text style={s.sheetTitle} numberOfLines={2}>
              {item.title || item.name || item.question || item.id || 'Detail'}
            </Text>
            {academy.ttsEnabled ? (
              <TouchableOpacity onPress={togglePlay} style={[s.ttsBtn, { backgroundColor: color + '22', borderColor: color }]}>
                <Ionicons name={playing ? 'stop' : 'play'} size={16} color={color} />
                <Text style={[s.ttsBtnText, { color }]}>{playing ? 'Stop' : 'Listen'}</Text>
              </TouchableOpacity>
            ) : null}
            <TouchableOpacity onPress={onClose} style={s.headerBtn}>
              <Ionicons name="close" size={24} color="#F8FAFC" />
            </TouchableOpacity>
          </View>
          <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 60 }}>
            {tab === 'quizzes' && (
              <>
                <Text style={[s.sheetQuestion, { fontSize: fs + 2, lineHeight: (fs + 2) * academy.lineHeight, color: readerColor }]}>{item.question}</Text>
                {(item.options || []).map((opt: string, i: number) => (
                  <View key={i} style={[s.quizOpt, { borderColor: color + '66' }]}>
                    <Text style={[s.quizLetter, { color }]}>{String.fromCharCode(65 + i)}</Text>
                    <Text style={s.quizOptText}>{opt}</Text>
                  </View>
                ))}
                {item.hints?.length > 0 && (
                  <>
                    <Text style={s.sheetSection}>Hints</Text>
                    {item.hints.map((h: string, i: number) => (
                      <Text key={i} style={s.sheetParagraph}>• {h}</Text>
                    ))}
                  </>
                )}
                <Row label="Difficulty" value={item.difficulty} />
                <Row label="Domain" value={item.domain} />
                <Row label="Topic" value={item.topic} />
              </>
            )}

            {tab !== 'quizzes' && item.description && (
              <Text style={s.sheetParagraph}>{item.description}</Text>
            )}

            {tab === 'subjects' && item.content && (
              <>
                <Text style={s.sheetSection}>Content</Text>
                <Text style={s.sheetParagraph}>{item.content}</Text>
              </>
            )}

            {tab === 'projects' && (
              <>
                {item.requirements?.length > 0 && (
                  <>
                    <Text style={s.sheetSection}>Requirements</Text>
                    {item.requirements.map((r: string, i: number) => (
                      <Text key={i} style={s.sheetParagraph}>✓ {r}</Text>
                    ))}
                  </>
                )}
                {item.starter_code && (
                  <>
                    <Text style={s.sheetSection}>Starter Code</Text>
                    <View style={s.codeBlock}>
                      <Text style={s.code} selectable>{item.starter_code}</Text>
                    </View>
                  </>
                )}
              </>
            )}

            {tab === 'challenges' && (
              <>
                {item.examples?.length > 0 && (
                  <>
                    <Text style={s.sheetSection}>Examples</Text>
                    {item.examples.map((ex: any, i: number) => (
                      <View key={i} style={s.exBlock}>
                        <Text style={s.exLabel}>Input:</Text>
                        <Text style={s.code}>{ex.input}</Text>
                        <Text style={s.exLabel}>Output:</Text>
                        <Text style={s.code}>{ex.output}</Text>
                      </View>
                    ))}
                  </>
                )}
                {item.constraints?.length > 0 && (
                  <>
                    <Text style={s.sheetSection}>Constraints</Text>
                    {item.constraints.map((c: string, i: number) => (
                      <Text key={i} style={s.sheetParagraph}>• {c}</Text>
                    ))}
                  </>
                )}
              </>
            )}

            {tab === 'knowledge' && item.topics?.length > 0 && (
              <>
                <Text style={s.sheetSection}>Topics</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
                  {item.topics.map((t: string, i: number) => (
                    <View key={i} style={[s.badge, { backgroundColor: color + '20', margin: 4 }]}>
                      <Text style={[s.badgeText, { color }]}>{t}</Text>
                    </View>
                  ))}
                </View>
              </>
            )}

            {tab === 'tracks' && (
              <>
                <Row label="Category" value={item.category} />
                <Row label="Total hours" value={`${item.total_hours}h`} />
                <Row label="Prerequisites" value={(item.prerequisites || []).join(', ') || 'None'} />
                <Row label="Certificate" value={item.certificate} />
              </>
            )}

            {tab === 'assessments' && (
              <>
                <Row label="Track" value={item.track_id} />
                <Row label="Duration" value={`${item.duration_minutes || 60} min`} />
                <Row label="Passing score" value={`${item.passing_score || 70}%`} />
                <Row label="Questions" value={`${item.questions?.length || item.question_count || 0}`} />
              </>
            )}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

function Row({ label, value }: { label: string; value: any }) {
  if (value === undefined || value === null || value === '') return null;
  return (
    <View style={s.rowDetail}>
      <Text style={s.rowLabel}>{label}</Text>
      <Text style={s.rowValue}>{String(value)}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F172A' },
  header: { flexDirection: 'row', alignItems: 'center', padding: 16, backgroundColor: '#1E293B', borderBottomWidth: 1, borderBottomColor: '#334155' },
  headerBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  headerTextContainer: { flex: 1, alignItems: 'center' },
  headerTitle: { fontSize: 18, fontWeight: '700', color: '#F8FAFC' },
  headerSub: { fontSize: 11, color: '#3B82F6', marginTop: 2, fontWeight: '600' },

  tabsScroll: { maxHeight: 60, backgroundColor: '#0B1222' },
  tabsRow: { paddingHorizontal: 12, paddingVertical: 10, alignItems: 'center' },
  tab: {
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 7,
    borderRadius: 10, marginRight: 8, backgroundColor: '#1E293B', borderWidth: 1, borderColor: '#334155',
    minHeight: 36,
  },
  tabLabel: { color: '#94A3B8', fontSize: 13, fontWeight: '600' },
  tabBadge: { backgroundColor: '#475569', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, marginLeft: 6 },
  tabBadgeText: { color: '#F8FAFC', fontSize: 10, fontWeight: '700' },

  searchBar: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: '#1E293B',
    marginHorizontal: 16, marginTop: 10, borderRadius: 12, paddingHorizontal: 14,
    borderWidth: 1, borderColor: '#334155',
  },
  searchInput: { flex: 1, color: '#F8FAFC', fontSize: 14, paddingVertical: 12, marginLeft: 8 },
  countLabel: { color: '#64748B', fontSize: 11, paddingHorizontal: 16, paddingTop: 10, fontWeight: '600' },
  listMetaRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingTop: 10 },
  flixToggle: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 10, paddingVertical: 5, backgroundColor: '#1E293B', borderRadius: 12,
  },
  flixToggleText: { color: '#F8FAFC', fontSize: 11, fontWeight: '600' },
  flixCard: {
    width: 140, marginRight: 12, padding: 8, borderRadius: 10, backgroundColor: '#1E293B',
  },
  flixCover: {
    width: 124, height: 170, borderRadius: 6,
    justifyContent: 'center', alignItems: 'center', borderWidth: 2,
  },
  flixTitle: { color: '#F8FAFC', fontSize: 12, fontWeight: '700', marginTop: 8 },
  flixSub: { color: '#94A3B8', fontSize: 10, marginTop: 2 },
  flixBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 3,
    marginTop: 4, paddingHorizontal: 5, paddingVertical: 2,
    backgroundColor: '#10B98122', alignSelf: 'flex-start', borderRadius: 4,
  },
  flixBadgeText: { color: '#10B981', fontSize: 9, fontWeight: '700' },
  continueCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    marginHorizontal: 16, marginTop: 12, padding: 12,
    backgroundColor: '#10B98114', borderLeftWidth: 3, borderLeftColor: '#10B981', borderRadius: 8,
  },
  continueIconWrap: { width: 44, height: 44, borderRadius: 22, backgroundColor: '#10B98122', justifyContent: 'center', alignItems: 'center' },
  continueLabel: { color: '#10B981', fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 },
  continueTitle: { color: '#F8FAFC', fontSize: 14, fontWeight: '700', marginTop: 2 },
  continueSub: { color: '#94A3B8', fontSize: 11, marginTop: 2 },

  card: { backgroundColor: '#1E293B', padding: 14, borderRadius: 12, marginBottom: 10 },
  topRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 6 },
  cardTitle: { fontSize: 15, fontWeight: '700', color: '#F8FAFC', flex: 1 },
  desc: { fontSize: 12, color: '#94A3B8', lineHeight: 18, marginBottom: 8 },
  metaRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 6 },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  badgeText: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },

  loader: { padding: 24, alignItems: 'center' },
  loaderText: { color: '#64748B', fontSize: 11, marginTop: 6 },
  endText: { textAlign: 'center', color: '#64748B', padding: 20, fontSize: 11, fontStyle: 'italic' },
  emptyWrap: { padding: 40, alignItems: 'center' },
  emptyText: { color: '#64748B', fontSize: 13, marginTop: 10 },

  // Detail sheet
  sheetBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: '#0F172A', borderTopLeftRadius: 20, borderTopRightRadius: 20, height: '85%' },
  sheetHeader: { flexDirection: 'row', alignItems: 'flex-start', padding: 16, borderBottomWidth: 1, borderBottomColor: '#1E293B' },
  sheetTitle: { flex: 1, fontSize: 16, fontWeight: '700', color: '#F8FAFC', marginRight: 12 },
  sheetQuestion: { fontSize: 17, fontWeight: '700', color: '#F8FAFC', marginBottom: 16, lineHeight: 24 },
  sheetSection: { fontSize: 12, fontWeight: '700', color: '#94A3B8', marginTop: 16, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  sheetParagraph: { fontSize: 14, color: '#CBD5E1', lineHeight: 22, marginBottom: 6 },

  quizOpt: { flexDirection: 'row', alignItems: 'center', padding: 12, borderRadius: 10, borderWidth: 1, marginBottom: 8, backgroundColor: '#1E293B' },
  quizLetter: { fontSize: 16, fontWeight: '800', marginRight: 12, width: 22 },
  quizOptText: { flex: 1, color: '#F8FAFC', fontSize: 14 },

  codeBlock: { backgroundColor: '#020617', padding: 12, borderRadius: 10, marginTop: 4, borderWidth: 1, borderColor: '#1E293B' },
  code: { color: '#CBD5E1', fontSize: 12, fontFamily: 'Courier' },

  ttsBtn: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, marginRight: 8 },
  ttsBtnText: { fontSize: 12, fontWeight: '700', marginLeft: 4 },

  exBlock: { backgroundColor: '#1E293B', padding: 10, borderRadius: 8, marginBottom: 8 },
  exLabel: { color: '#94A3B8', fontSize: 11, fontWeight: '700', marginTop: 4, marginBottom: 2 },

  rowDetail: { flexDirection: 'row', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: '#1E293B' },
  rowLabel: { color: '#64748B', fontSize: 12, width: 120, fontWeight: '600' },
  rowValue: { color: '#F8FAFC', fontSize: 13, flex: 1 },
});
