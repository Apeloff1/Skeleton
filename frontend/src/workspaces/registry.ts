export type WorkspaceStatus = 'live' | 'evolving' | 'migration';

export type WorkspaceId =
  | 'jeeves'
  | 'work'
  | 'markets'
  | 'wealth'
  | 'collaboration'
  | 'vault'
  | 'learning'
  | 'studio'
  | 'system';

export type WorkspaceDefinition = {
  id: WorkspaceId;
  title: string;
  subtitle: string;
  icon: string;
  accent: string;
  route: string;
  status: WorkspaceStatus;
  legacySources: readonly string[];
  evolvedCapabilities: readonly string[];
};

/**
 * Canonical product map for absorbing the user's older interfaces into one app.
 *
 * Rules:
 *  - Old projects become capabilities, not separate apps.
 *  - Each capability is redesigned against the current design system.
 *  - Existing mature routes are reused instead of duplicated.
 *  - Migration status is explicit so incomplete ports are never represented as live.
 */
export const WORKSPACES: readonly WorkspaceDefinition[] = [
  {
    id: 'jeeves',
    title: 'Jeeves Operator',
    subtitle: 'Control, reason, route, evaluate and adopt across the whole app',
    icon: 'sparkles',
    accent: '#A78BFA',
    route: '/jeeves-control',
    status: 'evolving',
    legacySources: ['Jeeves desktop assistant', 'stock assistant shell', 'OpenAI/API router experiments'],
    evolvedCapabilities: ['assistant chat', 'voice', 'agent routing', 'memory', 'tool control', 'analysis surfaces', 'measured adoption'],
  },
  {
    id: 'work',
    title: 'Work OS',
    subtitle: 'Time, focus, shifts, breaks, logs and personal output economics',
    icon: 'timer',
    accent: '#22D3EE',
    route: '/workforce',
    status: 'evolving',
    legacySources: ['clock-in/out app', 'worker/admin time tracker', 'hours-vs-profit desktop app'],
    evolvedCapabilities: ['clock in/out', 'break states', 'session ledger', 'focus timer', 'coin economy', 'daily output'],
  },
  {
    id: 'markets',
    title: 'Market Intelligence',
    subtitle: 'Watchlists, evidence, ticks, signals and source-grounded analysis',
    icon: 'trending-up',
    accent: '#34D399',
    route: '/market-intelligence',
    status: 'migration',
    legacySources: ['Jeeves stock assistant', 'RSS market analyzer', 'tick-chart predictor experiments'],
    evolvedCapabilities: ['watchlists', 'source ledger', 'signal journal', 'market snapshots', 'model analysis boundary'],
  },
  {
    id: 'wealth',
    title: 'Wealth & Progress',
    subtitle: 'Hours, value creation, fantasy coins and milestone progression',
    icon: 'diamond',
    accent: '#FBBF24',
    route: '/wealth',
    status: 'evolving',
    legacySources: ['hours-vs-profit Windows app', 'fantasy coin milestones'],
    evolvedCapabilities: ['earned coins', 'value ledger', 'milestones', 'work-to-value ratios', 'progress snapshots'],
  },
  {
    id: 'collaboration',
    title: 'Collaboration',
    subtitle: 'People, tasks, messages, schedules and team execution',
    icon: 'people',
    accent: '#60A5FA',
    route: '/collab',
    status: 'live',
    legacySources: ['worker/admin messaging', 'freelancer scheduling system', 'task status messaging'],
    evolvedCapabilities: ['collaboration', 'group chat', 'scheduling', 'task coordination', 'shared execution'],
  },
  {
    id: 'vault',
    title: 'Vault',
    subtitle: 'Saved knowledge, references, bookmarks and durable project assets',
    icon: 'lock-closed',
    accent: '#F472B6',
    route: '/vault',
    status: 'live',
    legacySources: ['shared bookmark folder', 'shared password-folder concept', 'reference libraries'],
    evolvedCapabilities: ['saved assets', 'references', 'collections', 'storage', 'secure-link boundary'],
  },
  {
    id: 'learning',
    title: 'Learning',
    subtitle: 'Curriculum, classes, reading, quizzes and skill progression',
    icon: 'school',
    accent: '#4ADE80',
    route: '/dashboard',
    status: 'live',
    legacySources: ['learning tools', 'booklets', 'reference material', 'academy experiments'],
    evolvedCapabilities: ['curriculum', 'reading', 'classes', 'quizzes', 'Jeeves tutoring', 'progress'],
  },
  {
    id: 'studio',
    title: 'Creation Studio',
    subtitle: 'Code, apps, games, assets, media and worldbuilding',
    icon: 'construct',
    accent: '#FB7185',
    route: '/gameforge-studio',
    status: 'live',
    legacySources: ['Tamagotchi dinosaur game', 'WordPress tools', 'desktop app builders', 'media generators'],
    evolvedCapabilities: ['game forge', 'code tools', 'asset generation', 'media', 'world forge', 'build export'],
  },
  {
    id: 'system',
    title: 'System Control',
    subtitle: 'Runtime health, agents, builds, telemetry and app control plane',
    icon: 'hardware-chip',
    accent: '#C4B5FD',
    route: '/command-center',
    status: 'live',
    legacySources: ['admin dashboards', 'API switching panels', 'runtime diagnostics'],
    evolvedCapabilities: ['mission control', 'agents', 'telemetry', 'builds', 'safety', 'feature flags', 'diagnostics'],
  },
] as const;

export const workspaceById = (id: WorkspaceId) => WORKSPACES.find(workspace => workspace.id === id);

export const WORKSPACE_COUNTS = WORKSPACES.reduce(
  (acc, workspace) => {
    acc[workspace.status] += 1;
    return acc;
  },
  { live: 0, evolving: 0, migration: 0 } as Record<WorkspaceStatus, number>,
);
