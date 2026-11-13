/**
 * AI Interactions Log Modal v12.0
 * 
 * Direct-to-Jeeves log of all AI interactions within the app
 * Visualizes data from logscraper.py backend
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Modal,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { logscraper, exportAPI } from '../../services/api';


interface AIInteractionsLogModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  userId?: string;
}

interface Interaction {
  id: string;
  type: string;
  prompt: string;
  response?: string;
  timestamp: string;
  model?: string;
}

type TabType = 'all' | 'by_type' | 'insights' | 'stats';

const TYPE_COLORS: Record<string, string> = {
  'code_generation': '#8B5CF6',
  'explain': '#3B82F6',
  'debug': '#EF4444',
  'optimize': '#10B981',
  'refactor': '#F59E0B',
  'test_gen': '#EC4899',
  'security': '#DC2626',
  'ask': '#6366F1',
  'teach': '#3B82F6',
  'default': '#6B7280',
};

const TYPE_ICONS: Record<string, string> = {
  'code_generation': 'code-slash',
  'explain': 'information-circle',
  'debug': 'bug',
  'optimize': 'rocket',
  'refactor': 'git-compare',
  'test_gen': 'flask',
  'security': 'shield-checkmark',
  'ask': 'chatbubble',
  'teach': 'school',
  'default': 'sparkles',
};

export const AIInteractionsLogModal: React.FC<AIInteractionsLogModalProps> = ({
  visible,
  onClose,
  colors,
  userId = 'default_user',
}) => {
  const [activeTab, setActiveTab] = useState<TabType>('all');
  const [loading, setLoading] = useState(false);
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [insights, setInsights] = useState<any[]>([]);
  const [profile, setProfile] = useState<any>(null);
  const [selectedType, setSelectedType] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [profileRes, insightsRes, aiStatsRes] = await Promise.all([
        logscraper.getProfile(userId),
        logscraper.getInsights(userId),
        exportAPI.getAIInteractions(userId),
      ]);

      if (profileRes.success && profileRes.data) {
        setProfile(profileRes.data);
        // Convert profile data to interactions list
        const interactionsList: Interaction[] = [];
        // Add recent actions as interactions
        if (profileRes.data.recent_actions) {
          profileRes.data.recent_actions.forEach((action: any, i: number) => {
            interactionsList.push({
              id: `action_${i}`,
              type: action.action_type || 'unknown',
              prompt: action.action_data?.prompt || JSON.stringify(action.action_data) || 'No prompt',
              response: action.action_data?.response,
              timestamp: action.timestamp || new Date().toISOString(),
              model: action.action_data?.model || 'GPT-4o',
            });
          });
        }
        setInteractions(interactionsList);
      }

      if (insightsRes.success && insightsRes.data) {
        setInsights(insightsRes.data.insights || []);
      }

      if (aiStatsRes.success && aiStatsRes.data) {
        setStats(aiStatsRes.data);
      }
    } catch (err) {
      console.error('Error fetching AI interactions:', err);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    if (visible) {
      fetchData();
    }
  }, [visible, fetchData]);

  const getTypeColor = (type: string) => TYPE_COLORS[type] || TYPE_COLORS.default;
  const getTypeIcon = (type: string) => TYPE_ICONS[type] || TYPE_ICONS.default;

  const filteredInteractions = selectedType
    ? interactions.filter(i => i.type === selectedType)
    : interactions;

  const renderTabs = () => (
    <View style={styles.tabBar}>
      {[
        { id: 'all', label: 'All', icon: 'list' },
        { id: 'by_type', label: 'By Type', icon: 'filter' },
        { id: 'insights', label: 'Insights', icon: 'bulb' },
        { id: 'stats', label: 'Stats', icon: 'stats-chart' },
      ].map(tab => (
        <TouchableOpacity
          key={tab.id}
          style={[
            styles.tab,
            activeTab === tab.id && {
              backgroundColor: colors.primary + '20',
              borderBottomColor: colors.primary,
              borderBottomWidth: 2,
            }
          ]}
          onPress={() => {
            setActiveTab(tab.id as TabType);
            setSelectedType(null);
          }}
        >
          <Ionicons
            name={tab.icon as any}
            size={18}
            color={activeTab === tab.id ? colors.primary : colors.textMuted}
          />
          <Text style={[
            styles.tabText,
            { color: activeTab === tab.id ? colors.primary : colors.textMuted }
          ]}>
            {tab.label}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );

  const renderInteractionItem = (item: Interaction) => (
    <View
      key={item.id}
      style={[styles.interactionCard, { backgroundColor: colors.surface }]}
    >
      <View style={styles.interactionHeader}>
        <View style={[styles.typeIcon, { backgroundColor: getTypeColor(item.type) + '20' }]}>
          <Ionicons name={getTypeIcon(item.type) as any} size={18} color={getTypeColor(item.type)} />
        </View>
        <View style={styles.interactionInfo}>
          <Text style={[styles.interactionType, { color: getTypeColor(item.type) }]}>
            {item.type.replace(/_/g, ' ').toUpperCase()}
          </Text>
          <Text style={[styles.interactionTime, { color: colors.textMuted }]}>
            {new Date(item.timestamp).toLocaleString()}
          </Text>
        </View>
        {item.model && (
          <View style={[styles.modelBadge, { backgroundColor: colors.primary + '20' }]}>
            <Text style={[styles.modelText, { color: colors.primary }]}>{item.model}</Text>
          </View>
        )}
      </View>
      <View style={[styles.promptSection, { backgroundColor: colors.background }]}>
        <Text style={[styles.promptLabel, { color: colors.textMuted }]}>Prompt:</Text>
        <Text style={[styles.promptText, { color: colors.text }]} numberOfLines={3}>
          {item.prompt}
        </Text>
      </View>
      {item.response && (
        <View style={[styles.responseSection, { backgroundColor: colors.surfaceAlt }]}>
          <Text style={[styles.responseLabel, { color: colors.textMuted }]}>Response:</Text>
          <Text style={[styles.responseText, { color: colors.text }]} numberOfLines={4}>
            {item.response}
          </Text>
        </View>
      )}
    </View>
  );

  const renderAllTab = () => (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
      {interactions.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="chatbubbles-outline" size={64} color={colors.textMuted} />
          <Text style={[styles.emptyTitle, { color: colors.text }]}>No Interactions Yet</Text>
          <Text style={[styles.emptySubtitle, { color: colors.textMuted }]}>
            Start using AI features to see your interaction history
          </Text>
        </View>
      ) : (
        filteredInteractions.map(renderInteractionItem)
      )}
    </ScrollView>
  );

  const renderByTypeTab = () => {
    const types = [...new Set(interactions.map(i => i.type))];
    
    return (
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {/* Type Filters */}
        <View style={styles.typeFilters}>
          <TouchableOpacity
            style={[
              styles.typeChip,
              { backgroundColor: colors.surface },
              !selectedType && { backgroundColor: colors.primary + '20', borderColor: colors.primary, borderWidth: 1 }
            ]}
            onPress={() => setSelectedType(null)}
          >
            <Text style={[
              styles.typeChipText,
              { color: !selectedType ? colors.primary : colors.text }
            ]}>All</Text>
          </TouchableOpacity>
          {types.map(type => (
            <TouchableOpacity
              key={type}
              style={[
                styles.typeChip,
                { backgroundColor: getTypeColor(type) + '20' },
                selectedType === type && { borderColor: getTypeColor(type), borderWidth: 1 }
              ]}
              onPress={() => setSelectedType(selectedType === type ? null : type)}
            >
              <Ionicons name={getTypeIcon(type) as any} size={14} color={getTypeColor(type)} />
              <Text style={[styles.typeChipText, { color: getTypeColor(type) }]}>
                {type.replace(/_/g, ' ')}
              </Text>
              <Text style={[styles.typeCount, { color: getTypeColor(type) }]}>
                {interactions.filter(i => i.type === type).length}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Filtered Interactions */}
        {filteredInteractions.map(renderInteractionItem)}
      </ScrollView>
    );
  };

  const renderInsightsTab = () => (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
      <View style={[styles.insightsHeader, { backgroundColor: colors.primary + '15' }]}>
        <Ionicons name="bulb" size={32} color={colors.primary} />
        <Text style={[styles.insightsTitle, { color: colors.text }]}>Learning Insights</Text>
        <Text style={[styles.insightsSubtitle, { color: colors.textMuted }]}>
          Personalized based on your AI interactions
        </Text>
      </View>

      {insights.length === 0 ? (
        <View style={[styles.insightCard, { backgroundColor: colors.surface }]}>
          <Text style={[styles.insightText, { color: colors.textMuted }]}>
            No insights available yet. Keep interacting with AI features to generate personalized insights!
          </Text>
        </View>
      ) : (
        insights.map((insight, i) => (
          <View key={i} style={[styles.insightCard, { backgroundColor: colors.surface }]}>
            <View style={styles.insightHeader}>
              <Ionicons name="star" size={16} color="#F59E0B" />
              <Text style={[styles.insightType, { color: colors.primary }]}>
                {insight.type || 'General'}
              </Text>
            </View>
            <Text style={[styles.insightText, { color: colors.text }]}>
              {insight.message || insight.content || JSON.stringify(insight)}
            </Text>
          </View>
        ))
      )}
    </ScrollView>
  );

  const renderStatsTab = () => (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
      {/* Summary Card */}
      <View style={[styles.statsCard, { backgroundColor: colors.primary + '15' }]}>
        <Text style={[styles.statsTitle, { color: colors.text }]}>Your AI Usage</Text>
        <View style={styles.statsGrid}>
          <View style={styles.statItem}>
            <Text style={[styles.statValue, { color: colors.primary }]}>
              {stats?.total_interactions || interactions.length}
            </Text>
            <Text style={[styles.statLabel, { color: colors.textMuted }]}>Total</Text>
          </View>
          <View style={styles.statItem}>
            <Text style={[styles.statValue, { color: '#10B981' }]}>
              {Object.keys(stats?.by_type || {}).length || new Set(interactions.map(i => i.type)).size}
            </Text>
            <Text style={[styles.statLabel, { color: colors.textMuted }]}>Types</Text>
          </View>
          <View style={styles.statItem}>
            <Text style={[styles.statValue, { color: '#8B5CF6' }]}>
              {profile?.total_sessions || 1}
            </Text>
            <Text style={[styles.statLabel, { color: colors.textMuted }]}>Sessions</Text>
          </View>
        </View>
      </View>

      {/* By Type Breakdown */}
      {stats?.by_type && Object.keys(stats.by_type).length > 0 && (
        <View style={[styles.breakdownCard, { backgroundColor: colors.surface }]}>
          <Text style={[styles.breakdownTitle, { color: colors.text }]}>By Type</Text>
          {Object.entries(stats.by_type).map(([type, count]: [string, any]) => (
            <View key={type} style={styles.breakdownRow}>
              <View style={[styles.breakdownIcon, { backgroundColor: getTypeColor(type) + '20' }]}>
                <Ionicons name={getTypeIcon(type) as any} size={16} color={getTypeColor(type)} />
              </View>
              <Text style={[styles.breakdownLabel, { color: colors.text }]}>
                {type.replace(/_/g, ' ')}
              </Text>
              <Text style={[styles.breakdownValue, { color: colors.primary }]}>
                {count}
              </Text>
            </View>
          ))}
        </View>
      )}

      {/* Learning Profile */}
      {profile && (
        <View style={[styles.profileCard, { backgroundColor: colors.surface }]}>
          <Text style={[styles.profileTitle, { color: colors.text }]}>Learning Profile</Text>
          <View style={styles.profileRow}>
            <Text style={[styles.profileLabel, { color: colors.textMuted }]}>Primary Language</Text>
            <Text style={[styles.profileValue, { color: colors.primary }]}>
              {profile.primary_language || 'Python'}
            </Text>
          </View>
          <View style={styles.profileRow}>
            <Text style={[styles.profileLabel, { color: colors.textMuted }]}>Skill Level</Text>
            <Text style={[styles.profileValue, { color: colors.primary }]}>
              {profile.skill_level || 'Intermediate'}
            </Text>
          </View>
          <View style={styles.profileRow}>
            <Text style={[styles.profileLabel, { color: colors.textMuted }]}>Active Days</Text>
            <Text style={[styles.profileValue, { color: colors.primary }]}>
              {profile.active_days || 1}
            </Text>
          </View>
        </View>
      )}
    </ScrollView>
  );

  const renderContent = () => {
    if (loading) {
      return (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={[styles.loadingText, { color: colors.textMuted }]}>
            Loading AI interactions...
          </Text>
        </View>
      );
    }

    switch (activeTab) {
      case 'all': return renderAllTab();
      case 'by_type': return renderByTypeTab();
      case 'insights': return renderInsightsTab();
      case 'stats': return renderStatsTab();
      default: return null;
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent>
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        {/* Header */}
        <View style={[styles.header, { backgroundColor: colors.surface, borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={onClose} style={styles.closeButton}>
            <Ionicons name="close" size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerCenter}>
            <Text style={[styles.headerTitle, { color: colors.text }]}>🤖 AI Interactions Log</Text>
            <Text style={[styles.headerSubtitle, { color: colors.textMuted }]}>
              Direct-to-Jeeves Learning Data
            </Text>
          </View>
          <TouchableOpacity onPress={fetchData} style={styles.refreshButton}>
            <Ionicons name="refresh" size={20} color={colors.primary} />
          </TouchableOpacity>
        </View>

        {/* Tabs */}
        {renderTabs()}

        {/* Content */}
        {renderContent()}
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    marginTop: 40,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
  },
  closeButton: {
    padding: 4,
  },
  headerCenter: {
    alignItems: 'center',
    flex: 1,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  headerSubtitle: {
    fontSize: 12,
  },
  refreshButton: {
    padding: 8,
  },
  tabBar: {
    flexDirection: 'row',
    paddingHorizontal: 8,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.1)',
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    gap: 6,
  },
  tabText: {
    fontSize: 12,
    fontWeight: '600',
  },
  content: {
    flex: 1,
    padding: 16,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 12,
  },
  loadingText: {
    fontSize: 14,
  },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 60,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '700',
    marginTop: 16,
  },
  emptySubtitle: {
    fontSize: 14,
    marginTop: 8,
    textAlign: 'center',
  },
  interactionCard: {
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  interactionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  typeIcon: {
    width: 36,
    height: 36,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },
  interactionInfo: {
    flex: 1,
    marginLeft: 12,
  },
  interactionType: {
    fontSize: 12,
    fontWeight: '700',
  },
  interactionTime: {
    fontSize: 11,
    marginTop: 2,
  },
  modelBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  modelText: {
    fontSize: 10,
    fontWeight: '600',
  },
  promptSection: {
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
  },
  promptLabel: {
    fontSize: 10,
    fontWeight: '600',
    marginBottom: 4,
    textTransform: 'uppercase',
  },
  promptText: {
    fontSize: 13,
    lineHeight: 18,
  },
  responseSection: {
    borderRadius: 8,
    padding: 12,
  },
  responseLabel: {
    fontSize: 10,
    fontWeight: '600',
    marginBottom: 4,
    textTransform: 'uppercase',
  },
  responseText: {
    fontSize: 13,
    lineHeight: 18,
  },
  typeFilters: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 16,
  },
  typeChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 20,
    gap: 6,
  },
  typeChipText: {
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  typeCount: {
    fontSize: 10,
    fontWeight: '700',
  },
  insightsHeader: {
    borderRadius: 16,
    padding: 24,
    alignItems: 'center',
    marginBottom: 20,
  },
  insightsTitle: {
    fontSize: 20,
    fontWeight: '800',
    marginTop: 12,
  },
  insightsSubtitle: {
    fontSize: 14,
    marginTop: 4,
  },
  insightCard: {
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  insightHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },
  insightType: {
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  insightText: {
    fontSize: 14,
    lineHeight: 20,
  },
  statsCard: {
    borderRadius: 16,
    padding: 20,
    marginBottom: 16,
  },
  statsTitle: {
    fontSize: 18,
    fontWeight: '700',
    textAlign: 'center',
    marginBottom: 16,
  },
  statsGrid: {
    flexDirection: 'row',
    justifyContent: 'space-around',
  },
  statItem: {
    alignItems: 'center',
  },
  statValue: {
    fontSize: 28,
    fontWeight: '800',
  },
  statLabel: {
    fontSize: 12,
    marginTop: 4,
  },
  breakdownCard: {
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },
  breakdownTitle: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 12,
  },
  breakdownRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
  },
  breakdownIcon: {
    width: 32,
    height: 32,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
  },
  breakdownLabel: {
    flex: 1,
    fontSize: 14,
    marginLeft: 12,
    textTransform: 'capitalize',
  },
  breakdownValue: {
    fontSize: 16,
    fontWeight: '700',
  },
  profileCard: {
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },
  profileTitle: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 12,
  },
  profileRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.1)',
  },
  profileLabel: {
    fontSize: 14,
  },
  profileValue: {
    fontSize: 14,
    fontWeight: '600',
  },
});

export default AIInteractionsLogModal;
