export type ProductPillar = 'create' | 'play' | 'learn' | 'operate';

export type ProductAction = {
  id: string;
  title: string;
  description: string;
  operation: string;
  href?: string;
  legacyHref?: string;
};

export type ProductCapability = {
  id: string;
  title: string;
  description: string;
  pillar: ProductPillar;
  href: string;
  backendSurface?: string;
  experimental?: boolean;
  actions: readonly ProductAction[];
};

const capabilityHref = (id: string) => `/capability?id=${encodeURIComponent(id)}`;

/** Canonical user-facing capability map. */
export const PRODUCT_CAPABILITIES: readonly ProductCapability[] = [
  {
    id: 'studio',
    title: 'Studio',
    description: 'Describe, design, build, test and publish a playable project.',
    pillar: 'create',
    href: capabilityHref('studio'),
    backendSurface: '/api/gameforge-studio',
    actions: [
      { id: 'new-project', title: 'New project', description: 'Start from a prompt, brief or template.', operation: 'project.create', legacyHref: '/ai-game-generator' },
      { id: 'build', title: 'Build', description: 'Compile a project into a runnable artifact.', operation: 'build.submit', legacyHref: '/apk-build' },
      { id: 'inspect', title: 'Inspect pipeline', description: 'Review build stages and generated artifacts.', operation: 'pipeline.inspect', legacyHref: '/ai-pipeline' },
      { id: 'native-homebrew', title: 'Native homebrew', description: 'Generate original console and PC source archives with explicit rights approval.', operation: 'dragon.native.sources', href: '/dragon-native-production' },
      { id: 'route-world', title: 'Multi-path world explorer', description: 'Play and build original worlds with public transport, weather, secrets, long detours, free roaming, magical and space routes.', operation: 'dragon.routes.world', href: '/dragon-route-world' },
      { id: 'maze-forge', title: 'Constructive maze builder', description: 'Create genuinely finishable original mazes with scenic circuits, doublebacks, dead-end discoveries, climate-safe paths and native C99 source evidence.', operation: 'dragon.routes.maze', href: '/dragon-maze-world' },
      { id: 'route-atlas', title: 'World-scale route atlas', description: 'Play 12 independently certified maze regions with hundreds of rooms, alternate portal routes and full-world scenic expeditions.', operation: 'dragon.routes.atlas', href: '/dragon-route-atlas' },
      { id: 'living-worlds', title: 'Living worlds and postgame', description: 'Build never-ending sandbox and survival worlds, changing labyrinths, multiple realms, consequence-driven endings and persistent postgame exploration.', operation: 'dragon.worlds.living', href: '/dragon-living-world' },
      { id: 'genomic-universe', title: 'Genomic universe forge', description: 'Use 24 actual simulation axes, exact quintillion-plus world addresses, environmental routes and 16-decision independently replayed paths.', operation: 'dragon.worlds.genomic', href: '/dragon-genomic-universe' },
    ],
  },
  {
    id: 'world-forge',
    title: 'World Forge',
    description: 'Construct worlds, scenes, systems, assets and simulation rules.',
    pillar: 'create',
    href: capabilityHref('world-forge'),
    backendSurface: '/api/worldforge',
    actions: [
      { id: 'world', title: 'Create world', description: 'Generate terrain, regions, travel and environment rules.', operation: 'world.create' },
      { id: 'world-routes', title: 'Author route networks', description: 'Compare original multimodal journey graphs, gates, hidden paths, detours, alternate goals and challenge routes.', operation: 'world.routes.author', href: '/dragon-route-world' },
      { id: 'world-mazes', title: 'Design guaranteed mazes', description: 'Play and export certified worlds with every-room recovery, secret detours, scenic routes and optional maze difficulty.', operation: 'world.mazes.guaranteed', href: '/dragon-maze-world' },
      { id: 'world-route-atlas', title: 'Compose regional worlds', description: 'Connect up to 576 independently certified rooms across 12 playable regions with optional shortcuts and scenic full-world paths.', operation: 'world.regions.atlas', href: '/dragon-route-atlas' },
      { id: 'world-lifecycle', title: 'Create living and endless worlds', description: 'Change victory rules, world eras, faction consequences, ecology, moving mazes and post-ending open exploration across 32 active original gameplay profiles.', operation: 'world.lifecycle.author', href: '/dragon-living-world' },
      { id: 'world-genome', title: 'Compose genomic world universes', description: 'Control 24 working terrain, climate, resource, faction, narrative and postgame axes and replay exact-addressed large-world journeys.', operation: 'world.genome.author', href: '/dragon-genomic-universe' },
      { id: 'systems', title: 'Author systems', description: 'Compose quests, economy, crafting, NPCs and progression.', operation: 'world.systems.compose' },
      { id: 'assets', title: 'Forge assets', description: 'Generate and organize reusable world assets.', operation: 'asset.forge' },
    ],
  },
  {
    id: 'playables',
    title: 'Play',
    description: 'Launch, inspect and iterate on generated playable builds.',
    pillar: 'play',
    href: capabilityHref('playables'),
    backendSurface: '/api/playable',
    actions: [
      { id: 'launch', title: 'Launch playable', description: 'Start the current generated runtime.', operation: 'playable.launch' },
      { id: 'sessions', title: 'Runtime sessions', description: 'Inspect active and recent game sessions.', operation: 'runtime.sessions' },
      { id: 'progress', title: 'Progression', description: 'Review saves, unlocks, achievements and player state.', operation: 'progress.inspect', legacyHref: '/achievements' },
    ],
  },
  {
    id: 'jeeves',
    title: 'Jeeves',
    description: 'Plan, reason, teach and coordinate build work through one assistant.',
    pillar: 'learn',
    href: capabilityHref('jeeves'),
    backendSurface: '/api/jeeves',
    actions: [
      { id: 'reason', title: 'Reason', description: 'Work through a complex product or engineering problem.', operation: 'jeeves.reason' },
      { id: 'plan', title: 'Plan', description: 'Turn a goal into coordinated executable work.', operation: 'jeeves.plan' },
      { id: 'review', title: 'Review agents', description: 'Inspect delegated work and agent outcomes.', operation: 'agents.review', legacyHref: '/agent-review' },
    ],
  },
  {
    id: 'academy',
    title: 'Academy',
    description: 'Learn game development, programming, languages and mathematics.',
    pillar: 'learn',
    href: capabilityHref('academy'),
    backendSurface: '/api/academy',
    actions: [
      { id: 'continue', title: 'Continue learning', description: 'Resume the current learning path.', operation: 'academy.continue' },
      { id: 'practice', title: 'Practice', description: 'Open adaptive exercises and challenges.', operation: 'academy.practice' },
      { id: 'progress', title: 'Learning progress', description: 'Inspect mastery, streaks and completed work.', operation: 'academy.progress' },
    ],
  },
  {
    id: 'operations',
    title: 'Operations',
    description: 'Observe builds, queues, agents, deployments, safety and runtime health.',
    pillar: 'operate',
    href: capabilityHref('operations'),
    backendSurface: '/api/ops',
    actions: [
      { id: 'agents', title: 'Agents', description: 'Inspect active workers, tasks and health.', operation: 'ops.agents', legacyHref: '/agents' },
      { id: 'runtime', title: 'Runtime health', description: 'Inspect governed queues, policy, audit and resource pressure.', operation: 'ops.runtime', href: '/control-plane' },
      { id: 'deployments', title: 'Deployments', description: 'Review build and deployment state.', operation: 'ops.deployments' },
    ],
  },
  {
    id: 'governance',
    title: 'Governance',
    description: 'Audit consequential actions, moderation decisions and execution policy.',
    pillar: 'operate',
    href: capabilityHref('governance'),
    backendSurface: '/api/governance',
    actions: [
      { id: 'policy', title: 'Execution policy', description: 'Inspect chartered actions, quorum rules and amendments.', operation: 'governance.policy', href: '/control-plane' },
      { id: 'audit', title: 'Audit trail', description: 'Review immutable consequential-operation history.', operation: 'governance.audit', href: '/control-plane' },
      { id: 'safety', title: 'Safety controls', description: 'Review moderation and runtime safety controls.', operation: 'governance.safety', legacyHref: '/anti-cheat' },
    ],
  },
] as const;

export function capabilitiesFor(pillar: ProductPillar): readonly ProductCapability[] {
  return PRODUCT_CAPABILITIES.filter((capability) => capability.pillar === pillar);
}

export function capabilityById(id: string): ProductCapability | undefined {
  return PRODUCT_CAPABILITIES.find((capability) => capability.id === id);
}

export function actionById(capabilityId: string, actionId: string): ProductAction | undefined {
  return capabilityById(capabilityId)?.actions.find((action) => action.id === actionId);
}
