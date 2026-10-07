// ============================================================================
// CODEDOCK v9.0.0 - AI FEATURE SUGGESTIONS MODAL
// Self-evolving AI-powered feature discovery
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
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

interface AISuggestionsModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  context?: {
    languages?: string[];
    features_used?: string[];
    skill_level?: string;
  };
}

interface FeatureSuggestion {
  id: string | number;
  name: string;
  description: string;
  category: string;
  impact: string;
  implementation_difficulty: string;
}

export const AISuggestionsModal: React.FC<AISuggestionsModalProps> = ({
  visible,
  onClose,
  colors,
  context = {},
}) => {
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<FeatureSuggestion[]>([]);
  const [sotaAnalysis, setSotaAnalysis] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<'suggestions' | 'sota'>('suggestions');
  const [sotaLoading, setSotaLoading] = useState(false);

  const backendUrl = process.env.EXPO_PUBLIC_BACKEND_URL || '';

  const fetchSuggestions = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${backendUrl}/api/ai/hub/suggest-features`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(context),
      });
      const data = await res.json();
      setSuggestions(data.suggestions || []);
    } catch (error) {
      console.error('Suggestion fetch error:', error);
      // Fallback suggestions
      setSuggestions([
        {
          id: '1',
          name: 'AI Code Refactoring',
          description: 'Automatic code improvement suggestions',
          category: 'productivity',
          impact: 'high',
          implementation_difficulty: 'medium',
        },
        {
          id: '2',
          name: 'Smart Test Generator',
          description: 'Generate test cases automatically',
          category: 'quality',
          impact: 'high',
          implementation_difficulty: 'high',
        },
      ]);
    }
    setLoading(false);
  }, [backendUrl, context]);

  const fetchSotaAnalysis = useCallback(async (domain: string) => {
    setSotaLoading(true);
    try {
      const res = await fetch(`${backendUrl}/api/ai/hub/query-sota`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain }),
      });
      const data = await res.json();
      setSotaAnalysis(data.analysis || 'No analysis available');
    } catch (error) {
      console.error('SOTA fetch error:', error);
      setSotaAnalysis('Failed to fetch state-of-the-art analysis');
    }
    setSotaLoading(false);
  }, [backendUrl]);

  useEffect(() => {
    if (visible) {
      fetchSuggestions();
    }
  }, [visible, fetchSuggestions]);

  const getImpactColor = (impact: string) => {
    switch (impact?.toLowerCase()) {
      case 'critical': return '#EF4444';
      case 'high': return '#F59E0B';
      case 'medium': return '#10B981';
      default: return '#6B7280';
    }
  };

  const getDifficultyColor = (diff: string) => {
    switch (diff?.toLowerCase()) {
      case 'high': return '#EF4444';
      case 'medium': return '#F59E0B';
      case 'low': return '#10B981';
      default: return '#6B7280';
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
            <Ionicons name="sparkles" size={24} color={colors.primary} />
            <Text style={[styles.title, { color: colors.text }]}>AI Feature Lab</Text>
          </View>
          <TouchableOpacity onPress={fetchSuggestions} style={styles.refreshButton}>
            <Ionicons name="refresh" size={20} color={colors.primary} />
          </TouchableOpacity>
        </View>

        {/* Tab Bar */}
        <View style={[styles.tabBar, { backgroundColor: colors.surfaceAlt }]}>
          <TouchableOpacity
            style={[styles.tab, activeView === 'suggestions' && { backgroundColor: colors.primary + '30' }]}
            onPress={() => setActiveView('suggestions')}
          >
            <Ionicons name="bulb" size={18} color={activeView === 'suggestions' ? colors.primary : colors.textMuted} />
            <Text style={[styles.tabText, { color: activeView === 'suggestions' ? colors.primary : colors.textMuted }]}>
              Suggestions
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.tab, activeView === 'sota' && { backgroundColor: colors.primary + '30' }]}
            onPress={() => { setActiveView('sota'); if (!sotaAnalysis) fetchSotaAnalysis('compiler optimization'); }}
          >
            <Ionicons name="rocket" size={18} color={activeView === 'sota' ? colors.primary : colors.textMuted} />
            <Text style={[styles.tabText, { color: activeView === 'sota' ? colors.primary : colors.textMuted }]}>
              State of Art
            </Text>
          </TouchableOpacity>
        </View>

        <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
          {activeView === 'suggestions' ? (
            <>
              {loading ? (
                <View style={styles.loadingContainer}>
                  <ActivityIndicator size="large" color={colors.primary} />
                  <Text style={[styles.loadingText, { color: colors.textMuted }]}>
                    AI is analyzing your usage patterns...
                  </Text>
                </View>
              ) : (
                <>
                  <View style={[styles.infoCard, { backgroundColor: colors.primary + '15' }]}>
                    <Ionicons name="information-circle" size={20} color={colors.primary} />
                    <Text style={[styles.infoText, { color: colors.text }]}>
                      These suggestions are generated by GPT-4o based on your coding patterns
                    </Text>
                  </View>

                  {suggestions.map((suggestion, index) => (
                    <View key={suggestion.id || index} style={[styles.suggestionCard, { backgroundColor: colors.surface }]}>
                      <View style={styles.suggestionHeader}>
                        <View style={[styles.suggestionIcon, { backgroundColor: colors.primary + '20' }]}>
                          <Ionicons name="bulb" size={24} color={colors.primary} />
                        </View>
                        <View style={styles.suggestionInfo}>
                          <Text style={[styles.suggestionName, { color: colors.text }]}>{suggestion.name}</Text>
                          <Text style={[styles.suggestionCategory, { color: colors.textMuted }]}>
                            {suggestion.category}
                          </Text>
                        </View>
                      </View>

                      <Text style={[styles.suggestionDesc, { color: colors.textMuted }]}>
                        {suggestion.description}
                      </Text>

                      <View style={styles.badgeRow}>
                        <View style={[styles.badge, { backgroundColor: getImpactColor(suggestion.impact) + '20' }]}>
                          <Ionicons name="trending-up" size={12} color={getImpactColor(suggestion.impact)} />
                          <Text style={[styles.badgeText, { color: getImpactColor(suggestion.impact) }]}>
                            {suggestion.impact} impact
                          </Text>
                        </View>
                        <View style={[styles.badge, { backgroundColor: getDifficultyColor(suggestion.implementation_difficulty) + '20' }]}>
                          <Ionicons name="construct" size={12} color={getDifficultyColor(suggestion.implementation_difficulty)} />
                          <Text style={[styles.badgeText, { color: getDifficultyColor(suggestion.implementation_difficulty) }]}>
                            {suggestion.implementation_difficulty}
                          </Text>
                        </View>
                      </View>

                      <TouchableOpacity style={[styles.implementButton, { backgroundColor: colors.primary }]}>
                        <Ionicons name="add-circle" size={18} color="#FFF" />
                        <Text style={styles.implementText}>Request Implementation</Text>
                      </TouchableOpacity>
                    </View>
                  ))}
                </>
              )}
            </>
          ) : (
            <>
              <View style={[styles.sotaHeader, { backgroundColor: colors.surface }]}>
                <Text style={[styles.sotaTitle, { color: colors.text }]}>State of the Art Analysis</Text>
                <Text style={[styles.sotaSubtitle, { color: colors.textMuted }]}>
                  Latest developments in compiler technology
                </Text>
              </View>

              <View style={styles.domainButtons}>
                {['compiler optimization', 'language design', 'IDE features', 'AI coding'].map(domain => (
                  <TouchableOpacity
                    key={domain}
                    style={[styles.domainButton, { backgroundColor: colors.surface }]}
                    onPress={() => fetchSotaAnalysis(domain)}
                  >
                    <Text style={[styles.domainText, { color: colors.text }]}>{domain}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              {sotaLoading ? (
                <View style={styles.loadingContainer}>
                  <ActivityIndicator size="large" color={colors.primary} />
                  <Text style={[styles.loadingText, { color: colors.textMuted }]}>
                    Querying AI for latest developments...
                  </Text>
                </View>
              ) : sotaAnalysis ? (
                <View style={[styles.analysisCard, { backgroundColor: colors.surface }]}>
                  <Text style={[styles.analysisText, { color: colors.text }]}>{sotaAnalysis}</Text>
                </View>
              ) : null}
            </>
          )}
        </ScrollView>
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
  refreshButton: {
    padding: 8,
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
    fontSize: 13,
    fontWeight: '600',
  },
  content: {
    flex: 1,
    paddingHorizontal: 16,
  },
  loadingContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 60,
  },
  loadingText: {
    marginTop: 16,
    fontSize: 14,
    textAlign: 'center',
  },
  infoCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    borderRadius: 12,
    marginVertical: 12,
    gap: 10,
  },
  infoText: {
    flex: 1,
    fontSize: 13,
    lineHeight: 18,
  },
  suggestionCard: {
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
  },
  suggestionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  suggestionIcon: {
    width: 48,
    height: 48,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  suggestionInfo: {
    flex: 1,
    marginLeft: 12,
  },
  suggestionName: {
    fontSize: 16,
    fontWeight: '600',
  },
  suggestionCategory: {
    fontSize: 12,
    marginTop: 2,
    textTransform: 'capitalize',
  },
  suggestionDesc: {
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 12,
  },
  badgeRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 14,
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 8,
    gap: 4,
  },
  badgeText: {
    fontSize: 11,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  implementButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: 10,
    gap: 8,
  },
  implementText: {
    color: '#FFF',
    fontSize: 14,
    fontWeight: '600',
  },
  sotaHeader: {
    padding: 20,
    borderRadius: 12,
    marginVertical: 12,
    alignItems: 'center',
  },
  sotaTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  sotaSubtitle: {
    fontSize: 13,
    marginTop: 4,
  },
  domainButtons: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 16,
  },
  domainButton: {
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 10,
  },
  domainText: {
    fontSize: 12,
    fontWeight: '500',
    textTransform: 'capitalize',
  },
  analysisCard: {
    padding: 16,
    borderRadius: 12,
    marginBottom: 20,
  },
  analysisText: {
    fontSize: 14,
    lineHeight: 22,
  },
});

export default AISuggestionsModal;
