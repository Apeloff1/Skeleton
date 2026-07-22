/**
 * Learning Hub Modal v12.5 - Multi-Layer Learning System
 * 
 * Comprehensive learning interface with:
 * - 6 redundant learning layers
 * - 10 learning domains
 * - 5 learning modes
 * - 5 mastery levels
 * - Real-time progress tracking
 */

import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Dimensions,
  RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const { width: SCREEN_WIDTH } = Dimensions.get('window');
const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface LearningHubModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  userId?: string;
}

interface LearningDomain {
  id: string;
  name: string;
  description: string;
  estimated_hours: number;
  prerequisites: string[];
  redundancy_coverage: number;
  layer_count: number;
}

interface LearningLayer {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  retention_boost: string;
  best_for: string[];
}

interface LearningMode {
  id: string;
  name: string;
  description: string;
  icon: string;
  recommended_for: string;
}

// Domain Card Component
const DomainCard: React.FC<{
  domain: LearningDomain;
  colors: any;
  onPress: () => void;
}> = ({ domain, colors, onPress }) => {
  const getDomainIcon = (id: string): string => {
    const icons: Record<string, string> = {
      programming_fundamentals: 'code-slash',
      data_structures: 'git-network',
      algorithms: 'analytics',
      web_development: 'globe',
      mobile_development: 'phone-portrait',
      ai_ml: 'hardware-chip',
      game_development: 'game-controller',
      devops_cloud: 'cloud',
      security: 'shield-checkmark',
      databases: 'server',
    };
    return icons[id] || 'book';
  };

  const getDomainColor = (id: string): string => {
    const domainColors: Record<string, string> = {
      programming_fundamentals: '#8B5CF6',
      data_structures: '#2563EB',
      algorithms: '#10B981',
      web_development: '#F59E0B',
      mobile_development: '#EF4444',
      ai_ml: '#6366F1',
      game_development: '#EC4899',
      devops_cloud: '#3B82F6',
      security: '#F97316',
      databases: '#84CC16',
    };
    return domainColors[id] || colors.primary;
  };

  const iconName = getDomainIcon(domain.id);
  const domainColor = getDomainColor(domain.id);

  return (
    <TouchableOpacity
      style={[styles.domainCard, { backgroundColor: colors.surfaceAlt }]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <View style={[styles.domainIconContainer, { backgroundColor: domainColor + '20' }]}>
        <Ionicons name={iconName as any} size={28} color={domainColor} />
      </View>
      <View style={styles.domainInfo}>
        <Text style={[styles.domainName, { color: colors.text }]}>{domain.name}</Text>
        <Text style={[styles.domainDescription, { color: colors.textMuted }]} numberOfLines={2}>
          {domain.description}
        </Text>
        <View style={styles.domainMeta}>
          <View style={styles.metaItem}>
            <Ionicons name="time" size={12} color={colors.textMuted} />
            <Text style={[styles.metaText, { color: colors.textMuted }]}>
              {domain.estimated_hours}h
            </Text>
          </View>
          <View style={styles.metaItem}>
            <Ionicons name="layers" size={12} color={domainColor} />
            <Text style={[styles.metaText, { color: domainColor }]}>
              {domain.layer_count} layers
            </Text>
          </View>
        </View>
      </View>
      <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
    </TouchableOpacity>
  );
};

// Layer Card Component
const LayerCard: React.FC<{
  layer: LearningLayer;
  colors: any;
  isSelected?: boolean;
  onPress: () => void;
}> = ({ layer, colors, isSelected, onPress }) => (
  <TouchableOpacity
    style={[
      styles.layerCard,
      { 
        backgroundColor: isSelected ? layer.color + '20' : colors.surfaceAlt,
        borderColor: isSelected ? layer.color : 'transparent',
        borderWidth: isSelected ? 2 : 0,
      }
    ]}
    onPress={onPress}
    activeOpacity={0.7}
  >
    <View style={[styles.layerIconContainer, { backgroundColor: layer.color + '30' }]}>
      <Ionicons name={layer.icon as any} size={24} color={layer.color} />
    </View>
    <Text style={[styles.layerName, { color: colors.text }]}>{layer.name}</Text>
    <Text style={[styles.layerBoost, { color: layer.color }]}>+{layer.retention_boost}</Text>
  </TouchableOpacity>
);

// Mode Selector Component
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const ModeSelector: React.FC<{
  modes: LearningMode[];
  selectedMode: string;
  onSelect: (mode: string) => void;
  colors: any;
}> = ({ modes, selectedMode, onSelect, colors }) => (
  <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.modeSelector}>
    {modes.map((mode) => (
      <TouchableOpacity
        key={mode.id}
        style={[
          styles.modeChip,
          {
            backgroundColor: selectedMode === mode.id ? colors.primary : colors.surfaceAlt,
          },
        ]}
        onPress={() => onSelect(mode.id)}
      >
        <Ionicons
          name={mode.icon as any}
          size={16}
          color={selectedMode === mode.id ? '#fff' : colors.textMuted}
        />
        <Text
          style={[
            styles.modeChipText,
            { color: selectedMode === mode.id ? '#fff' : colors.text },
          ]}
        >
          {mode.name}
        </Text>
      </TouchableOpacity>
    ))}
  </ScrollView>
);

// Stats Overview Component
const StatsOverview: React.FC<{
  stats: any;
  colors: any;
}> = ({ stats, colors }) => {
  if (!stats) return null;
  
  return (
    <View style={[styles.statsContainer, { backgroundColor: colors.surfaceAlt }]}>
      <View style={styles.statItem}>
        <Text style={[styles.statValue, { color: colors.primary }]}>{stats.total_domains || 0}</Text>
        <Text style={[styles.statLabel, { color: colors.textMuted }]}>Domains</Text>
      </View>
      <View style={[styles.statDivider, { backgroundColor: colors.border }]} />
      <View style={styles.statItem}>
        <Text style={[styles.statValue, { color: '#10B981' }]}>{stats.total_learning_hours || 0}</Text>
        <Text style={[styles.statLabel, { color: colors.textMuted }]}>Hours</Text>
      </View>
      <View style={[styles.statDivider, { backgroundColor: colors.border }]} />
      <View style={styles.statItem}>
        <Text style={[styles.statValue, { color: '#F59E0B' }]}>{stats.redundancy_layers || 6}</Text>
        <Text style={[styles.statLabel, { color: colors.textMuted }]}>Layers</Text>
      </View>
      <View style={[styles.statDivider, { backgroundColor: colors.border }]} />
      <View style={styles.statItem}>
        <Text style={[styles.statValue, { color: '#EF4444' }]}>{stats.learning_modes || 5}</Text>
        <Text style={[styles.statLabel, { color: colors.textMuted }]}>Modes</Text>
      </View>
    </View>
  );
};

// Main Learning Hub Modal
export const LearningHubModal: React.FC<LearningHubModalProps> = ({
  visible,
  onClose,
  colors,
  userId = 'default_user',
}) => {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState<'domains' | 'layers' | 'modes'>('domains');
  const [domains, setDomains] = useState<LearningDomain[]>([]);
  const [layers, setLayers] = useState<LearningLayer[]>([]);
  const [modes, setModes] = useState<LearningMode[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [selectedMode, setSelectedMode] = useState('guided');
  const [, setSelectedDomain] = useState<LearningDomain | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [domainsRes, layersRes, modesRes, statsRes] = await Promise.all([
        apiFetch(`${API_BASE}/api/learning-engine/domains`),
        apiFetch(`${API_BASE}/api/learning-engine/layers`),
        apiFetch(`${API_BASE}/api/learning-engine/modes`),
        apiFetch(`${API_BASE}/api/learning-engine/stats`),
      ]);

      if (domainsRes.ok) {
        const data = await domainsRes.json();
        setDomains(data.domains || []);
      }
      if (layersRes.ok) {
        const data = await layersRes.json();
        setLayers(data.layers || []);
      }
      if (modesRes.ok) {
        const data = await modesRes.json();
        setModes(data.modes || []);
      }
      if (statsRes.ok) {
        const data = await statsRes.json();
        setStats(data);
      }
    } catch (error) {
      console.error('Failed to load learning data:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (visible) {
      setLoading(true);
      loadData();
    }
  }, [visible, loadData]);

  const onRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const renderTabContent = () => {
    switch (activeTab) {
      case 'domains':
        return (
          <View style={styles.tabContent}>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>
              📚 Learning Domains
            </Text>
            <Text style={[styles.sectionSubtitle, { color: colors.textMuted }]}>
              Choose your learning path with 6x redundant coverage per topic
            </Text>
            {domains.map((domain) => (
              <DomainCard
                key={domain.id}
                domain={domain}
                colors={colors}
                onPress={() => setSelectedDomain(domain)}
              />
            ))}
          </View>
        );
      case 'layers':
        return (
          <View style={styles.tabContent}>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>
              🧠 Learning Layers
            </Text>
            <Text style={[styles.sectionSubtitle, { color: colors.textMuted }]}>
              Each topic is taught through 6 different cognitive pathways
            </Text>
            <View style={styles.layersGrid}>
              {layers.map((layer) => (
                <LayerCard
                  key={layer.id}
                  layer={layer}
                  colors={colors}
                  onPress={() => {}}
                />
              ))}
            </View>
            <View style={[styles.infoBox, { backgroundColor: colors.primary + '10' }]}>
              <Ionicons name="information-circle" size={20} color={colors.primary} />
              <Text style={[styles.infoText, { color: colors.text }]}>
                Complete all 6 layers for 100% retention. Each layer reinforces through different neural pathways.
              </Text>
            </View>
          </View>
        );
      case 'modes':
        return (
          <View style={styles.tabContent}>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>
              🎯 Learning Modes
            </Text>
            <Text style={[styles.sectionSubtitle, { color: colors.textMuted }]}>
              Choose how you want to learn based on your style and goals
            </Text>
            {modes.map((mode) => (
              <TouchableOpacity
                key={mode.id}
                style={[
                  styles.modeCard,
                  { 
                    backgroundColor: selectedMode === mode.id ? colors.primary + '20' : colors.surfaceAlt,
                    borderColor: selectedMode === mode.id ? colors.primary : 'transparent',
                    borderWidth: selectedMode === mode.id ? 2 : 0,
                  }
                ]}
                onPress={() => setSelectedMode(mode.id)}
              >
                <View style={[styles.modeIconContainer, { backgroundColor: colors.primary + '20' }]}>
                  <Ionicons name={mode.icon as any} size={24} color={colors.primary} />
                </View>
                <View style={styles.modeInfo}>
                  <Text style={[styles.modeName, { color: colors.text }]}>{mode.name}</Text>
                  <Text style={[styles.modeDescription, { color: colors.textMuted }]}>
                    {mode.description}
                  </Text>
                  <Text style={[styles.modeRecommended, { color: colors.primary }]}>
                    Best for: {mode.recommended_for}
                  </Text>
                </View>
                {selectedMode === mode.id && (
                  <Ionicons name="checkmark-circle" size={24} color={colors.primary} />
                )}
              </TouchableOpacity>
            ))}
          </View>
        );
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={[styles.modalContainer, { backgroundColor: 'rgba(0,0,0,0.5)' }]}>
        <View style={[styles.modalContent, { backgroundColor: colors.background }]}>
          {/* Header */}
          <View style={[styles.header, { borderBottomColor: colors.border }]}>
            <View style={styles.headerLeft}>
              <Ionicons name="school" size={24} color={colors.primary} />
              <View>
                <Text style={[styles.headerTitle, { color: colors.text }]}>
                  Learning Hub
                </Text>
                <Text style={[styles.headerSubtitle, { color: colors.textMuted }]}>
                  Multi-Layer Learning System
                </Text>
              </View>
            </View>
            <TouchableOpacity onPress={onClose} style={styles.closeButton}>
              <Ionicons name="close" size={24} color={colors.text} />
            </TouchableOpacity>
          </View>

          {loading ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color={colors.primary} />
              <Text style={[styles.loadingText, { color: colors.textMuted }]}>
                Loading learning system...
              </Text>
            </View>
          ) : (
            <>
              {/* Stats Overview */}
              {stats && <StatsOverview stats={stats} colors={colors} />}

              {/* Tab Navigation */}
              <View style={[styles.tabBar, { borderBottomColor: colors.border }]}>
                {(['domains', 'layers', 'modes'] as const).map((tab) => (
                  <TouchableOpacity
                    key={tab}
                    style={[
                      styles.tabButton,
                      activeTab === tab && { borderBottomColor: colors.primary, borderBottomWidth: 2 },
                    ]}
                    onPress={() => setActiveTab(tab)}
                  >
                    <Text
                      style={[
                        styles.tabButtonText,
                        { color: activeTab === tab ? colors.primary : colors.textMuted },
                      ]}
                    >
                      {tab.charAt(0).toUpperCase() + tab.slice(1)}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Content */}
              <ScrollView
                style={styles.scrollContent}
                showsVerticalScrollIndicator={false}
                refreshControl={
                  <RefreshControl
                    refreshing={refreshing}
                    onRefresh={onRefresh}
                    tintColor={colors.primary}
                  />
                }
              >
                {renderTabContent()}
                <View style={{ height: 40 }} />
              </ScrollView>
            </>
          )}
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  modalContainer: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  modalContent: {
    height: '92%',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: '700',
  },
  headerSubtitle: {
    fontSize: 12,
  },
  closeButton: {
    padding: 4,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 16,
  },
  loadingText: {
    fontSize: 14,
  },
  statsContainer: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
    margin: 16,
    padding: 16,
    borderRadius: 12,
  },
  statItem: {
    alignItems: 'center',
  },
  statValue: {
    fontSize: 24,
    fontWeight: '700',
  },
  statLabel: {
    fontSize: 11,
    marginTop: 2,
  },
  statDivider: {
    width: 1,
    height: 40,
  },
  tabBar: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    paddingHorizontal: 16,
  },
  tabButton: {
    flex: 1,
    paddingVertical: 12,
    alignItems: 'center',
  },
  tabButtonText: {
    fontSize: 14,
    fontWeight: '600',
  },
  scrollContent: {
    flex: 1,
  },
  tabContent: {
    padding: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 4,
  },
  sectionSubtitle: {
    fontSize: 13,
    marginBottom: 16,
  },
  domainCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
    gap: 12,
  },
  domainIconContainer: {
    width: 56,
    height: 56,
    borderRadius: 28,
    justifyContent: 'center',
    alignItems: 'center',
  },
  domainInfo: {
    flex: 1,
  },
  domainName: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 4,
  },
  domainDescription: {
    fontSize: 12,
    marginBottom: 8,
  },
  domainMeta: {
    flexDirection: 'row',
    gap: 16,
  },
  metaItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  metaText: {
    fontSize: 11,
  },
  layersGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    marginBottom: 16,
  },
  layerCard: {
    width: (SCREEN_WIDTH - 56) / 2,
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
  },
  layerIconContainer: {
    width: 48,
    height: 48,
    borderRadius: 24,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
  },
  layerName: {
    fontSize: 12,
    fontWeight: '600',
    textAlign: 'center',
    marginBottom: 4,
  },
  layerBoost: {
    fontSize: 11,
    fontWeight: '700',
  },
  infoBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    padding: 12,
    borderRadius: 8,
    gap: 8,
  },
  infoText: {
    flex: 1,
    fontSize: 12,
    lineHeight: 18,
  },
  modeSelector: {
    marginBottom: 16,
  },
  modeChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
    marginRight: 8,
    gap: 6,
  },
  modeChipText: {
    fontSize: 13,
    fontWeight: '500',
  },
  modeCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
    gap: 12,
  },
  modeIconContainer: {
    width: 48,
    height: 48,
    borderRadius: 24,
    justifyContent: 'center',
    alignItems: 'center',
  },
  modeInfo: {
    flex: 1,
  },
  modeName: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 4,
  },
  modeDescription: {
    fontSize: 12,
    marginBottom: 4,
  },
  modeRecommended: {
    fontSize: 11,
    fontWeight: '500',
  },
});

export default LearningHubModal;
