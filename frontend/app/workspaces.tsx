import { useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { AppHeader, Chip, FeatureCard, Screen, SearchBar, SectionHeader } from '../components/UI';
import theme from '../theme/tokens';
import { WORKSPACES, WORKSPACE_COUNTS, WorkspaceStatus } from '../src/workspaces/registry';
import { LEGACY_ACTIVE, LEGACY_COVERAGE, LEGACY_TOTAL } from '../src/workspaces/legacyMap';

type Filter = 'all' | WorkspaceStatus;

const STATUS_LABEL: Record<WorkspaceStatus, string> = {
  live: 'Live',
  evolving: 'Evolving',
  migration: 'Migration',
};

export default function WorkspacesScreen() {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<Filter>('all');

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return WORKSPACES.filter(workspace => {
      if (filter !== 'all' && workspace.status !== filter) return false;
      if (!q) return true;
      return [
        workspace.title,
        workspace.subtitle,
        ...workspace.legacySources,
        ...workspace.evolvedCapabilities,
      ].some(value => value.toLowerCase().includes(q));
    });
  }, [filter, query]);

  return (
    <Screen edges={['top', 'left', 'right']}>
      <AppHeader
        title="Workspaces"
        subtitle="One app. Every system absorbed and evolved."
        onBack={() => router.back()}
      />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.hero}>
          <View style={styles.heroIcon}>
            <Ionicons name="grid" size={24} color={theme.colors.primaryHover} />
          </View>
          <View style={styles.heroBody}>
            <Text style={styles.heroTitle}>Unified product map</Text>
            <Text style={styles.heroText}>
              Older interfaces are being redesigned into capability domains instead of preserved as disconnected apps.
            </Text>
          </View>
        </View>

        <View style={styles.statsRow}>
          <Stat label="Live" value={WORKSPACE_COUNTS.live} />
          <Stat label="Evolving" value={WORKSPACE_COUNTS.evolving} />
          <Stat label="Migration" value={WORKSPACE_COUNTS.migration} />
        </View>

        <View style={styles.coverageCard}>
          <View style={styles.coverageTop}>
            <View>
              <Text style={styles.coverageEyebrow}>LEGACY ABSORPTION</Text>
              <Text style={styles.coverageTitle}>{LEGACY_COVERAGE}% capability coverage</Text>
            </View>
            <Text style={styles.coverageCount}>{LEGACY_ACTIVE}/{LEGACY_TOTAL}</Text>
          </View>
          <View style={styles.track}>
            <View style={[styles.fill, { width: `${LEGACY_COVERAGE}%` }]} />
          </View>
          <Text style={styles.coverageText}>
            Coverage counts capabilities that are already absorbed or actively evolving. Queued and retired behavior stays explicit in the migration ledger.
          </Text>
        </View>

        <SearchBar
          value={query}
          onChangeText={setQuery}
          placeholder="Search old interfaces or new capabilities"
        />

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}>
          {(['all', 'live', 'evolving', 'migration'] as const).map(value => (
            <Chip
              key={value}
              label={value === 'all' ? 'All' : STATUS_LABEL[value]}
              selected={filter === value}
              onPress={() => setFilter(value)}
            />
          ))}
        </ScrollView>

        <SectionHeader
          title="Capability Domains"
          subtitle={`${visible.length} visible · canonical routes only`}
        />

        <View style={styles.grid}>
          {visible.map(workspace => (
            <FeatureCard
              key={workspace.id}
              title={workspace.title}
              subtitle={workspace.subtitle}
              icon={workspace.icon}
              color={workspace.accent}
              badge={STATUS_LABEL[workspace.status]}
              onPress={() => router.push(workspace.route as any)}
            />
          ))}
        </View>

        <SectionHeader title="Migration Oversight" subtitle="Track every legacy capability to a canonical destination" />
        <FeatureCard
          title="Legacy Absorption Map"
          subtitle={`${LEGACY_TOTAL} capabilities tracked across ${WORKSPACES.length} canonical workspaces`}
          icon="git-merge"
          color={theme.colors.primaryHover}
          badge={`${LEGACY_COVERAGE}% covered`}
          onPress={() => router.push('/migration-map' as any)}
        />

        <SectionHeader title="Migration Contract" />
        <View style={styles.contract}>
          <ContractRow icon="git-merge" text="Old code is mined for behavior and intent, not copied blindly." />
          <ContractRow icon="color-wand" text="Each surface is rebuilt against the current design system and navigation model." />
          <ContractRow icon="layers" text="Duplicate tools collapse into shared primitives, stores and services." />
          <ContractRow icon="shield-checkmark" text="Live, evolving and migration states remain explicit until functionality is real." />
        </View>
      </ScrollView>
    </Screen>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function ContractRow({ icon, text }: { icon: string; text: string }) {
  return (
    <View style={styles.contractRow}>
      <View style={styles.contractIcon}>
        <Ionicons name={icon as any} size={16} color={theme.colors.primaryHover} />
      </View>
      <Text style={styles.contractText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: theme.spacing.base, paddingBottom: 80, gap: theme.spacing.md },
  hero: {
    flexDirection: 'row',
    gap: theme.spacing.md,
    padding: theme.spacing.base,
    borderRadius: theme.radii.xl,
    backgroundColor: theme.colors.primarySoft,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  heroIcon: {
    width: 48,
    height: 48,
    borderRadius: theme.radii.lg,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: theme.colors.surfaceAlt,
  },
  heroBody: { flex: 1 },
  heroTitle: { ...theme.typography.h3, color: theme.colors.text },
  heroText: { ...theme.typography.body, color: theme.colors.textMuted, marginTop: 4 },
  statsRow: { flexDirection: 'row', gap: theme.spacing.sm },
  stat: {
    flex: 1,
    minHeight: 74,
    borderRadius: theme.radii.lg,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  statValue: { ...theme.typography.h2, color: theme.colors.text },
  statLabel: { ...theme.typography.caption, color: theme.colors.textMuted, marginTop: 2 },
  coverageCard: {
    padding: theme.spacing.base,
    borderRadius: theme.radii.xl,
    borderWidth: 1,
    borderColor: `${theme.colors.primary}55`,
    backgroundColor: theme.colors.surface,
  },
  coverageTop: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', gap: theme.spacing.md },
  coverageEyebrow: { ...theme.typography.micro, color: theme.colors.primaryHover },
  coverageTitle: { ...theme.typography.h3, color: theme.colors.text, marginTop: 3 },
  coverageCount: { ...theme.typography.monoSm, color: theme.colors.textMuted },
  track: {
    height: 7,
    borderRadius: theme.radii.full,
    overflow: 'hidden',
    backgroundColor: theme.colors.surfaceAlt,
    marginTop: theme.spacing.md,
  },
  fill: { height: '100%', borderRadius: theme.radii.full, backgroundColor: theme.colors.primaryHover },
  coverageText: { ...theme.typography.caption, color: theme.colors.textMuted, marginTop: theme.spacing.sm },
  filters: { gap: theme.spacing.sm, paddingVertical: 2 },
  grid: { gap: theme.spacing.sm },
  contract: {
    borderRadius: theme.radii.xl,
    padding: theme.spacing.base,
    gap: theme.spacing.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  contractRow: { flexDirection: 'row', gap: theme.spacing.md, alignItems: 'flex-start' },
  contractIcon: {
    width: 32,
    height: 32,
    borderRadius: theme.radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: theme.colors.primarySoft,
  },
  contractText: { ...theme.typography.body, color: theme.colors.textMuted, flex: 1, paddingTop: 5 },
});
