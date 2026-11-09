/**
 * /capabilities — Galaxy Studio Capability Systems browser.
 *
 * Surfaces the 40 generated capability systems (engine + per-capability
 * mutation permutation engine) from GET /api/galaxy-studio/capabilities/catalog.
 *
 * Smoothness: skeleton loading, error + retry, pull-to-refresh, live search,
 * expand/collapse per capability, haptic feedback on expand.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, TextInput,
  StyleSheet, SafeAreaView, Platform, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';

interface Capability {
  id: string;
  title: string;
  subsystems: string[];
  operations: string[];
  permutations: number;
}
interface Category { name: string; count: number; capabilities: Capability[] }
interface Catalog {
  ok: boolean;
  total_capabilities: number;
  total_categories: number;
  operators: string[];
  categories: Category[];
}

const ACCENTS = ['#8B5CF6', '#3B82F6', '#f472b6', '#10B981', '#f59e0b', '#3B82F6', '#A78BFA', '#c084fc'];

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export default function CapabilitiesScreen() {
  const router = useRouter();
  const haptics = useHaptics();
  const [catalog, setCatalog] = React.useState<Catalog | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [query, setQuery] = React.useState('');
  const [expanded, setExpanded] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setError(null);
    const r = await api.get<Catalog>('/api/galaxy-studio/capabilities/catalog');
    if (r.ok && r.data?.ok) {
      setCatalog(r.data);
    } else {
      setError(r.error || `HTTP ${r.status}`);
    }
    setLoading(false);
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const onRefresh = React.useCallback(async () => {
    setLoading(true);
    await load();
  }, [load]);

  const toggle = React.useCallback((id: string) => {
    haptics.selection();
    setExpanded((cur) => (cur === id ? null : id));
  }, [haptics]);

  const filtered = React.useMemo(() => {
    if (!catalog) return [] as Category[];
    const q = query.trim().toLowerCase();
    if (!q) return catalog.categories;
    return catalog.categories
      .map((cat) => ({
        ...cat,
        capabilities: cat.capabilities.filter(
          (c) =>
            c.title.toLowerCase().includes(q) ||
            c.id.includes(q) ||
            c.subsystems.some((s) => s.includes(q)),
        ),
      }))
      .filter((cat) => cat.capabilities.length > 0);
  }, [catalog, query]);

  const totalPerms = React.useMemo(
    () =>
      catalog
        ? catalog.categories.reduce(
            (acc, cat) => acc + cat.capabilities.reduce((a, c) => a + c.permutations, 0),
            0,
          )
        : 0,
    [catalog],
  );

  const visibleCount = filtered.reduce((a, c) => a + c.capabilities.length, 0);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header} testID="capabilities-header">
        <TouchableOpacity testID="capabilities-back" onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backTxt}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Capability Systems</Text>
        <Text style={styles.badge}>{catalog ? catalog.total_capabilities : '—'}</Text>
      </View>

      {catalog ? (
        <View style={styles.statsRow}>
          <Stat testID="stat-systems" label="Systems" value={String(catalog.total_capabilities)} />
          <Stat testID="stat-categories" label="Categories" value={String(catalog.total_categories)} />
          <Stat testID="stat-permutations" label="Permutations" value={fmt(totalPerms)} />
        </View>
      ) : null}

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={{ paddingBottom: 80 }}
        refreshControl={<RefreshControl tintColor="#fff" refreshing={loading && !!catalog} onRefresh={onRefresh} />}
      >
        {/* Loading skeletons */}
        {loading && !catalog ? (
          <View style={{ paddingTop: 8 }}>
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <View key={i} style={styles.skeleton} />
            ))}
          </View>
        ) : null}

        {/* Error + retry */}
        {error && !catalog ? (
          <View style={styles.center}>
            <Text style={styles.errTitle}>Couldn’t load capabilities</Text>
            <Text style={styles.errSub}>{error}</Text>
            <TouchableOpacity style={styles.retryBtn} onPress={onRefresh}>
              <Text style={styles.retryTxt}>Retry</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {/* Empty search */}
        {catalog && visibleCount === 0 ? (
          <View style={styles.center}>
            <Text style={styles.errTitle}>No systems match “{query}”</Text>
          </View>
        ) : null}

        {filtered.map((cat, ci) => (
          <View key={cat.name}>
            <View style={styles.groupHeader}>
              <Text style={[styles.groupName, { color: ACCENTS[ci % ACCENTS.length] }]}>{cat.name}</Text>
              <Text style={styles.groupCount}>{cat.capabilities.length}</Text>
            </View>
            {cat.capabilities.map((cap) => {
              const open = expanded === cap.id;
              const accent = ACCENTS[ci % ACCENTS.length];
              return (
                <View testID={`cap-card-${cap.id}`} key={cap.id} style={[styles.card, { borderColor: accent + '44' }]}>
                  <TouchableOpacity testID={`cap-head-${cap.id}`} style={styles.cardHead} activeOpacity={0.8} onPress={() => toggle(cap.id)}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.capTitle}>{cap.title}</Text>
                      <Text style={styles.capMeta}>
                        {cap.subsystems.length} subsystems · {cap.operations.length} ops · {fmt(cap.permutations)} permutations
                      </Text>
                    </View>
                    <Text style={[styles.chevron, { color: accent }]}>{open ? '−' : '+'}</Text>
                  </TouchableOpacity>
                  {open ? (
                    <View style={styles.cardBody}>
                      <Text style={styles.sectionLabel}>Subsystems</Text>
                      <View style={styles.chipWrap}>
                        {cap.subsystems.map((s) => (
                          <View key={s} style={[styles.chip, { backgroundColor: accent + '22', borderColor: accent + '55' }]}>
                            <Text style={[styles.chipTxt, { color: accent }]}>{s}</Text>
                          </View>
                        ))}
                      </View>
                      <Text style={styles.sectionLabel}>Operations</Text>
                      <View style={styles.chipWrap}>
                        {cap.operations.map((o) => (
                          <View key={o} style={styles.chipMuted}>
                            <Text style={styles.chipMutedTxt}>{o}</Text>
                          </View>
                        ))}
                      </View>
                    </View>
                  ) : null}
                </View>
              );
            })}
          </View>
        ))}
      </ScrollView>

      <View style={styles.bottomBar}>
        <TextInput
          testID="capabilities-search"
          style={styles.search}
          value={query}
          onChangeText={setQuery}
          placeholder="Search systems & subsystems…"
          placeholderTextColor="#64748b"
          autoCapitalize="none"
          autoCorrect={false}
        />
      </View>
    </SafeAreaView>
  );
}

function Stat({ label, value, testID }: { label: string; value: string; testID?: string }) {
  return (
    <View style={styles.stat} testID={testID}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#0A0A0A' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingTop: Platform.OS === 'ios' ? 8 : 16, paddingBottom: 12,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1F1F1F',
  },
  backBtn: { paddingVertical: 6, paddingHorizontal: 10 },
  backTxt: { color: '#93c5fd', fontSize: 15 },
  title: { color: '#fff', fontSize: 18, fontWeight: '700' },
  badge: { color: '#8B5CF6', fontSize: 14, fontWeight: '800' },
  statsRow: { flexDirection: 'row', paddingHorizontal: 12, paddingVertical: 12, gap: 10 },
  stat: { flex: 1, backgroundColor: '#0A0A0A', borderRadius: 12, paddingVertical: 12, alignItems: 'center' },
  statValue: { color: '#fff', fontSize: 18, fontWeight: '800' },
  statLabel: { color: '#64748b', fontSize: 11, marginTop: 2 },
  controls: { paddingHorizontal: 12, paddingBottom: 6 },
  bottomBar: {
    paddingHorizontal: 12, paddingTop: 8, paddingBottom: Platform.OS === 'ios' ? 20 : 10,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#1F1F1F', backgroundColor: '#0A0A0A',
  },
  search: {
    backgroundColor: '#262626', color: '#fff', borderRadius: 8,
    paddingHorizontal: 12, paddingVertical: Platform.OS === 'ios' ? 10 : 6, fontSize: 13,
  },
  scroll: { flex: 1 },
  skeleton: { height: 64, marginHorizontal: 12, marginBottom: 10, borderRadius: 12, backgroundColor: '#0A0A0A' },
  center: { padding: 40, alignItems: 'center' },
  errTitle: { color: '#e2e8f0', fontSize: 15, fontWeight: '600', marginBottom: 6, textAlign: 'center' },
  errSub: { color: '#64748b', fontSize: 12, marginBottom: 16, textAlign: 'center' },
  retryBtn: { backgroundColor: '#8B5CF6', paddingHorizontal: 24, paddingVertical: 10, borderRadius: 10 },
  retryTxt: { color: '#fff', fontWeight: '700', fontSize: 13 },
  groupHeader: {
    flexDirection: 'row', justifyContent: 'space-between',
    paddingHorizontal: 14, paddingTop: 16, paddingBottom: 6,
  },
  groupName: { fontSize: 11, fontWeight: '800', letterSpacing: 1.2, textTransform: 'uppercase' },
  groupCount: { color: '#64748b', fontSize: 11, fontWeight: '600' },
  card: { marginHorizontal: 12, marginBottom: 8, borderRadius: 12, borderWidth: 1, backgroundColor: '#0A0A0A' },
  cardHead: { flexDirection: 'row', alignItems: 'center', padding: 14, gap: 10 },
  capTitle: { color: '#fff', fontSize: 14, fontWeight: '700' },
  capMeta: { color: '#94a3b8', fontSize: 11, marginTop: 4 },
  chevron: { fontSize: 22, fontWeight: '700', width: 24, textAlign: 'center' },
  cardBody: { paddingHorizontal: 14, paddingBottom: 14 },
  sectionLabel: { color: '#64748b', fontSize: 10, fontWeight: '700', letterSpacing: 1, textTransform: 'uppercase', marginTop: 8, marginBottom: 6 },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8, borderWidth: 1 },
  chipTxt: { fontSize: 11, fontWeight: '600' },
  chipMuted: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8, backgroundColor: '#262626' },
  chipMutedTxt: { fontSize: 11, color: '#94a3b8' },
});
