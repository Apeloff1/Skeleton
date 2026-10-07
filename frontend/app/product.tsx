import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';

import {
  PRODUCT_CAPABILITIES,
  ProductPillar,
  capabilitiesFor,
} from '../src/product/productCatalog';
import { probeAppHealth } from '../src/product/appHealthClient';
import type { AppHealthSnapshot } from '../src/product/appHealthClient';

const PILLARS: readonly { id: ProductPillar; title: string; subtitle: string }[] = [
  { id: 'create', title: 'Create', subtitle: 'Design, generate and ship worlds and playable projects.' },
  { id: 'play', title: 'Play', subtitle: 'Launch builds, simulations and generated game experiences.' },
  { id: 'learn', title: 'Learn', subtitle: 'Use Jeeves and Academy to reason, practice and improve.' },
  { id: 'operate', title: 'Operate', subtitle: 'Observe agents, builds, policy, audit and runtime health.' },
];

const pillarSearchText = (pillar: ProductPillar) => {
  const definition = PILLARS.find((candidate) => candidate.id === pillar);
  return definition ? `${definition.title} ${definition.subtitle}` : pillar;
};

export default function ProductShellRoute() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const [query, setQuery] = useState('');
  const [health, setHealth] = useState<AppHealthSnapshot | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const normalizedQuery = query.trim().toLowerCase();
  const isWide = width >= 760;

  const refreshHealth = useCallback(async (signal?: AbortSignal) => {
    setHealthLoading(true);
    try {
      const snapshot = await probeAppHealth(2_500, signal);
      if (!signal?.aborted) setHealth(snapshot);
    } finally {
      if (!signal?.aborted) setHealthLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    void refreshHealth(controller?.signal);
    return () => {
      try { controller?.abort(); } catch {}
    };
  }, [refreshHealth]);

  const visibleCapabilities = useMemo(() => {
    if (!normalizedQuery) return PRODUCT_CAPABILITIES;

    const searchTerms = normalizedQuery.split(/\s+/).filter(Boolean);

    return PRODUCT_CAPABILITIES.filter((capability) => {
      const searchable = [
        capability.title,
        capability.description,
        capability.pillar,
        pillarSearchText(capability.pillar),
        capability.backendSurface ?? '',
        ...capability.actions.flatMap((action) => [action.title, action.description, action.operation]),
      ]
        .join(' ')
        .toLowerCase();

      return searchTerms.every((term) => searchable.includes(term));
    });
  }, [normalizedQuery]);

  const visibleIds = useMemo(
    () => new Set(visibleCapabilities.map((capability) => capability.id)),
    [visibleCapabilities],
  );

  const counts = useMemo(
    () => Object.fromEntries(
      PILLARS.map((pillar) => [
        pillar.id,
        capabilitiesFor(pillar.id).filter((capability) => visibleIds.has(capability.id)).length,
      ]),
    ) as Record<ProductPillar, number>,
    [visibleIds],
  );

  const visiblePillars = useMemo(
    () => PILLARS.filter((pillar) => counts[pillar.id] > 0),
    [counts],
  );

  const clearSearch = () => setQuery('');

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView
        contentContainerStyle={[styles.page, isWide && styles.pageWide]}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.hero}>
          <Text style={styles.eyebrow}>SKELETON</Text>
          <Text style={styles.title}>One product. Four pillars.</Text>
          <Text style={styles.subtitle}>
            The consolidated runtime is surfaced as Create, Play, Learn and Operate while mined systems remain behind stable product contracts.
          </Text>
          <View style={styles.metricsRow}>
            <Metric label={normalizedQuery ? 'Matches' : 'Capabilities'} value={String(visibleCapabilities.length)} />
            <Metric label="Pillars" value={String(normalizedQuery ? visiblePillars.length : PILLARS.length)} />
            <Metric
              label="Runtime"
              value={
                healthLoading && !health
                  ? 'Checking'
                  : health?.ok
                    ? 'Healthy'
                    : health?.contractSource && health.contractSource !== 'runtime'
                      ? 'Partial'
                      : health
                        ? 'Degraded'
                        : 'Unknown'
              }
            />
            <Metric
              label="Actions"
              value={health?.product?.available ? `${health.product.ready_actions}/${health.product.canonical_actions}` : '—'}
            />
          </View>
        </View>

        <View style={styles.healthPanel}>
          <View style={styles.healthHeader}>
            <View style={styles.healthCopy}>
              <Text style={styles.healthTitle}>Application runtime</Text>
              <Text style={styles.healthSubtitle}>
                {health?.application
                  ? `${health.application.name} v${health.application.version} · ${health.contractSource} contract · assembled runtime health`
                  : 'Canonical application runtime health from the assembly contract.'}
              </Text>
            </View>
            <TouchableOpacity
              accessibilityRole="button"
              accessibilityLabel="Refresh application runtime health"
              disabled={healthLoading}
              onPress={() => void refreshHealth()}
              style={[styles.healthRefresh, healthLoading && styles.healthRefreshDisabled]}
              activeOpacity={0.78}
            >
              <Text style={styles.healthRefreshText}>{healthLoading ? 'Checking…' : 'Refresh'}</Text>
            </TouchableOpacity>
          </View>
          <View style={styles.healthServices}>
            {(health?.services.length ? health.services : [
              { name: 'backend' as const },
              { name: 'skeleton' as const },
            ]).map((item) => {
              const name = item.name;
              const service = 'ok' in item ? item : health?.services.find((candidate) => candidate.name === name);
              const state = healthLoading && !service ? 'checking' : service?.ok ? 'healthy' : service ? 'degraded' : 'unknown';
              const label = name === 'backend'
                ? 'Application API'
                : name === 'skeleton'
                  ? 'Skeleton engine'
                  : 'Mongo state';
              return (
                <View key={name} style={styles.healthService}>
                  <View style={styles.healthServiceTop}>
                    <Text style={styles.healthServiceName}>{label}</Text>
                    <Text style={[
                      styles.healthState,
                      state === 'healthy' ? styles.healthGood : state === 'degraded' ? styles.healthBad : styles.healthMuted,
                    ]}>
                      {state.toUpperCase()}
                    </Text>
                  </View>
                  <Text style={styles.healthDetail}>
                    {service
                      ? `${service.status ?? '—'} · ${service.latencyMs} ms · ${service.detail}`
                      : 'Awaiting first probe'}
                  </Text>
                </View>
              );
            })}
          </View>
        </View>

        <View style={styles.searchPanel}>
          <View style={styles.searchHeader}>
            <View style={styles.searchCopy}>
              <Text style={styles.searchTitle}>Find a capability</Text>
              <Text style={styles.searchSubtitle}>
                Search names, pillars, descriptions, operations and backend surfaces.
              </Text>
            </View>
            {normalizedQuery ? (
              <TouchableOpacity
                accessibilityRole="button"
                accessibilityLabel="Clear capability search"
                onPress={clearSearch}
                hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                style={styles.clearButton}
              >
                <Text style={styles.clearButtonText}>Clear</Text>
              </TouchableOpacity>
            ) : null}
          </View>
          <TextInput
            accessibilityLabel="Search capabilities"
            accessibilityHint="Filters capabilities across all four product pillars"
            value={query}
            onChangeText={setQuery}
            placeholder="Try “build”, “agents”, “academy”…"
            placeholderTextColor="#667085"
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="search"
            style={styles.searchInput}
          />
          <Text style={styles.resultSummary} accessibilityLiveRegion="polite">
            {normalizedQuery
              ? `${visibleCapabilities.length} ${visibleCapabilities.length === 1 ? 'match' : 'matches'} for “${query.trim()}”`
              : `${PRODUCT_CAPABILITIES.length} capabilities available`}
          </Text>
        </View>

        {visiblePillars.map((pillar) => (
          <View key={pillar.id} style={styles.section}>
            <View style={styles.sectionHeader}>
              <View style={styles.sectionCopy}>
                <Text style={styles.sectionTitle}>{pillar.title}</Text>
                <Text style={styles.sectionSubtitle}>{pillar.subtitle}</Text>
              </View>
              <Text style={styles.count} accessibilityLabel={`${counts[pillar.id]} capabilities`}>
                {counts[pillar.id]}
              </Text>
            </View>
            <View style={styles.grid}>
              {capabilitiesFor(pillar.id)
                .filter((capability) => visibleIds.has(capability.id))
                .map((capability) => (
                  <TouchableOpacity
                    key={capability.id}
                    accessibilityRole="button"
                    accessibilityLabel={`${capability.title}${capability.experimental ? ', lab' : ''}`}
                    accessibilityHint={`Open ${capability.title}. ${capability.description}`}
                    style={[styles.card, isWide ? styles.cardWide : styles.cardNarrow]}
                    activeOpacity={0.78}
                    onPress={() => router.push(capability.href as never)}
                  >
                    <View style={styles.cardTop}>
                      <Text style={styles.cardTitle}>{capability.title}</Text>
                      {capability.experimental ? <Text style={styles.badge}>LAB</Text> : null}
                    </View>
                    <Text style={styles.cardDescription}>{capability.description}</Text>
                    <Text style={styles.surface}>{capability.backendSurface ?? 'local runtime'}</Text>
                  </TouchableOpacity>
                ))}
            </View>
          </View>
        ))}

        {normalizedQuery && visibleCapabilities.length === 0 ? (
          <View style={styles.emptyState} accessibilityLiveRegion="polite">
            <Text style={styles.emptyTitle}>No capabilities found</Text>
            <Text style={styles.emptySubtitle}>
              Try a broader term, a feature name, an operation, or a backend surface.
            </Text>
            <TouchableOpacity
              accessibilityRole="button"
              accessibilityLabel="Clear search and show all capabilities"
              onPress={clearSearch}
              style={styles.emptyButton}
              activeOpacity={0.78}
            >
              <Text style={styles.emptyButtonText}>Show all capabilities</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        <TouchableOpacity
          accessibilityRole="button"
          accessibilityLabel="Open full legacy hub"
          accessibilityHint="Opens accumulated tools that have not yet been folded into the four product pillars"
          style={styles.legacyButton}
          onPress={() => router.push('/hub' as never)}
          activeOpacity={0.78}
        >
          <Text style={styles.legacyTitle}>Open full legacy hub</Text>
          <Text style={styles.legacySubtitle}>All accumulated tools remain available while they are progressively folded behind the product pillars.</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#080A0F' },
  page: { paddingHorizontal: 18, paddingTop: 22, paddingBottom: 48, gap: 22 },
  pageWide: { width: '100%', maxWidth: 1180, alignSelf: 'center', paddingHorizontal: 28 },
  hero: { borderWidth: 1, borderColor: '#232838', borderRadius: 24, padding: 22, backgroundColor: '#0D111A' },
  eyebrow: { color: '#8B9AFF', fontSize: 11, fontWeight: '800', letterSpacing: 2.2, marginBottom: 8 },
  title: { color: '#F8FAFC', fontSize: 30, lineHeight: 35, fontWeight: '800' },
  subtitle: { color: '#AAB3C5', fontSize: 14, lineHeight: 21, marginTop: 10 },
  metricsRow: { flexDirection: 'row', gap: 8, marginTop: 20 },
  metric: { flex: 1, borderRadius: 14, backgroundColor: '#121827', paddingHorizontal: 12, paddingVertical: 12 },
  metricValue: { color: '#F8FAFC', fontSize: 16, fontWeight: '800' },
  metricLabel: { color: '#748096', fontSize: 10, marginTop: 3, textTransform: 'uppercase', letterSpacing: 0.7 },
  healthPanel: { borderRadius: 18, borderWidth: 1, borderColor: '#202737', backgroundColor: '#0F141F', padding: 16, gap: 12 },
  healthHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  healthCopy: { flex: 1 },
  healthTitle: { color: '#F1F5F9', fontSize: 16, fontWeight: '800' },
  healthSubtitle: { color: '#8490A5', fontSize: 11, lineHeight: 17, marginTop: 3 },
  healthRefresh: { minHeight: 38, justifyContent: 'center', borderRadius: 10, backgroundColor: '#20284A', paddingHorizontal: 12 },
  healthRefreshDisabled: { opacity: 0.55 },
  healthRefreshText: { color: '#DDE2FF', fontSize: 11, fontWeight: '800' },
  healthServices: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  healthService: { flex: 1, minWidth: 180, borderRadius: 12, backgroundColor: '#0A0F18', borderWidth: 1, borderColor: '#202737', padding: 12 },
  healthServiceTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  healthServiceName: { color: '#DDE3EE', fontSize: 12, fontWeight: '800' },
  healthState: { fontSize: 9, fontWeight: '900', letterSpacing: 0.7 },
  healthGood: { color: '#7FD9A1' },
  healthBad: { color: '#F08A9A' },
  healthMuted: { color: '#8A96AA' },
  healthDetail: { color: '#69758A', fontSize: 10, lineHeight: 15, marginTop: 6, fontFamily: 'monospace' },
  searchPanel: { borderRadius: 18, borderWidth: 1, borderColor: '#202737', backgroundColor: '#0F141F', padding: 16 },
  searchHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  searchCopy: { flex: 1 },
  searchTitle: { color: '#F1F5F9', fontSize: 16, fontWeight: '800' },
  searchSubtitle: { color: '#8490A5', fontSize: 11, lineHeight: 17, marginTop: 3 },
  clearButton: { minHeight: 36, justifyContent: 'center', paddingHorizontal: 8 },
  clearButtonText: { color: '#A9B2FF', fontSize: 12, fontWeight: '800' },
  searchInput: {
    minHeight: 48,
    marginTop: 14,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#30384C',
    backgroundColor: '#0A0F18',
    color: '#F8FAFC',
    paddingHorizontal: 14,
    paddingVertical: 11,
    fontSize: 14,
  },
  resultSummary: { color: '#69758A', fontSize: 10, lineHeight: 15, marginTop: 8 },
  section: { gap: 12 },
  sectionHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  sectionCopy: { flex: 1 },
  sectionTitle: { color: '#F1F5F9', fontSize: 21, fontWeight: '800' },
  sectionSubtitle: { color: '#8490A5', fontSize: 12, lineHeight: 18, marginTop: 3 },
  count: { minWidth: 32, textAlign: 'center', color: '#A9B2FF', backgroundColor: '#171C31', borderRadius: 10, paddingVertical: 7, overflow: 'hidden', fontWeight: '800' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  card: { backgroundColor: '#0F141F', borderWidth: 1, borderColor: '#202737', borderRadius: 18, padding: 16 },
  cardNarrow: { width: '100%' },
  cardWide: { width: '49%', flexGrow: 1 },
  cardTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  cardTitle: { color: '#F8FAFC', fontSize: 16, fontWeight: '800' },
  badge: { color: '#FBBF24', fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  cardDescription: { color: '#9AA6BA', fontSize: 12, lineHeight: 18, marginTop: 7 },
  surface: { color: '#69758A', fontSize: 10, marginTop: 12, fontFamily: 'monospace' },
  emptyState: { alignItems: 'center', borderRadius: 18, borderWidth: 1, borderColor: '#2D3548', backgroundColor: '#0D121D', padding: 24 },
  emptyTitle: { color: '#F1F5F9', fontSize: 18, fontWeight: '800', textAlign: 'center' },
  emptySubtitle: { color: '#8490A5', fontSize: 12, lineHeight: 18, marginTop: 6, textAlign: 'center', maxWidth: 420 },
  emptyButton: { minHeight: 44, borderRadius: 999, backgroundColor: '#20284A', justifyContent: 'center', paddingHorizontal: 18, marginTop: 16 },
  emptyButtonText: { color: '#DDE2FF', fontSize: 12, fontWeight: '800' },
  legacyButton: { borderRadius: 18, borderWidth: 1, borderColor: '#30374A', padding: 16, backgroundColor: '#111622' },
  legacyTitle: { color: '#DDE3EE', fontSize: 14, fontWeight: '800' },
  legacySubtitle: { color: '#7E899B', fontSize: 11, lineHeight: 17, marginTop: 5 },
});
