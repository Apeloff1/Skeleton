export type ProductPillar = 'create' | 'play' | 'learn' | 'operate';

type ProductActionBase = {
  id: string;
  title: string;
  description: string;
  legacyHref?: string;
};

/** A direct product link is not an authorized backend command. */
export type ProductAction = ProductActionBase & (
  { operation: string; navigationId?: never; href?: string } |
  { navigationId: string; operation?: never; href: string }
);

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
      { id: 'galaxy-studio', title: 'Galaxy Studio', description: 'Open the unified design, build, snowball and export workspace.', navigationId: 'studio.unified', href: '/studio' },
      { id: 'galaxy-factory', title: 'Galaxy Factory', description: 'Open the original questionnaire and phased design editor.', navigationId: 'studio.factory', href: '/galaxy' },
      { id: 'snowball-flow', title: 'Snowball quality flow', description: 'Select your game in Studio, then inspect and refine its Snowball stages.', navigationId: 'studio.snowball', href: '/studio' },
      { id: 'design-review', title: 'Design and quality review', description: 'Inspect design evidence and improvement proposals.', navigationId: 'studio.design.review', href: '/design-review' },
      { id: 'build', title: 'Build', description: 'Compile a project into a runnable artifact.', operation: 'build.submit', legacyHref: '/apk-build' },
      { id: 'inspect', title: 'Inspect pipeline', description: 'Review build stages and generated artifacts.', operation: 'pipeline.inspect', legacyHref: '/ai-pipeline' },
      { id: 'native-homebrew', title: 'Native homebrew', description: 'Generate original console and PC source archives with explicit rights approval.', navigationId: 'dragon.native.sources', href: '/dragon-native-production' },
      { id: 'route-world', title: 'Multi-path world explorer', description: 'Play and build original worlds with public transport, weather, secrets, long detours, free roaming, magical and space routes.', navigationId: 'dragon.routes.world', href: '/dragon-route-world' },
      { id: 'maze-forge', title: 'Constructive maze builder', description: 'Create genuinely finishable original mazes with scenic circuits, doublebacks, dead-end discoveries, climate-safe paths and native C99 source evidence.', navigationId: 'dragon.routes.maze', href: '/dragon-maze-world' },
      { id: 'route-atlas', title: 'World-scale route atlas', description: 'Play 12 independently certified maze regions with hundreds of rooms, alternate portal routes and full-world scenic expeditions.', navigationId: 'dragon.routes.atlas', href: '/dragon-route-atlas' },
      { id: 'living-worlds', title: 'Living worlds and postgame', description: 'Build never-ending sandbox and survival worlds, changing labyrinths, multiple realms, consequence-driven endings and persistent postgame exploration.', navigationId: 'dragon.worlds.living', href: '/dragon-living-world' },
      { id: 'original-mechanics', title: 'Originals Forge · 18 quintillion programs', description: 'Author and play 32 independently causal original mechanics with 4 levels, 16.7 million distinct rule profiles, earned combinations and 16 replayed journey strategies.', navigationId: 'dragon.worlds.originals', href: '/dragon-originals-forge' },
      { id: 'genomic-universe', title: 'Genomic universe forge', description: 'Use 24 actual simulation axes, exact quintillion-plus world addresses, environmental routes and 16-decision independently replayed paths.', navigationId: 'dragon.worlds.genomic', href: '/dragon-genomic-universe' },
      { id: 'world-codex', title: 'World Codex 128×256', description: 'Shape 128 real geology, society, ecology, chronology, secret route and postgame axes with 256 levels each, actual delayed traversal and console/PC content translation.', navigationId: 'dragon.worlds.codex', href: '/dragon-world-codex' },
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
      { id: 'world-routes', title: 'Author route networks', description: 'Compare original multimodal journey graphs, gates, hidden paths, detours, alternate goals and challenge routes.', navigationId: 'world.routes.author', href: '/dragon-route-world' },
      { id: 'world-mazes', title: 'Design guaranteed mazes', description: 'Play and export certified worlds with every-room recovery, secret detours, scenic routes and optional maze difficulty.', navigationId: 'world.mazes.guaranteed', href: '/dragon-maze-world' },
      { id: 'world-route-atlas', title: 'Compose regional worlds', description: 'Connect up to 576 independently certified rooms across 12 playable regions with optional shortcuts and scenic full-world paths.', navigationId: 'world.regions.atlas', href: '/dragon-route-atlas' },
      { id: 'world-lifecycle', title: 'Create living and endless worlds', description: 'Change victory rules, world eras, faction consequences, ecology, moving mazes and post-ending open exploration across 32 active original gameplay profiles.', navigationId: 'world.lifecycle.author', href: '/dragon-living-world' },
      { id: 'world-originals', title: 'Build original executable game mechanics', description: 'Compose 32 real action/resource/story systems into at least 16.7m distinguishable playable rule profiles and over 18 quintillion parameterized programs.', navigationId: 'world.originals.compose', href: '/dragon-originals-forge' },
      { id: 'world-genome', title: 'Compose genomic world universes', description: 'Control 24 working terrain, climate, resource, faction, narrative and postgame axes and replay exact-addressed large-world journeys.', navigationId: 'world.genome.author', href: '/dragon-genomic-universe' },
      { id: 'world-codex-multiplatform', title: 'Design deep original world systems', description: 'Create 128-axis × 256-level worlds, earned time-gated traversal, multi-era narratives and hardware-aware source projections across all registered native targets.', navigationId: 'world.codex.author', href: '/dragon-world-codex' },
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
      { id: 'open-library', title: 'Playable library', description: 'Choose an existing playable build and open its game controls.', navigationId: 'playables.library', href: '/my-builds' },
      { id: 'learning-simulation', title: 'Emulation and game learning', description: 'Inspect registered emulator targets and replayable game-learning sessions.', navigationId: 'playables.learn', href: '/game-learning' },
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
      { id: 'reason-execute', title: 'Reason with Jeeves', description: 'Execute an admitted reason operation through the canonical Jeeves provider.', operation: 'jeeves.reason' },
      { id: 'reason', title: 'AI chat', description: 'Work through a problem with the configured engine and durable conversation history.', navigationId: 'jeeves.chat.canonical', href: '/jeeves-chat' },
      { id: 'cockpit', title: 'Jeeves cockpit', description: 'Observe Jeeves service availability and diagnose individual services.', navigationId: 'jeeves.cockpit', href: '/jeeves-hub' },
      { id: 'workbench', title: 'Jeeves workbench', description: 'Review and transfer proposed chat work into governed workbench tasks.', navigationId: 'jeeves.workbench', href: '/jeeves-workbench' },
      { id: 'jeeves-settings', title: 'Jeeves settings and persona', description: 'Configure persona, directives, DNA and voice preferences.', navigationId: 'jeeves.settings', href: '/settings/jeeves' },
      { id: 'mirror-room', title: 'Mirror room', description: 'Inspect available review and adversarial simulation surfaces.', navigationId: 'jeeves.mirror', href: '/mirror-room' },
      { id: 'governed-chat', title: 'Conversation workspace', description: 'Use governed attachments, message editing and regeneration with canonical conversation history.', navigationId: 'jeeves.chat.governed', href: '/ai-chat' },
      { id: 'capture-web', title: 'Capture web knowledge', description: 'Authorize a bounded crawl and inspect captured sources.', navigationId: 'jeeves.crawler', href: '/crawler' },
      { id: 'learn-games', title: 'Game learning studio', description: 'Edit, simulate and train original games across registered engine and console targets.', navigationId: 'jeeves.games.learn', href: '/game-learning' },
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
      { id: 'academy-hub', title: 'Mega Academy', description: 'Browse multidisciplinary curricula, lessons and training materials.', navigationId: 'academy.hub', href: '/mega-academy' },
      { id: 'my-classes', title: 'My classes', description: 'Resume enrolled lessons and review progress.', navigationId: 'academy.classes', href: '/my-classes' },
      { id: 'learning-hub', title: 'Learning hub', description: 'Find exercises and tutorials in the learning library.', navigationId: 'academy.learning', href: '/learning-hub' },
      { id: 'academy-settings', title: 'Academy settings', description: 'Adjust speech, accessibility and Academy behavior.', navigationId: 'academy.settings', href: '/settings/academy' },
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
      { id: 'setup', title: 'Setup & readiness', description: 'Check first-install services, model availability and capture readiness.', navigationId: 'operations.setup', href: '/setup' },
      { id: 'operator-settings', title: 'Application settings', description: 'Manage UI appearance, APIs, Academy, Galaxy Studio and Jeeves.', navigationId: 'operations.settings', href: '/settings' },
      { id: 'controller', title: 'Jeeves services', description: 'View live Jeeves service readiness without pretending an offline model is active.', navigationId: 'operations.jeeves.services', href: '/jeeves-hub' },
      { id: 'ai-readiness', title: 'Neural model readiness', description: 'Observe actual registered models and readiness through governed AI chat.', navigationId: 'operations.ai.readiness', href: '/ai-chat' },
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

/** Verified Expo Router entry points; navigation never implies model/engine readiness. */
export const PRODUCT_WORKSPACES = [
  { id: 'academy', title: 'Academy', subtitle: 'Curricula and lessons', href: '/mega-academy' },
  { id: 'galaxy', title: 'Galaxy Studio', subtitle: 'Build, polish and export', href: '/studio' },
  { id: 'snowball', title: 'Snowball Flow', subtitle: 'Choose a project in Studio', href: '/studio' },
  { id: 'jeeves', title: 'Jeeves Chat', subtitle: 'Canonical assistant conversations', href: '/jeeves-chat' },
  { id: 'cockpit', title: 'Jeeves Cockpit', subtitle: 'Live service health', href: '/jeeves-hub' },
  { id: 'neural', title: 'AI Models', subtitle: 'Observed model readiness', href: '/ai-chat' },
  { id: 'training', title: 'Game Learning', subtitle: 'Controlled training workspace', href: '/game-learning' },
  { id: 'mirror', title: 'Mirror Room', subtitle: 'Review and simulation', href: '/mirror-room' },
  { id: 'settings', title: 'Settings', subtitle: 'Jeeves, Academy and Studio', href: '/settings' },
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
