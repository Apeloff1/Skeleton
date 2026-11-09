// ============================================================================
// CODEDOCK v9.0.0 - ULTIMATE HUB MODAL
// Language Packs, Expansions, Algorithms, Compilation Bible
// ============================================================================

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  Modal,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  TextInput,
  Dimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const { width: SCREEN_WIDTH } = Dimensions.get('window');

interface HubModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
}

type HubTab = 'languages' | 'expansions' | 'algorithms' | 'bible';

interface LanguagePack {
  id: string;
  name: string;
  version: string;
  category: string;
  icon: string;
  color: string;
  features: string[];
  description: string;
  tier: number;
}

interface Expansion {
  id: string;
  name: string;
  category: string;
  description: string;
  languages?: string[];
  features: string[];
  status: string;
}

interface Algorithm {
  name: string;
  type?: string;
  complexity: string;
  description: string;
}

interface BibleChapter {
  id: string;
  title: string;
  subtitle: string;
  difficulty: string;
}

export const HubModal: React.FC<HubModalProps> = ({ visible, onClose, colors }) => {
  const [activeTab, setActiveTab] = useState<HubTab>('languages');
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  
  // Data states
  const [languagePacks, setLanguagePacks] = useState<LanguagePack[]>([]);
  const [expansions, setExpansions] = useState<Expansion[]>([]);
  const [algorithms, setAlgorithms] = useState<Record<string, Record<string, Algorithm>>>({});
  const [bibleChapters, setBibleChapters] = useState<BibleChapter[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [categories, setCategories] = useState<string[]>([]);
  
  // Selected item for detail view
  const [selectedItem, setSelectedItem] = useState<any>(null);
  const [detailView, setDetailView] = useState<'list' | 'detail'>('list');

  const backendUrl = process.env.EXPO_PUBLIC_BACKEND_URL || '';

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      if (activeTab === 'languages') {
        const res = await apiFetch(`${backendUrl}/api/language-packs`);
        const data = await res.json();
        setLanguagePacks(data.packs || []);
        setCategories(['all', ...(data.categories || [])]);
      } else if (activeTab === 'expansions') {
        const res = await apiFetch(`${backendUrl}/api/expansions`);
        const data = await res.json();
        setExpansions(data.expansions || []);
        setCategories(['all', ...(data.categories || [])]);
      } else if (activeTab === 'algorithms') {
        const res = await apiFetch(`${backendUrl}/api/algorithms`);
        const data = await res.json();
        setAlgorithms(data.algorithms || {});
        setCategories(['all', ...(data.categories || [])]);
      } else if (activeTab === 'bible') {
        const res = await apiFetch(`${backendUrl}/api/bible`);
        const data = await res.json();
        setBibleChapters(data.toc || []);
      }
    } catch (error) {
      console.error('Hub fetch error:', error);
    }
    setLoading(false);
  }, [activeTab, backendUrl]);

  useEffect(() => {
    if (visible) {
      fetchData();
      setSelectedCategory('all');
      setSearchQuery('');
      setDetailView('list');
    }
  }, [visible, activeTab, fetchData]);

  const filterItems = useCallback((items: any[]) => {
    return items.filter(item => {
      const matchesSearch = !searchQuery || 
        item.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.description?.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesCategory = selectedCategory === 'all' || item.category === selectedCategory;
      return matchesSearch && matchesCategory;
    });
  }, [searchQuery, selectedCategory]);

  const installExpansion = async (packId: string) => {
    try {
      await apiFetch(`${backendUrl}/api/expansions/${packId}/install`, { method: 'POST' });
      fetchData();
    } catch (error) {
      console.error('Install error:', error);
    }
  };

  const fetchBibleChapter = async (chapterId: string) => {
    try {
      const res = await apiFetch(`${backendUrl}/api/bible/chapter/${chapterId}`);
      const data = await res.json();
      setSelectedItem(data);
      setDetailView('detail');
    } catch (error) {
      console.error('Bible chapter fetch error:', error);
    }
  };

  const renderTabs = () => (
    <View style={[styles.tabBar, { backgroundColor: colors.surfaceAlt }]}>
      {[
        { key: 'languages', icon: 'code-slash', label: 'Languages' },
        { key: 'expansions', icon: 'cube', label: 'Packs' },
        { key: 'algorithms', icon: 'git-network', label: 'Algorithms' },
        { key: 'bible', icon: 'book', label: 'Bible' },
      ].map(tab => (
        <TouchableOpacity
          key={tab.key}
          style={[
            styles.tab,
            activeTab === tab.key && { backgroundColor: colors.primary + '30' }
          ]}
          onPress={() => setActiveTab(tab.key as HubTab)}
        >
          <Ionicons 
            name={tab.icon as any} 
            size={18} 
            color={activeTab === tab.key ? colors.primary : colors.textMuted} 
          />
          <Text style={[
            styles.tabText,
            { color: activeTab === tab.key ? colors.primary : colors.textMuted }
          ]}>
            {tab.label}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );

  const renderSearch = () => (
    <View style={[styles.searchContainer, { backgroundColor: colors.surface }]}>
      <Ionicons name="search" size={18} color={colors.textMuted} />
      <TextInput
        style={[styles.searchInput, { color: colors.text }]}
        placeholder="Search..."
        placeholderTextColor={colors.textMuted}
        value={searchQuery}
        onChangeText={setSearchQuery}
      />
      {searchQuery.length > 0 && (
        <TouchableOpacity onPress={() => setSearchQuery('')}>
          <Ionicons name="close-circle" size={18} color={colors.textMuted} />
        </TouchableOpacity>
      )}
    </View>
  );

  const renderCategoryFilter = () => (
    <ScrollView 
      horizontal 
      showsHorizontalScrollIndicator={false}
      style={styles.categoryContainer}
      contentContainerStyle={styles.categoryContent}
    >
      {categories.map(cat => (
        <TouchableOpacity
          key={cat}
          style={[
            styles.categoryChip,
            { backgroundColor: selectedCategory === cat ? colors.primary : colors.surface }
          ]}
          onPress={() => setSelectedCategory(cat)}
        >
          <Text style={[
            styles.categoryText,
            { color: selectedCategory === cat ? '#FFF' : colors.text }
          ]}>
            {cat.charAt(0).toUpperCase() + cat.slice(1)}
          </Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );

  const renderLanguagePacks = () => {
    const filtered = filterItems(languagePacks);
    return (
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.grid}>
          {filtered.map(pack => (
            <TouchableOpacity
              key={pack.id}
              style={[styles.languageCard, { backgroundColor: colors.surface }]}
              onPress={() => { setSelectedItem(pack); setDetailView('detail'); }}
            >
              <View style={[styles.languageIcon, { backgroundColor: pack.color + '20' }]}>
                <Ionicons name={pack.icon as any || 'code'} size={24} color={pack.color} />
              </View>
              <Text style={[styles.languageName, { color: colors.text }]}>{pack.name}</Text>
              <Text style={[styles.languageVersion, { color: colors.textMuted }]}>{pack.version}</Text>
              <View style={[styles.tierBadge, { backgroundColor: pack.tier === 1 ? '#10B981' : pack.tier === 2 ? '#F59E0B' : '#6B7280' }]}>
                <Text style={styles.tierText}>Tier {pack.tier}</Text>
              </View>
            </TouchableOpacity>
          ))}
        </View>
        {filtered.length === 0 && (
          <Text style={[styles.emptyText, { color: colors.textMuted }]}>No languages found</Text>
        )}
      </ScrollView>
    );
  };

  const renderExpansions = () => {
    const filtered = filterItems(expansions);
    return (
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {filtered.map(exp => (
          <View key={exp.id} style={[styles.expansionCard, { backgroundColor: colors.surface }]}>
            <View style={styles.expansionHeader}>
              <View style={[styles.expansionIcon, { backgroundColor: colors.primary + '20' }]}>
                <Ionicons name="cube" size={24} color={colors.primary} />
              </View>
              <View style={styles.expansionInfo}>
                <Text style={[styles.expansionName, { color: colors.text }]}>{exp.name}</Text>
                <Text style={[styles.expansionCategory, { color: colors.textMuted }]}>{exp.category}</Text>
              </View>
              <TouchableOpacity
                style={[
                  styles.installButton,
                  { backgroundColor: exp.status === 'installed' ? colors.success : colors.primary }
                ]}
                onPress={() => installExpansion(exp.id)}
                disabled={exp.status === 'installed'}
              >
                <Text style={styles.installText}>
                  {exp.status === 'installed' ? 'Installed' : 'Install'}
                </Text>
              </TouchableOpacity>
            </View>
            <Text style={[styles.expansionDesc, { color: colors.textMuted }]}>{exp.description}</Text>
            <View style={styles.featureTags}>
              {exp.features?.slice(0, 3).map((f: string, i: number) => (
                <View key={i} style={[styles.featureTag, { backgroundColor: colors.surfaceAlt }]}>
                  <Text style={[styles.featureTagText, { color: colors.text }]}>{f}</Text>
                </View>
              ))}
            </View>
          </View>
        ))}
        {filtered.length === 0 && (
          <Text style={[styles.emptyText, { color: colors.textMuted }]}>No expansions found</Text>
        )}
      </ScrollView>
    );
  };

  const renderAlgorithms = () => {
    const algCategories = Object.keys(algorithms);
    const filteredCategories = selectedCategory === 'all' ? algCategories : [selectedCategory];
    
    return (
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {filteredCategories.map(cat => (
          <View key={cat} style={styles.algCategory}>
            <Text style={[styles.algCategoryTitle, { color: colors.primary }]}>
              {cat.replace(/_/g, ' ').toUpperCase()}
            </Text>
            {algorithms[cat] && Object.entries(algorithms[cat]).map(([key, alg]) => (
              <View key={key} style={[styles.algCard, { backgroundColor: colors.surface }]}>
                <View style={styles.algHeader}>
                  <Text style={[styles.algName, { color: colors.text }]}>{alg.name}</Text>
                  <View style={[styles.complexityBadge, { backgroundColor: colors.warning + '20' }]}>
                    <Text style={[styles.complexityText, { color: colors.warning }]}>{alg.complexity}</Text>
                  </View>
                </View>
                {alg.type && (
                  <Text style={[styles.algType, { color: colors.textMuted }]}>Type: {alg.type}</Text>
                )}
                <Text style={[styles.algDesc, { color: colors.text }]}>{alg.description}</Text>
              </View>
            ))}
          </View>
        ))}
      </ScrollView>
    );
  };

  const renderBible = () => {
    if (detailView === 'detail' && selectedItem) {
      return (
        <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
          <TouchableOpacity 
            style={styles.backButton} 
            onPress={() => { setDetailView('list'); setSelectedItem(null); }}
          >
            <Ionicons name="arrow-back" size={20} color={colors.primary} />
            <Text style={[styles.backText, { color: colors.primary }]}>Back to Chapters</Text>
          </TouchableOpacity>
          
          <Text style={[styles.chapterTitle, { color: colors.text }]}>{selectedItem.title}</Text>
          <Text style={[styles.chapterSubtitle, { color: colors.textMuted }]}>{selectedItem.subtitle}</Text>
          
          <View style={[styles.difficultyBadge, { 
            backgroundColor: selectedItem.difficulty === 'beginner' ? '#10B981' : 
                           selectedItem.difficulty === 'intermediate' ? '#F59E0B' : 
                           selectedItem.difficulty === 'advanced' ? '#EF4444' : '#8B5CF6'
          }]}>
            <Text style={styles.difficultyText}>{selectedItem.difficulty?.toUpperCase()}</Text>
          </View>
          
          <View style={[styles.contentBox, { backgroundColor: colors.surface }]}>
            <Text style={[styles.chapterContent, { color: colors.text }]}>
              {selectedItem.content}
            </Text>
          </View>
          
          {selectedItem.exercises && selectedItem.exercises.length > 0 && (
            <View style={styles.exercisesSection}>
              <Text style={[styles.exercisesTitle, { color: colors.text }]}>Exercises</Text>
              {selectedItem.exercises.map((ex: any, i: number) => (
                <View key={i} style={[styles.exerciseCard, { backgroundColor: colors.surface }]}>
                  <View style={[styles.exerciseType, { backgroundColor: colors.primary + '20' }]}>
                    <Text style={[styles.exerciseTypeText, { color: colors.primary }]}>{ex.type}</Text>
                  </View>
                  <Text style={[styles.exercisePrompt, { color: colors.text }]}>{ex.prompt || ex.question}</Text>
                </View>
              ))}
            </View>
          )}
        </ScrollView>
      );
    }
    
    return (
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        <View style={[styles.bibleHeader, { backgroundColor: colors.surface }]}>
          <Ionicons name="book" size={40} color={colors.primary} />
          <Text style={[styles.bibleTitle, { color: colors.text }]}>The Complete Compilation Bible</Text>
          <Text style={[styles.bibleSubtitle, { color: colors.textMuted }]}>
            {bibleChapters.length} Chapters • 40+ Hours • Expert Level Certification
          </Text>
        </View>
        
        {bibleChapters.map((chapter, index) => (
          <TouchableOpacity
            key={chapter.id}
            style={[styles.bibleChapter, { backgroundColor: colors.surface }]}
            onPress={() => fetchBibleChapter(chapter.id)}
          >
            <View style={[styles.chapterNumber, { backgroundColor: colors.primary }]}>
              <Text style={styles.chapterNumberText}>{index + 1}</Text>
            </View>
            <View style={styles.chapterInfo}>
              <Text style={[styles.chapterName, { color: colors.text }]}>{chapter.title}</Text>
              <Text style={[styles.chapterSub, { color: colors.textMuted }]}>{chapter.subtitle}</Text>
            </View>
            <View style={[styles.diffBadge, { 
              backgroundColor: chapter.difficulty === 'beginner' ? '#10B98130' : 
                             chapter.difficulty === 'intermediate' ? '#F59E0B30' : 
                             chapter.difficulty === 'advanced' ? '#EF444430' : '#8B5CF630'
            }]}>
              <Text style={[styles.diffText, {
                color: chapter.difficulty === 'beginner' ? '#10B981' : 
                       chapter.difficulty === 'intermediate' ? '#F59E0B' : 
                       chapter.difficulty === 'advanced' ? '#EF4444' : '#8B5CF6'
              }]}>
                {chapter.difficulty?.charAt(0).toUpperCase()}
              </Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
          </TouchableOpacity>
        ))}
      </ScrollView>
    );
  };

  const renderLanguageDetail = () => {
    if (!selectedItem) return null;
    const pack = selectedItem as LanguagePack;
    
    return (
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        <TouchableOpacity 
          style={styles.backButton} 
          onPress={() => { setDetailView('list'); setSelectedItem(null); }}
        >
          <Ionicons name="arrow-back" size={20} color={colors.primary} />
          <Text style={[styles.backText, { color: colors.primary }]}>Back</Text>
        </TouchableOpacity>
        
        <View style={[styles.detailHeader, { backgroundColor: pack.color + '15' }]}>
          <View style={[styles.detailIcon, { backgroundColor: pack.color + '30' }]}>
            <Ionicons name={pack.icon as any || 'code'} size={48} color={pack.color} />
          </View>
          <Text style={[styles.detailName, { color: colors.text }]}>{pack.name}</Text>
          <Text style={[styles.detailVersion, { color: colors.textMuted }]}>{pack.version}</Text>
        </View>
        
        <View style={[styles.detailSection, { backgroundColor: colors.surface }]}>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>Description</Text>
          <Text style={[styles.sectionContent, { color: colors.textMuted }]}>{pack.description}</Text>
        </View>
        
        <View style={[styles.detailSection, { backgroundColor: colors.surface }]}>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>Features</Text>
          <View style={styles.featureList}>
            {pack.features?.map((f, i) => (
              <View key={i} style={styles.featureItem}>
                <Ionicons name="checkmark-circle" size={16} color={colors.success} />
                <Text style={[styles.featureText, { color: colors.text }]}>
                  {f.replace(/_/g, ' ')}
                </Text>
              </View>
            ))}
          </View>
        </View>
        
        <View style={[styles.detailMeta, { backgroundColor: colors.surface }]}>
          <View style={styles.metaItem}>
            <Text style={[styles.metaLabel, { color: colors.textMuted }]}>Category</Text>
            <Text style={[styles.metaValue, { color: colors.text }]}>{pack.category}</Text>
          </View>
          <View style={styles.metaItem}>
            <Text style={[styles.metaLabel, { color: colors.textMuted }]}>Tier</Text>
            <Text style={[styles.metaValue, { color: colors.text }]}>Tier {pack.tier}</Text>
          </View>
        </View>
      </ScrollView>
    );
  };

  const renderContent = () => {
    if (loading) {
      return (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={[styles.loadingText, { color: colors.textMuted }]}>Loading...</Text>
        </View>
      );
    }
    
    if (detailView === 'detail' && activeTab === 'languages') {
      return renderLanguageDetail();
    }
    
    switch (activeTab) {
      case 'languages': return renderLanguagePacks();
      case 'expansions': return renderExpansions();
      case 'algorithms': return renderAlgorithms();
      case 'bible': return renderBible();
      default: return null;
    }
  };

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet">
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        {/* Header */}
        <View style={[styles.header, { backgroundColor: colors.surface }]}>
          <TouchableOpacity onPress={onClose} style={styles.closeButton}>
            <Ionicons name="close" size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerTitle}>
            <Ionicons name="planet" size={24} color={colors.primary} />
            <Text style={[styles.title, { color: colors.text }]}>Ultimate Hub</Text>
          </View>
          <View style={styles.headerBadge}>
            <Text style={[styles.badgeText, { color: colors.primary }]}>v9.0</Text>
          </View>
        </View>
        
        {renderTabs()}
        {activeTab !== 'bible' && renderSearch()}
        {activeTab !== 'bible' && activeTab !== 'algorithms' && renderCategoryFilter()}
        {activeTab === 'algorithms' && categories.length > 1 && renderCategoryFilter()}
        {renderContent()}
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    paddingTop: 50,
  },
  closeButton: {
    padding: 8,
  },
  headerTitle: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
  },
  headerBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
    backgroundColor: 'rgba(99, 102, 241, 0.1)',
  },
  badgeText: {
    fontSize: 12,
    fontWeight: '600',
  },
  tabBar: {
    flexDirection: 'row',
    paddingHorizontal: 8,
    paddingVertical: 8,
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: 8,
    gap: 6,
  },
  tabText: {
    fontSize: 12,
    fontWeight: '600',
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: 16,
    marginVertical: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 10,
    gap: 8,
  },
  searchInput: {
    flex: 1,
    fontSize: 14,
  },
  categoryContainer: {
    maxHeight: 44,
  },
  categoryContent: {
    paddingHorizontal: 16,
    gap: 8,
  },
  categoryChip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 16,
  },
  categoryText: {
    fontSize: 12,
    fontWeight: '600',
  },
  content: {
    flex: 1,
    paddingHorizontal: 16,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    paddingVertical: 12,
  },
  languageCard: {
    width: (SCREEN_WIDTH - 56) / 3,
    padding: 12,
    borderRadius: 12,
    alignItems: 'center',
  },
  languageIcon: {
    width: 48,
    height: 48,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 8,
  },
  languageName: {
    fontSize: 12,
    fontWeight: '600',
    textAlign: 'center',
  },
  languageVersion: {
    fontSize: 10,
    marginTop: 2,
  },
  tierBadge: {
    marginTop: 6,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  tierText: {
    fontSize: 8,
    fontWeight: '700',
    color: '#FFF',
  },
  expansionCard: {
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
  },
  expansionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10,
  },
  expansionIcon: {
    width: 44,
    height: 44,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  expansionInfo: {
    flex: 1,
    marginLeft: 12,
  },
  expansionName: {
    fontSize: 16,
    fontWeight: '600',
  },
  expansionCategory: {
    fontSize: 12,
    marginTop: 2,
  },
  installButton: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
  },
  installText: {
    color: '#FFF',
    fontSize: 12,
    fontWeight: '600',
  },
  expansionDesc: {
    fontSize: 13,
    lineHeight: 18,
    marginBottom: 10,
  },
  featureTags: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  featureTag: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  featureTagText: {
    fontSize: 10,
    fontWeight: '500',
  },
  algCategory: {
    marginBottom: 20,
  },
  algCategoryTitle: {
    fontSize: 12,
    fontWeight: '700',
    marginBottom: 10,
    letterSpacing: 1,
  },
  algCard: {
    padding: 14,
    borderRadius: 10,
    marginBottom: 8,
  },
  algHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  algName: {
    fontSize: 15,
    fontWeight: '600',
  },
  complexityBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  complexityText: {
    fontSize: 11,
    fontWeight: '600',
  },
  algType: {
    fontSize: 11,
    marginBottom: 4,
  },
  algDesc: {
    fontSize: 13,
    lineHeight: 18,
  },
  bibleHeader: {
    padding: 24,
    borderRadius: 16,
    alignItems: 'center',
    marginVertical: 12,
  },
  bibleTitle: {
    fontSize: 18,
    fontWeight: '700',
    marginTop: 12,
    textAlign: 'center',
  },
  bibleSubtitle: {
    fontSize: 12,
    marginTop: 6,
  },
  bibleChapter: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    borderRadius: 12,
    marginBottom: 8,
  },
  chapterNumber: {
    width: 36,
    height: 36,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chapterNumberText: {
    color: '#FFF',
    fontSize: 14,
    fontWeight: '700',
  },
  chapterInfo: {
    flex: 1,
    marginLeft: 12,
  },
  chapterName: {
    fontSize: 14,
    fontWeight: '600',
  },
  chapterSub: {
    fontSize: 11,
    marginTop: 2,
  },
  diffBadge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 8,
  },
  diffText: {
    fontSize: 12,
    fontWeight: '700',
  },
  backButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 12,
  },
  backText: {
    fontSize: 14,
    fontWeight: '600',
  },
  chapterTitle: {
    fontSize: 22,
    fontWeight: '700',
    marginBottom: 4,
  },
  chapterSubtitle: {
    fontSize: 14,
    marginBottom: 12,
  },
  difficultyBadge: {
    alignSelf: 'flex-start',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
    marginBottom: 16,
  },
  difficultyText: {
    color: '#FFF',
    fontSize: 11,
    fontWeight: '700',
  },
  contentBox: {
    padding: 16,
    borderRadius: 12,
    marginBottom: 16,
  },
  chapterContent: {
    fontSize: 14,
    lineHeight: 22,
  },
  exercisesSection: {
    marginBottom: 20,
  },
  exercisesTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
  },
  exerciseCard: {
    padding: 14,
    borderRadius: 10,
    marginBottom: 8,
  },
  exerciseType: {
    alignSelf: 'flex-start',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    marginBottom: 8,
  },
  exerciseTypeText: {
    fontSize: 10,
    fontWeight: '600',
  },
  exercisePrompt: {
    fontSize: 13,
    lineHeight: 18,
  },
  detailHeader: {
    padding: 24,
    borderRadius: 16,
    alignItems: 'center',
    marginBottom: 16,
  },
  detailIcon: {
    width: 80,
    height: 80,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
  },
  detailName: {
    fontSize: 24,
    fontWeight: '700',
  },
  detailVersion: {
    fontSize: 14,
    marginTop: 4,
  },
  detailSection: {
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },
  sectionContent: {
    fontSize: 13,
    lineHeight: 20,
  },
  featureList: {
    gap: 8,
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  featureText: {
    fontSize: 13,
  },
  detailMeta: {
    flexDirection: 'row',
    padding: 16,
    borderRadius: 12,
    marginBottom: 20,
  },
  metaItem: {
    flex: 1,
  },
  metaLabel: {
    fontSize: 11,
    marginBottom: 4,
  },
  metaValue: {
    fontSize: 14,
    fontWeight: '600',
  },
  loadingContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
  },
  emptyText: {
    textAlign: 'center',
    marginTop: 40,
    fontSize: 14,
  },
});

export default HubModal;
