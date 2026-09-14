import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { AppHeader, FeatureCard, Screen, SectionHeader } from '../components/UI';
import theme from '../theme/tokens';
import { WORKSPACES, WorkspaceDefinition } from '../src/workspaces/registry';

type OperatorStage = {
  title: string;
  description: string;
  icon: string;
  color: string;
};

const OPERATOR_STAGES: readonly OperatorStage[] = [
  {
    title: 'Observe',
    description: 'Read the current world, task, runtime and evidence before proposing change.',
    icon: 'eye',
    color: theme.colors.info,
  },
  {
    title: 'Route',
    description: 'Select capabilities and models by requirements, budgets, privacy and measured reliability.',
    icon: 'git-branch',
    color: theme.colors.primaryHover,
  },
  {
    title: 'Experiment',
    description: 'Run candidate work in bounded live sessions with cancellation, budgets and structured evidence.',
    icon: 'flask',
    color: theme.colors.warning,
  },
  {
    title: 'Evaluate',
    description: 'Compare the candidate against explicit metrics instead of trusting a model or component self-report.',
    icon: 'analytics',
    color: theme.colors.success,
  },
  {
    title: 'Adopt',
    description: 'Promote useful evolution atomically; hold higher-risk mutation for explicit approval and rollback.',
    icon: 'checkmark-done-circle',
    color: theme.colors.success,
  },
];

const STATUS_COPY = {
  live: 'Live capability',
  evolving: 'Actively evolving',
  migration: 'Migration boundary',
} as const;

export default function JeevesControlScreen() {
  const router = useRouter();
  const jeeves = WORKSPACES.find(workspace => workspace.id === 'jeeves');
  const managed = WORKSPACES.filter(workspace => workspace.id !== 'jeeves');

  return (
    <Screen edges={['top', 'left', 'right']}>
      <AppHeader
        title="Jeeves Operator"
        subtitle="Control · reason · route · evaluate · adopt"
        onBack={() => router.back()}
      />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.hero}>
          <View style={styles.heroGlyph}>
            <Ionicons name="sparkles" size={28} color={theme.colors.primaryHover} />
          </View>
          <View style={styles.heroBody}>
            <Text style={styles.eyebrow}>CANONICAL OPERATOR LAYER</Text>
            <Text style={styles.heroTitle}>Jeeves controls the app; it is not another isolated app.</Text>
            <Text style={styles.heroText}>
              The old assistant, stock analyst, model switcher and agent experiments are being collapsed into one bounded operator over shared capabilities, memory, evidence and project state.
            </Text>
          </View>
        </View>

        <View style={styles.guardrailGrid}>
          <Guardrail icon="speedometer" title="Bounded" text="Priority admission, queue limits, cancellation and execution budgets." />
          <Guardrail icon="finger-print" title="Typed authority" text="Capabilities declare mutation, approval and evidence requirements." />
          <Guardrail icon="git-compare" title="Measured" text="Model and candidate selection use observed quality, reliability, latency and cost." />
          <Guardrail icon="return-up-back" title="Reversible" text="World mutations carry revision guards and generated inverse patches." />
        </View>

        <SectionHeader
          title="Operator Cycle"
          subtitle="Evolve first. Mutate only when measured benefit clears the higher bar."
        />
        <View style={styles.stageList}>
          {OPERATOR_STAGES.map((stage, index) => (
            <View key={stage.title} style={styles.stageRow}>
              <View style={[styles.stageIndex, { borderColor: `${stage.color}66`, backgroundColor: `${stage.color}16` }]}>
                <Ionicons name={stage.icon as any} size={17} color={stage.color} />
              </View>
              <View style={styles.stageBody}>
                <View style={styles.stageTitleRow}>
                  <Text style={styles.stageNumber}>{String(index + 1).padStart(2, '0')}</Text>
                  <Text style={styles.stageTitle}>{stage.title}</Text>
                </View>
                <Text style={styles.stageDescription}>{stage.description}</Text>
              </View>
            </View>
          ))}
        </View>

        <SectionHeader
          title="Capability Domains"
          subtitle="Jeeves routes into canonical workspaces instead of recreating their interfaces."
        />
        <View style={styles.workspaceList}>
          {managed.map(workspace => (
            <WorkspaceCard key={workspace.id} workspace={workspace} onOpen={() => router.push(workspace.route as any)} />
          ))}
        </View>

        <SectionHeader title="Legacy Jeeves" subtitle="Preserved as specialist surfaces while capability migration continues" />
        <FeatureCard
          title="Research & Analysis Hub"
          subtitle="Open the existing Jeeves research, source and historical market-analysis surface."
          icon="search"
          color={theme.colors.info}
          badge="Legacy specialist"
          onPress={() => router.push('/jeeves-hub' as any)}
        />

        <View style={styles.truthCard}>
          <Ionicons name="shield-checkmark" size={20} color={theme.colors.success} />
          <View style={styles.truthBody}>
            <Text style={styles.truthTitle}>Truth boundary</Text>
            <Text style={styles.truthText}>
              This screen does not invent model health, market prices, agent counts or backend status. Runtime telemetry belongs in System Control, and real-time market data stays behind verified provider integrations.
            </Text>
          </View>
        </View>

        {jeeves ? (
          <Text style={styles.sourceFootnote}>
            Absorbing: {jeeves.legacySources.join(' · ')}
          </Text>
        ) : null}
      </ScrollView>
    </Screen>
  );
}

function Guardrail({ icon, title, text }: { icon: string; title: string; text: string }) {
  return (
    <View style={styles.guardrail}>
      <Ionicons name={icon as any} size={18} color={theme.colors.primaryHover} />
      <Text style={styles.guardrailTitle}>{title}</Text>
      <Text style={styles.guardrailText}>{text}</Text>
    </View>
  );
}

function WorkspaceCard({ workspace, onOpen }: { workspace: WorkspaceDefinition; onOpen: () => void }) {
  return (
    <FeatureCard
      title={workspace.title}
      subtitle={workspace.subtitle}
      icon={workspace.icon}
      color={workspace.accent}
      badge={STATUS_COPY[workspace.status]}
      onPress={onOpen}
    />
  );
}

const styles = StyleSheet.create({
  content: { padding: theme.spacing.base, paddingBottom: 96, gap: theme.spacing.md },
  hero: {
    flexDirection: 'row',
    gap: theme.spacing.base,
    padding: theme.spacing.xl,
    borderRadius: theme.radii['2xl'],
    borderWidth: 1,
    borderColor: `${theme.colors.primary}55`,
    backgroundColor: theme.colors.primarySoft,
  },
  heroGlyph: {
    width: 56,
    height: 56,
    borderRadius: theme.radii.xl,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: theme.colors.surfaceAlt,
  },
  heroBody: { flex: 1 },
  eyebrow: { ...theme.typography.micro, color: theme.colors.primaryHover },
  heroTitle: { ...theme.typography.h2, color: theme.colors.text, marginTop: 6 },
  heroText: { ...theme.typography.body, color: theme.colors.textMuted, marginTop: 8 },
  guardrailGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: theme.spacing.sm },
  guardrail: {
    width: '48%',
    flexGrow: 1,
    minHeight: 128,
    padding: theme.spacing.md,
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  guardrailTitle: { ...theme.typography.h4, color: theme.colors.text, marginTop: 8 },
  guardrailText: { ...theme.typography.caption, color: theme.colors.textMuted, marginTop: 5 },
  stageList: {
    borderRadius: theme.radii.xl,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    overflow: 'hidden',
  },
  stageRow: {
    minHeight: 86,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: theme.spacing.md,
    padding: theme.spacing.base,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.colors.border,
  },
  stageIndex: {
    width: 40,
    height: 40,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stageBody: { flex: 1 },
  stageTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  stageNumber: { ...theme.typography.monoSm, color: theme.colors.textDim },
  stageTitle: { ...theme.typography.h4, color: theme.colors.text },
  stageDescription: { ...theme.typography.body, color: theme.colors.textMuted, marginTop: 5 },
  workspaceList: { gap: theme.spacing.sm },
  truthCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: theme.spacing.md,
    padding: theme.spacing.base,
    borderRadius: theme.radii.xl,
    borderWidth: 1,
    borderColor: `${theme.colors.success}44`,
    backgroundColor: `${theme.colors.success}0D`,
  },
  truthBody: { flex: 1 },
  truthTitle: { ...theme.typography.h4, color: theme.colors.text },
  truthText: { ...theme.typography.body, color: theme.colors.textMuted, marginTop: 4 },
  sourceFootnote: { ...theme.typography.caption, color: theme.colors.textDim, textAlign: 'center', marginTop: 4 },
});
