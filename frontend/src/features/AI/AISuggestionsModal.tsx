import { API_BASE as CANONICAL_API_BASE } from '../../utils/apiBase';
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
import * as Clipboard from 'expo-clipboard';

import { apiFetch } from '../../utils/apiController';
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

interface ImplementationPlan {
  status: 'success';
  feature_id: string;
  feature: string;
  implementation_plan: string;
  estimated_complexity: string;
  provider: 'skeleton-engine';
  generated_at: string;
  execution_authorized: false;
  plan_digest: string;
}

const EMPTY_CONTEXT: NonNullable<AISuggestionsModalProps['context']> = Object.freeze({});
const PLAN_DIGEST = /^[a-f0-9]{64}$/;

export const AISuggestionsModal: React.FC<AISuggestionsModalProps> = ({
  visible,
  onClose,
  colors,
  context = EMPTY_CONTEXT,
}) => {
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<FeatureSuggestion[]>([]);
  const [sotaAnalysis, setSotaAnalysis] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<'suggestions' | 'sota'>('suggestions');
  const [sotaLoading, setSotaLoading] = useState(false);
  const [error, setError] = useState('');
  const [implementing, setImplementing] = useState<string | null>(null);
  const [plans, setPlans] = useState<Record<string, ImplementationPlan>>({});

  const backendUrl = CANONICAL_API_BASE || '';

  const fetchSuggestions = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiFetch(`${backendUrl}/api/ai/hub/suggest-features`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(context),
      });
      if (!res.ok) throw new Error(`Feature service returned ${res.status}.`);
      const data = await res.json();
      if (!Array.isArray(data?.suggestions) || data.suggestions.length > 20) throw new Error('Feature service returned an invalid suggestion list.');
      const rows = data.suggestions.filter((value: unknown): value is FeatureSuggestion => {
        if (!value || typeof value !== 'object') return false;
        const row = value as Record<string, unknown>;
        return ['id', 'name', 'description', 'category', 'impact', 'implementation_difficulty'].every(key => ['string', 'number'].includes(typeof row[key]))
          && String(row.id).length <= 128 && String(row.name).length <= 160 && String(row.description).length <= 2000;
      });
      if (rows.length !== data.suggestions.length) throw new Error('Feature service returned malformed suggestions.');
      setSuggestions(rows);
    } catch (failure) {
      setSuggestions([]);
      setError(failure instanceof Error ? failure.message : 'Feature suggestions are unavailable.');
    }
    setLoading(false);
  }, [backendUrl, context]);

  const requestImplementation = useCallback(async (suggestion: FeatureSuggestion) => {
    const id = String(suggestion.id);
    if (implementing) return;
    setImplementing(id); setError('');
    try {
      const body = {
        ...suggestion,
        id,
        impact: suggestion.impact.toLowerCase(),
        implementation_difficulty: suggestion.implementation_difficulty.toLowerCase(),
      };
      const res = await apiFetch(`${backendUrl}/api/ai/hub/auto-implement`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`Implementation planner returned ${res.status}.`);
      const value = await res.json() as Record<string, unknown>;
      if (value.status !== 'success' || value.feature_id !== id || value.feature !== suggestion.name
        || typeof value.implementation_plan !== 'string' || !value.implementation_plan.trim() || value.implementation_plan.length > 100000
        || value.provider !== 'skeleton-engine' || value.execution_authorized !== false
        || typeof value.generated_at !== 'string' || !Number.isFinite(Date.parse(value.generated_at))
        || typeof value.plan_digest !== 'string' || !PLAN_DIGEST.test(value.plan_digest)) {
        throw new Error(value.status === 'offline' ? 'The canonical AI engine is unavailable.' : 'Implementation planner returned an invalid receipt.');
      }
      setPlans(current => ({ ...current, [id]: value as unknown as ImplementationPlan }));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'The implementation plan could not be created.');
    } finally { setImplementing(null); }
  }, [backendUrl, implementing]);

  const fetchSotaAnalysis = useCallback(async (domain: string) => {
    setSotaLoading(true);
    try {
      const res = await apiFetch(`${backendUrl}/api/ai/hub/query-sota`, {
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
          {!!error && <View accessibilityRole="alert" style={styles.errorCard}><Text style={styles.errorText}>{error}</Text></View>}
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
                      Suggestions come through the configured Skeleton engine and remain proposals until you request a governed construction plan.
                    </Text>
                  </View>

                  {!suggestions.length && <View style={[styles.infoCard, { backgroundColor: colors.surface }]}><Text style={[styles.infoText, { color: colors.textMuted }]}>No feature suggestions are currently available. Refresh after the local or configured AI engine is ready.</Text></View>}

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

                      <TouchableOpacity disabled={!!implementing} onPress={() => void requestImplementation(suggestion)} style={[styles.implementButton, { backgroundColor: colors.primary }, !!implementing && { opacity: 0.55 }]}>
                        {implementing === String(suggestion.id) ? <ActivityIndicator color="#FFF" /> : <Ionicons name="add-circle" size={18} color="#FFF" />}
                        <Text style={styles.implementText}>{plans[String(suggestion.id)] ? 'Regenerate implementation plan' : 'Request implementation plan'}</Text>
                      </TouchableOpacity>
                      {plans[String(suggestion.id)] && <View style={styles.planCard} testID={`implementation-plan-${suggestion.id}`}>
                        <View style={styles.planHeader}><Text style={[styles.planTitle, { color: colors.text }]}>Governed construction plan</Text><Text style={[styles.planMeta, { color: colors.textMuted }]}>{plans[String(suggestion.id)].provider} · {plans[String(suggestion.id)].estimated_complexity}</Text></View>
                        <Text selectable style={[styles.analysisText, { color: colors.text }]}>{plans[String(suggestion.id)].implementation_plan}</Text>
                        <Text selectable style={[styles.planDigest, { color: colors.textMuted }]}>SHA-256 {plans[String(suggestion.id)].plan_digest}</Text>
                        <Text style={[styles.planMeta, { color: colors.textMuted }]}>Planning receipt only · execution requires a separately authorized Studio goal.</Text>
                        <TouchableOpacity accessibilityRole="button" onPress={() => void Clipboard.setStringAsync(plans[String(suggestion.id)].implementation_plan)} style={[styles.copyButton, { borderColor: colors.primary }]}><Ionicons name="copy-outline" size={16} color={colors.primary} /><Text style={{ color: colors.primary, fontWeight: '700' }}>Copy plan</Text></TouchableOpacity>
                      </View>}
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
  errorCard: { backgroundColor: '#3f1d1d', borderRadius: 10, padding: 12, marginTop: 12 },
  errorText: { color: '#fca5a5', fontSize: 13, lineHeight: 18 },
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
    paddingVertical: 13,
    paddingHorizontal: 14,
    borderRadius: 10,
    gap: 8,
    minHeight: 44,
    flexWrap: 'wrap',
  },
  implementText: {
    color: '#FFF',
    fontSize: 14,
    fontWeight: '600',
    textAlign: 'center',
    flexShrink: 1,
  },
  planCard: { marginTop: 12, borderRadius: 10, borderWidth: 1, borderColor: '#334155', padding: 14, gap: 10 },
  planHeader: { gap: 3 },
  planTitle: { fontSize: 15, fontWeight: '700' },
  planMeta: { fontSize: 11, lineHeight: 16 },
  planDigest: { fontSize: 10, fontFamily: 'monospace' },
  copyButton: { minHeight: 42, borderWidth: 1, borderRadius: 9, paddingHorizontal: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7 },
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
    gap: 10,
    marginBottom: 16,
  },
  domainButton: {
    paddingHorizontal: 14,
    paddingVertical: 11,
    borderRadius: 10,
    minHeight: 40,
    minWidth: 130,
    flexGrow: 1,
    flexBasis: '45%',
    justifyContent: 'center',
    alignItems: 'center',
  },
  domainText: {
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'capitalize',
    textAlign: 'center',
    flexShrink: 1,
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
