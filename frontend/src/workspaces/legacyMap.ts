import type { WorkspaceId } from './registry';

export type LegacyMigrationState = 'absorbed' | 'evolving' | 'queued' | 'retired';
export type LegacyRisk = 'low' | 'medium' | 'high';

export type LegacyCapability = {
  id: string;
  source: string;
  capability: string;
  destination: WorkspaceId;
  state: LegacyMigrationState;
  risk: LegacyRisk;
  replacement: string;
  notes: string;
};

/**
 * Granular migration ledger for historical interfaces and experiments.
 *
 * This is intentionally capability-oriented. A legacy project can contribute
 * multiple rows because useful behavior is absorbed into shared domains rather
 * than copied as a monolithic application.
 */
export const LEGACY_CAPABILITIES: readonly LegacyCapability[] = [
  {
    id: 'jeeves-chat-shell',
    source: 'Jeeves desktop assistant',
    capability: 'Assistant conversation shell',
    destination: 'jeeves',
    state: 'evolving',
    risk: 'medium',
    replacement: 'Jeeves Operator + specialist research surfaces',
    notes: 'Preserve useful conversation behavior while removing desktop-only routing assumptions.',
  },
  {
    id: 'jeeves-api-switcher',
    source: 'OpenAI/API router experiments',
    capability: 'Model and provider switching',
    destination: 'jeeves',
    state: 'evolving',
    risk: 'high',
    replacement: 'Policy-driven capability router',
    notes: 'Provider choice must become measured routing with privacy, cost and reliability constraints.',
  },
  {
    id: 'jeeves-market-analysis',
    source: 'Jeeves stock assistant',
    capability: 'Market analysis workflow',
    destination: 'markets',
    state: 'evolving',
    risk: 'high',
    replacement: 'Evidence-first Market Intelligence workspace',
    notes: 'Keep analysis separate from verified price feeds and never represent model output as market truth.',
  },
  {
    id: 'jeeves-rss-ingest',
    source: 'RSS market analyzer',
    capability: 'News and source ingestion',
    destination: 'markets',
    state: 'queued',
    risk: 'medium',
    replacement: 'Source ledger with provenance',
    notes: 'Normalize feeds into cited evidence records instead of free-form prompt context.',
  },
  {
    id: 'tick-chart-experiments',
    source: 'Tick-chart predictor experiments',
    capability: 'Historical tick visualization',
    destination: 'markets',
    state: 'queued',
    risk: 'medium',
    replacement: 'Market snapshot and chart primitives',
    notes: 'Visualization can migrate; unsupported prediction claims do not.',
  },
  {
    id: 'clock-core',
    source: 'Clock-in/out app',
    capability: 'Clock in and clock out',
    destination: 'work',
    state: 'evolving',
    risk: 'low',
    replacement: 'Work OS session ledger',
    notes: 'Use one session model for focus, shift, pause and completion events.',
  },
  {
    id: 'clock-breaks',
    source: 'Clock-in/out app',
    capability: 'Break, smoke and food states',
    destination: 'work',
    state: 'queued',
    risk: 'low',
    replacement: 'Typed Work OS pause states',
    notes: 'Collapse arbitrary break buttons into tagged pause intervals.',
  },
  {
    id: 'worker-admin-logs',
    source: 'Worker/admin time tracker',
    capability: 'Admin visibility across worker logs',
    destination: 'collaboration',
    state: 'queued',
    risk: 'high',
    replacement: 'Role-scoped team execution views',
    notes: 'Requires explicit authorization boundaries before broader visibility is enabled.',
  },
  {
    id: 'worker-messaging',
    source: 'Worker/admin messaging',
    capability: 'Task completed, failed and delayed messages',
    destination: 'collaboration',
    state: 'absorbed',
    risk: 'low',
    replacement: 'Collaboration messages and task coordination',
    notes: 'Retained as execution communication rather than a standalone messaging app.',
  },
  {
    id: 'freelancer-scheduling',
    source: 'Freelancer scheduling system',
    capability: 'Scheduling and deadlines',
    destination: 'collaboration',
    state: 'evolving',
    risk: 'medium',
    replacement: 'Shared schedules and deadline-aware tasks',
    notes: 'Deadline alarms should derive from task state rather than ad-hoc timers.',
  },
  {
    id: 'hours-profit',
    source: 'Hours-vs-profit Windows app',
    capability: 'Hours versus value tracking',
    destination: 'wealth',
    state: 'evolving',
    risk: 'low',
    replacement: 'Work-to-value ledger',
    notes: 'Separate measured time from user-entered value while preserving combined progress views.',
  },
  {
    id: 'fantasy-coins',
    source: 'Fantasy coin milestones',
    capability: '200 coins per work hour and milestone progression',
    destination: 'wealth',
    state: 'evolving',
    risk: 'low',
    replacement: 'Configurable progress economy',
    notes: 'Keep the motivational mechanic but make conversion and milestones data-driven.',
  },
  {
    id: 'shared-bookmarks',
    source: 'Shared bookmark folder',
    capability: 'Shared references and bookmarks',
    destination: 'vault',
    state: 'absorbed',
    risk: 'low',
    replacement: 'Vault collections',
    notes: 'Links are durable assets with metadata, tags and provenance.',
  },
  {
    id: 'password-folder',
    source: 'Shared password-folder concept',
    capability: 'Credential storage concept',
    destination: 'vault',
    state: 'retired',
    risk: 'high',
    replacement: 'Secure-link boundary only',
    notes: 'Do not recreate an ad-hoc password manager; integrate trusted secure storage instead.',
  },
  {
    id: 'academy-material',
    source: 'Learning tools and booklets',
    capability: 'Structured reading material',
    destination: 'learning',
    state: 'absorbed',
    risk: 'low',
    replacement: 'Learning curriculum and reading surfaces',
    notes: 'Documents become curriculum units rather than separate viewers.',
  },
  {
    id: 'jeeves-tutoring',
    source: 'Assistant learning experiments',
    capability: 'Contextual tutoring',
    destination: 'learning',
    state: 'evolving',
    risk: 'medium',
    replacement: 'Jeeves tutoring inside Learning',
    notes: 'Tutoring should operate over explicit course context and progress.',
  },
  {
    id: 'dinosaur-game',
    source: 'Tamagotchi dinosaur game',
    capability: 'Creature simulation and lifecycle game',
    destination: 'studio',
    state: 'queued',
    risk: 'low',
    replacement: 'Game Forge project template',
    notes: 'Migrate game rules as reusable simulation primitives, not a one-off screen.',
  },
  {
    id: 'wordpress-tools',
    source: 'WordPress tools',
    capability: 'Site and content tooling',
    destination: 'studio',
    state: 'queued',
    risk: 'medium',
    replacement: 'Creation Studio web project tooling',
    notes: 'Separate generated content, deploy adapters and performance tooling into explicit capabilities.',
  },
  {
    id: 'desktop-builders',
    source: 'Desktop app builders',
    capability: 'GUI application generation',
    destination: 'studio',
    state: 'evolving',
    risk: 'medium',
    replacement: 'Creation Studio application projects',
    notes: 'Retain project intent while moving output generation behind build/export contracts.',
  },
  {
    id: 'admin-dashboards',
    source: 'Admin dashboards',
    capability: 'Operational overview',
    destination: 'system',
    state: 'absorbed',
    risk: 'medium',
    replacement: 'System Control',
    notes: 'Operational state belongs in one control plane rather than feature-specific admin panels.',
  },
  {
    id: 'runtime-diagnostics',
    source: 'Runtime diagnostics',
    capability: 'Health, logs and telemetry',
    destination: 'system',
    state: 'absorbed',
    risk: 'medium',
    replacement: 'System telemetry and diagnostics',
    notes: 'Keep runtime truth sourced from actual telemetry and never from decorative UI state.',
  },
] as const;

export const LEGACY_STATE_LABEL: Record<LegacyMigrationState, string> = {
  absorbed: 'Absorbed',
  evolving: 'Evolving',
  queued: 'Queued',
  retired: 'Retired',
};

export const LEGACY_COUNTS = LEGACY_CAPABILITIES.reduce(
  (acc, capability) => {
    acc[capability.state] += 1;
    return acc;
  },
  { absorbed: 0, evolving: 0, queued: 0, retired: 0 } as Record<LegacyMigrationState, number>,
);

export const LEGACY_TOTAL = LEGACY_CAPABILITIES.length;
export const LEGACY_ACTIVE = LEGACY_COUNTS.absorbed + LEGACY_COUNTS.evolving;
export const LEGACY_COVERAGE = LEGACY_TOTAL === 0 ? 0 : Math.round((LEGACY_ACTIVE / LEGACY_TOTAL) * 100);

export function capabilitiesForWorkspace(workspaceId: WorkspaceId) {
  return LEGACY_CAPABILITIES.filter(capability => capability.destination === workspaceId);
}
