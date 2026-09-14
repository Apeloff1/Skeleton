import { useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { AppHeader, Chip, Screen, SearchBar, SectionHeader } from '../components/UI';
import theme from '../theme/tokens';
import { WORKSPACES, WorkspaceId } from '../src/workspaces/registry';
import {
  LEGACY_ACTIVE,
  LEGACY_CAPABILITIES,
  LEGACY_COUNTS,
  LEGACY_COVERAGE,
  LEGACY_STATE_LABEL,
  LEGACY_TOTAL,
  LegacyMigrationState,
  LegacyRisk,
} from '../src/workspaces/legacyMap';

type Filter = 'all' | LegacyMigrationState;

const STATE_COLOR: Record<LegacyMigrationState, string> = {
  absorbed: theme.colors.success,
  evolving: theme.colors.info,
  queued: theme.colors.warning,
  retired: theme.colors.textDim,
};

const RISK_COLOR: Record<LegacyRisk, string> = {
  low: theme.colors.success,
  medium: theme.colors.warning,
  high: theme.colors.danger,
};

export default function MigrationMapScreen() {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<Filter>('all');

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return LEGACY_CAPABILITIES.filter(item => {
      if (filter !== 'all' && item.state !== filter) return false;
      if (!q) return true;
      return [item.source, item.capability, item.replacement, item.notes, item.destination]
        .some(value => value.toLowerCase().includes(q));
    });
  }, [filter, query]);

  const grouped = useMemo(() => {
    return WORKSPACES.map(workspace => ({
      workspace,
      items: visible.filter(item => item.destination === workspace.id),
    })).filter(group => group.items.length > 0);
  }, [visible]);

  return (
    <Screen edges={['top', 'left', 'right']}>
      <AppHeader
        title="Migration Map"
        subtitle="Legacy capability absorption · explicit state · no silent loss"
        onBack={() => router.back()}
      />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.hero}>
          <View style={styles.coverageRing}>
            <Text style={styles.coverageValue}>{LEGACY_COVERAGE}%</Text>
            <Text style={styles.coverageLabel}>covered</Text>
          </View>
          <View style={styles.heroBody}>
            <Text style={styles.heroTitle}>Capability-level migration ledger</Text>
            <Text style={styles.heroText}>
              {LEGACY_ACTIVE} of {LEGACY_TOTAL} tracked legacy capabilities are absorbed or actively evolving. Queued work stays visible until it has a real destination and implementation.
            </Text>
          </View>
        </View>

        <View style={styles.statsRow}>
          <Stat label="Absorbed" value={LEGACY_COUNTS.absorbed} color={STATE_COLOR.absorbed} />
          <Stat label="Evolving" value={LEGACY_COUNTS.evolving} color={STATE_COLOR.evolving} />
          <Stat label="Queued" value={LEGACY_COUNTS.queued} color={STATE_COLOR.queued} />
          <Stat label="Retired" value={LEGACY_COUNTS.retired} color={STATE_COLOR.retired} />
        </View>

        <SearchBar value={query} onChangeText={setQuery} placeholder="Search legacy capability, source or replacement" />

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}>
          {(['all', 'absorbed', 'evolving', 'queued', 'retired'] as const).map(value => (
            <Chip
              key={value}
              label={value === 'all' ? 'All' : LEGACY_STATE_LABEL[value]}
              selected={filter === value}
              onPress={() => setFilter(value)}
            />
          ))}
        </ScrollView>

        {grouped.map(({ workspace, items }) => (
          <View key={workspace.id} style={styles.group}>
            <SectionHeader
              title={workspace.title}
              subtitle={`${items.length} tracked ${items.length === 1 ? 'capability' : 'capabilities'} · ${workspace.status}`}
            />
            <View style={styles.cardStack}>
              {items.map(item => (
                <View key={item.id} style={styles.card}>
                  <View style={styles.cardTop}>
                    <View style={[styles.iconWrap, { backgroundColor: `${workspace.accent}16`, borderColor: `${workspace.accent}55` }]}>
                      <Ionicons name={workspace.icon as any} size={17} color={workspace.accent} />
                    </View>
                    <View style={styles.cardTitleBody}>
                      <Text style={styles.source}>{item.source}</Text>
                      <Text style={styles.capability}>{item.capability}</Text>
                    </View>
                    <StatePill state={item.state} />
                  </View>

                  <View style={styles.replacementBox}>
                    <Ionicons name="git-merge" size={15} color={theme.colors.primaryHover} />
                    <View style={styles.replacementBody}>
                      <Text style={styles.replacementLabel}>Replacement</Text>
                      <Text style={styles.replacement}>{item.replacement}</Text>
                    </View>
                  </View>

                  <Text style={styles.notes}>{item.notes}</Text>

                  <View style={styles.metaRow}>
                    <Meta label="Destination" value={workspace.id} />
                    <Meta label="Risk" value={item.risk} color={RISK_COLOR[item.risk]} />
                    <Meta label="ID" value={item.id} />
                  </View>
                </View>
              ))}
            </View>
          </View>
        ))}

        {visible.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="search" size={24} color={theme.colors.textDim} />
            <Text style={styles.emptyTitle}>No migration rows match</Text>
            <Text style={styles.emptyText}>Change the filter or search terms to restore the ledger view.</Text>
          </View>
        ) : null}
      </ScrollView>
    </Screen>
  );
}

function StatePill({ state }: { state: LegacyMigrationState }) {
  const color = STATE_COLOR[state];
  return (
    <View style={[styles.statePill, { borderColor: `${color}66`, backgroundColor: `${color}14` }]}>
      <View style={[styles.stateDot, { backgroundColor: color }]} />
      <Text style={[styles.stateText, { color }]}>{LEGACY_STATE_LABEL[state]}</Text>
    </View>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <View style={styles.stat}>
      <Text style={[styles.statValue, { color }]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function Meta({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.meta}>
      <Text style={styles.metaLabel}>{label}</Text>
      <Text numberOfLines={1} style={[styles.metaValue, color ? { color } : null]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: theme.spacing.base, paddingBottom: 96, gap: theme.spacing.md },
  hero: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.base,
    padding: theme.spacing.xl,
    borderRadius: theme.radii['2xl'],
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  coverageRing: {
    width: 86,
    height: 86,
    borderRadius: 43,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: theme.colors.primary,
    backgroundColor: theme.colors.primarySoft,
  },
  coverageValue: { ...theme.typography.h2, color: theme.colors.text },
  coverageLabel: { ...theme.typography.micro, color: theme.colors.textMuted, marginTop: 1 },
  heroBody: { flex: 1 },
  heroTitle: { ...theme.typography.h3, color: theme.colors.text },
  heroText: { ...theme.typography.body, color: theme.colors.textMuted, marginTop: 5 },
  statsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: theme.spacing.sm },
  stat: {
    flexGrow: 1,
    minWidth: '22%',
    minHeight: 72,
    paddingHorizontal: 8,
    borderRadius: theme.radii.lg,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  statValue: { ...theme.typography.h3 },
  statLabel: { ...theme.typography.caption, color: theme.colors.textMuted, marginTop: 2 },
  filters: { gap: theme.spacing.sm, paddingVertical: 2 },
  group: { gap: theme.spacing.sm },
  cardStack: { gap: theme.spacing.sm },
  card: {
    padding: theme.spacing.base,
    borderRadius: theme.radii.xl,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  cardTop: { flexDirection: 'row', alignItems: 'flex-start', gap: theme.spacing.sm },
  iconWrap: {
    width: 38,
    height: 38,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardTitleBody: { flex: 1 },
  source: { ...theme.typography.micro, color: theme.colors.textDim },
  capability: { ...theme.typography.h4, color: theme.colors.text, marginTop: 2 },
  statePill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderWidth: 1,
    borderRadius: theme.radii.full,
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  stateDot: { width: 6, height: 6, borderRadius: 3 },
  stateText: { ...theme.typography.micro },
  replacementBox: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    padding: theme.spacing.sm,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.surfaceAlt,
    marginTop: theme.spacing.md,
  },
  replacementBody: { flex: 1 },
  replacementLabel: { ...theme.typography.micro, color: theme.colors.textDim },
  replacement: { ...theme.typography.body, color: theme.colors.text, marginTop: 1 },
  notes: { ...theme.typography.body, color: theme.colors.textMuted, marginTop: theme.spacing.md },
  metaRow: { flexDirection: 'row', gap: theme.spacing.sm, marginTop: theme.spacing.md },
  meta: { flex: 1, minWidth: 0 },
  metaLabel: { ...theme.typography.micro, color: theme.colors.textDim },
  metaValue: { ...theme.typography.caption, color: theme.colors.textMuted, marginTop: 2 },
  empty: {
    alignItems: 'center',
    padding: theme.spacing.xl,
    borderRadius: theme.radii.xl,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  emptyTitle: { ...theme.typography.h4, color: theme.colors.text, marginTop: 8 },
  emptyText: { ...theme.typography.body, color: theme.colors.textMuted, textAlign: 'center', marginTop: 4 },
});
