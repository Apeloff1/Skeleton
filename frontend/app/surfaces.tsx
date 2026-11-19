/**
 * Whole-studio index of every public route installed in this build.
 * Parameterised owners such as /gate/:stage stay with their own screens.
 */
import React, { useEffect, useMemo, useState } from 'react';
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
import { useLocalSearchParams, useRouter } from 'expo-router';
import {
  INSTALLED_SURFACES,
  ORPHAN_SURFACES,
  SurfacePillar,
  surfacesFor,
} from '../src/product/surfaceAtlas';

type PillarFilter = SurfacePillar | 'all';

const FILTERS: readonly { id: PillarFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'create', label: 'Create' },
  { id: 'play', label: 'Play' },
  { id: 'learn', label: 'Learn' },
  { id: 'operate', label: 'Operate' },
];

function firstQuery(value: string | string[] | undefined): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) {
    const found = value.find((item) => typeof item === 'string' && item.length > 0);
    return found ?? '';
  }
  return '';
}

export default function InstalledSurfacesRoute() {
  const router = useRouter();
  const params = useLocalSearchParams<{ q?: string | string[] }>();
  const { width } = useWindowDimensions();
  const wide = width >= 760;
  const [query, setQuery] = useState(() => firstQuery(params.q));
  const [pillar, setPillar] = useState<PillarFilter>('all');

  useEffect(() => {
    const incoming = firstQuery(params.q);
    if (incoming) setQuery(incoming);
  }, [params.q]);

  const visible = useMemo(() => {
    const pool = pillar === 'all' ? INSTALLED_SURFACES : surfacesFor(pillar);
    const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (terms.length === 0) return pool;
    return pool.filter((surface) => {
      const haystack = `${surface.title} ${surface.description} ${surface.href} ${surface.pillar}`.toLowerCase();
      return terms.every((term) => haystack.includes(term));
    });
  }, [pillar, query]);

  const showEverySurface = () => {
    setQuery('');
    setPillar('all');
  };

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView
        contentContainerStyle={[styles.page, wide && styles.pageWide]}
        keyboardShouldPersistTaps="handled"
      >
        <TouchableOpacity
          accessibilityRole="button"
          accessibilityLabel="Back to the product shell"
          onPress={() => router.push('/product' as never)}
          style={styles.backButton}
        >
          <Text style={styles.backText}>← Product</Text>
        </TouchableOpacity>

        <View style={styles.hero}>
          <Text style={styles.eyebrow}>WHOLE STUDIO</Text>
          <Text style={styles.title}>Every installed surface</Text>
          <Text style={styles.subtitle}>
            {INSTALLED_SURFACES.length} routes ship with this build. {ORPHAN_SURFACES.length} sit outside the pillar cards.
          </Text>
        </View>

        <View style={styles.searchPanel}>
          <Text style={styles.searchTitle}>Search the install</Text>
          <TextInput
            accessibilityLabel="Search installed surfaces"
            accessibilityHint="Filters titles, descriptions, routes and pillars"
            value={query}
            onChangeText={setQuery}
            placeholder="Try “forge”, “academy”, “/playable”…"
            placeholderTextColor="#667085"
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="search"
            style={styles.searchInput}
          />
          <View style={styles.chips}>
            {FILTERS.map((filter) => {
              const selected = pillar === filter.id;
              return (
                <TouchableOpacity
                  key={filter.id}
                  accessibilityRole="button"
                  accessibilityLabel={`Show ${filter.label} surfaces`}
                  accessibilityState={{ selected }}
                  onPress={() => setPillar(filter.id)}
                  style={[styles.chip, selected && styles.chipSelected]}
                >
                  <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{filter.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
          <Text style={styles.resultSummary}>
            {visible.length} {visible.length === 1 ? 'surface' : 'surfaces'}
          </Text>
        </View>

        {visible.length === 0 ? (
          <View style={styles.emptyState} accessibilityLiveRegion="polite">
            <Text style={styles.emptyTitle}>No surfaces found</Text>
            <Text style={styles.emptySubtitle}>
              Try a route, a pillar, or a shorter name. The index lists every public screen in this build.
            </Text>
            <TouchableOpacity
              accessibilityRole="button"
              accessibilityLabel="Show every surface"
              onPress={showEverySurface}
              style={styles.emptyButton}
            >
              <Text style={styles.emptyButtonText}>Show every surface</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={styles.grid}>
            {visible.map((surface) => (
              <TouchableOpacity
                key={surface.id}
                accessibilityRole="button"
                accessibilityLabel={`Open ${surface.title}`}
                accessibilityHint={surface.href}
                onPress={() => router.push(surface.href as never)}
                style={[styles.card, wide ? styles.cardWide : styles.cardNarrow]}
              >
                <View style={styles.cardTop}>
                  <Text style={styles.cardTitle}>{surface.title}</Text>
                  <Text style={styles.pillarTag}>{surface.pillar.toUpperCase()}</Text>
                </View>
                <Text style={styles.cardDescription}>{surface.description}</Text>
                <Text style={styles.href}>{surface.href}</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#080A0F' },
  page: { paddingHorizontal: 18, paddingTop: 18, paddingBottom: 48, gap: 18 },
  pageWide: { width: '100%', maxWidth: 1180, alignSelf: 'center', paddingHorizontal: 28 },
  backButton: { minHeight: 44, alignSelf: 'flex-start', justifyContent: 'center', paddingHorizontal: 4 },
  backText: { color: '#A9B2FF', fontSize: 13, fontWeight: '800' },
  hero: { borderWidth: 1, borderColor: '#232838', borderRadius: 24, padding: 22, backgroundColor: '#0D111A' },
  eyebrow: { color: '#8B9AFF', fontSize: 11, fontWeight: '800', letterSpacing: 2.2, marginBottom: 8 },
  title: { color: '#F8FAFC', fontSize: 30, lineHeight: 35, fontWeight: '800' },
  subtitle: { color: '#AAB3C5', fontSize: 14, lineHeight: 21, marginTop: 10 },
  searchPanel: { borderRadius: 18, borderWidth: 1, borderColor: '#202737', backgroundColor: '#0F141F', padding: 16, gap: 12 },
  searchTitle: { color: '#F1F5F9', fontSize: 16, fontWeight: '800' },
  searchInput: {
    minHeight: 48,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#30384C',
    backgroundColor: '#0A0F18',
    color: '#F8FAFC',
    paddingHorizontal: 14,
    paddingVertical: 11,
    fontSize: 14,
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    minHeight: 40,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#323B56',
    backgroundColor: '#141C2A',
    paddingHorizontal: 14,
    justifyContent: 'center',
  },
  chipSelected: { backgroundColor: '#20284A', borderColor: '#3C5C86' },
  chipText: { color: '#C5CCE0', fontSize: 12, fontWeight: '800' },
  chipTextSelected: { color: '#F8FAFC' },
  resultSummary: { color: '#69758A', fontSize: 10, lineHeight: 15 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  card: {
    minHeight: 112,
    backgroundColor: '#0F141F',
    borderWidth: 1,
    borderColor: '#202737',
    borderRadius: 18,
    padding: 16,
    justifyContent: 'center',
  },
  cardNarrow: { width: '100%' },
  cardWide: { width: '49%', flexGrow: 1 },
  cardTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  cardTitle: { color: '#F8FAFC', fontSize: 16, fontWeight: '800', flex: 1 },
  pillarTag: { color: '#A9B2FF', fontSize: 10, fontWeight: '900', letterSpacing: 0.8 },
  cardDescription: { color: '#9AA6BA', fontSize: 12, lineHeight: 18, marginTop: 7 },
  href: { color: '#69758A', fontSize: 11, marginTop: 10, fontFamily: 'monospace' },
  emptyState: { alignItems: 'center', borderRadius: 18, borderWidth: 1, borderColor: '#2D3548', backgroundColor: '#0D121D', padding: 24 },
  emptyTitle: { color: '#F1F5F9', fontSize: 18, fontWeight: '800', textAlign: 'center' },
  emptySubtitle: { color: '#8490A5', fontSize: 12, lineHeight: 18, marginTop: 6, textAlign: 'center', maxWidth: 420 },
  emptyButton: { minHeight: 44, borderRadius: 999, backgroundColor: '#20284A', justifyContent: 'center', paddingHorizontal: 18, marginTop: 16 },
  emptyButtonText: { color: '#DDE2FF', fontSize: 12, fontWeight: '800' },
});
