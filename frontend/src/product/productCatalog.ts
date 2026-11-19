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
      { id: 'unified-galaxy', title: 'Galaxy Studio · unified', description: 'Open the existing idea-to-build workflow with Snowball and export handoffs.', navigationId: 'studio.galaxy.unified', href: '/studio' },
      { id: 'skeleton-studio', title: 'Skeleton studio', description: 'Open the Skeleton forge from a brief: first-run, account, projects, build status, and settings.', navigationId: 'studio.skeleton.foundation', href: '/skeleton-studio' },
      { id: 'classic-galaxy', title: 'Galaxy Studio Factory', description: 'Use the classic questionnaire and 100-phase builder.', navigationId: 'studio.galaxy.classic', href: '/galaxy' },
      { id: 'snowball-flow', title: 'Snowball Flow', description: 'Review, refine and lock forge stages with the growing game design document.', navigationId: 'studio.snowball', href: '/snowball' },
      { id: 'world-workbench', title: 'World Workbench', description: 'Inspect and author persistent world systems for the current build.', navigationId: 'studio.world.workbench', href: '/world-workbench' },
      { id: 'studio-settings', title: 'Galaxy Studio settings', description: 'Configure existing build emphases and phase preferences.', navigationId: 'studio.settings', href: '/settings/galaxy-studio' },
      { id: 'new-project', title: 'New project', description: 'Start from a prompt, brief or template.', operation: 'project.create', legacyHref: '/ai-game-generator' },
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
      { id: 'universal-forge', title: 'Universal forge', description: 'Paint eras, skins and constructs, then build them through the forge runtime.', navigationId: 'studio.forge.universal', href: '/forge' },
      { id: 'gameforge-studio', title: 'Gameforge studio', description: 'Run the Gameforge studio from a brief through a build you can watch.', navigationId: 'studio.gameforge', href: '/gameforge-studio' },
      { id: 'build-hub', title: 'Build hub', description: 'Watch and resume project builds from one desk.', navigationId: 'studio.build.hub', href: '/build-hub' },
      { id: 'construct-forge', title: 'Construct forge', description: 'Author constructs and place them in a scene.', navigationId: 'studio.construct', href: '/construct-forge' },
      { id: 'compose-scene', title: 'Compose scene', description: 'Arrange a scene from existing constructs and cameras.', navigationId: 'studio.scene.compose', href: '/compose-scene' },
      { id: 'creator-desk', title: 'Creator desk', description: 'Open the creator workspace for an original project.', navigationId: 'studio.creator', href: '/creator' },
      { id: 'skeleton-forge', title: 'Skeleton forge', description: 'Open the Skeleton forge controls beside the studio foundation.', navigationId: 'studio.forge.skeleton', href: '/skeleton-forge' },
      { id: 'guided-journeys', title: 'Guided workflows', description: 'Research, create, refine and release without losing your place.', navigationId: 'studio.journeys', href: '/journeys' },
      { id: 'design-spec', title: 'Design spec', description: 'Read and edit the versioned design specification for the current project.', navigationId: 'studio.design.spec', href: '/design-spec' },
      { id: 'design-review', title: 'Design review', description: 'Review a design before it is locked into a build.', navigationId: 'studio.design.review', href: '/design-review' },
      { id: 'story-index', title: 'Story index', description: 'Browse story beats and the canon links between them.', navigationId: 'studio.story.index', href: '/story-index' },
      { id: 'camera-director', title: 'Camera director', description: 'Set cameras and coverage for a scene.', navigationId: 'studio.camera', href: '/camera-director' },
      { id: 'cover-studio', title: 'Cover studio', description: 'Compose cover art for a project from admitted assets.', navigationId: 'studio.cover', href: '/cover-studio' },
      { id: 'media-studio', title: 'Media studio', description: 'Inspect and arrange image, audio and video assets.', navigationId: 'studio.media', href: '/media-studio' },
      { id: 'ecosystem-studio', title: 'Ecosystem', description: 'Create a brief, run the integrated studio pipeline, and inspect the sealed result.', navigationId: 'studio.ecosystem', href: '/ecosystem' },
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
      { id: 'worldforge-home', title: 'Worldforge', description: 'Open worldforge authoring, including the map and the vault.', navigationId: 'world.forge.home', href: '/worldforge' },
      { id: 'worldforge-map', title: 'Worldforge map', description: 'Inspect the spatial map of the current world.', navigationId: 'world.forge.map', href: '/worldforge-map' },
      { id: 'worldforge-vault', title: 'Worldforge vault', description: 'Browse stored world artifacts and reusable pieces.', navigationId: 'world.forge.vault', href: '/worldforge-vault' },
      { id: 'asset-genesis', title: 'Asset genesis', description: 'Generate original assets and admit them into the project vault.', navigationId: 'world.assets.genesis', href: '/asset-genesis' },
      { id: 'item-foundry', title: 'Item foundry', description: 'Author items, costs and the rules that use them.', navigationId: 'world.items.foundry', href: '/item-foundry' },
      { id: 'systems-forge', title: 'Systems forge', description: 'Compose quests, economy, crafting and progression in one forge.', navigationId: 'world.systems.forge', href: '/systems-forge' },
      { id: 'canon-graph', title: 'Canon graph', description: 'Inspect how world facts depend on each other.', navigationId: 'world.canon.graph', href: '/canon-graph' },
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
      { id: 'playable-runtime', title: 'Playable runtime', description: 'Launch the generated playable and exercise its core loop.', navigationId: 'play.runtime', href: '/playable' },
      { id: 'playground', title: 'Playground', description: 'Try a mechanic in isolation before it enters a project.', navigationId: 'play.playground', href: '/playground' },
      { id: 'worlds-gallery', title: 'Worlds gallery', description: 'Browse generated worlds you can open.', navigationId: 'play.worlds.gallery', href: '/worlds-gallery' },
      { id: 'gallery', title: 'Gallery', description: 'Review captured frames and finished scenes.', navigationId: 'play.gallery', href: '/gallery' },
      { id: 'multiplayer-room', title: 'Multiplayer', description: 'Inspect session, presence and shared-play controls.', navigationId: 'play.multiplayer', href: '/multiplayer' },
      { id: 'tournaments', title: 'Tournaments', description: 'Open scored runs and tournament brackets.', navigationId: 'play.tournaments', href: '/tournaments' },
      { id: 'music-bed', title: 'Music', description: 'Preview music beds attached to a project.', navigationId: 'play.music', href: '/music' },
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
      { id: 'jeeves-cockpit', title: 'Jeeves Cockpit', description: 'Inspect persona, services, service health and operator controls.', navigationId: 'jeeves.cockpit', href: '/jeeves-hub' },
      { id: 'jeeves-workbench', title: 'Jeeves Workbench', description: 'Open the existing agent workbench and orchestration workspace.', navigationId: 'jeeves.workbench', href: '/jeeves-workbench' },
      { id: 'jeeves-settings', title: 'Jeeves settings', description: 'Edit persona, directives, DNA controls and model-facing preferences.', navigationId: 'jeeves.settings', href: '/settings/jeeves' },
      { id: 'jeeves-runtime', title: 'AI runtime and readiness', description: 'Inspect setup, local inference readiness and model service status.', navigationId: 'jeeves.runtime.setup', href: '/setup' },
      { id: 'model-inventory', title: 'Observed model inventory', description: 'Inspect authenticated engine model readiness, capability reports and selection availability without asserting model activation.', navigationId: 'jeeves.models.inventory', href: '/ai-models' },
      { id: 'model-chat', title: 'Governed model workspace', description: 'Inspect model inventory and use server-authorized conversation and replay.', navigationId: 'jeeves.models.workspace', href: '/ai-chat' },
      { id: 'mirror-simulation', title: 'Mirror Room', description: 'Open the existing training, review and adversarial mirror UI.', navigationId: 'jeeves.mirrors', href: '/mirror-room' },
      { id: 'reason', title: 'AI chat', description: 'Work through a problem with the configured engine and durable conversation history.', navigationId: 'jeeves.chat.canonical', href: '/jeeves-chat' },
      { id: 'governed-chat', title: 'Conversation workspace', description: 'Use governed attachments, message editing and regeneration with canonical conversation history.', navigationId: 'jeeves.chat.governed', href: '/ai-chat' },
      { id: 'capture-web', title: 'Capture web knowledge', description: 'Authorize a bounded crawl and inspect captured sources.', navigationId: 'jeeves.crawler', href: '/crawler' },
      { id: 'learn-games', title: 'Game learning studio', description: 'Edit, simulate and train original games across registered engine and console targets.', navigationId: 'jeeves.games.learn', href: '/game-learning' },
      { id: 'plan', title: 'Plan', description: 'Turn a goal into coordinated executable work.', operation: 'jeeves.plan' },
      { id: 'review', title: 'Review agents', description: 'Inspect delegated work and agent outcomes.', operation: 'agents.review', legacyHref: '/agent-review' },
      { id: 'agent-codex', title: 'Agent codex', description: 'Inspect agent identities, mandates and recent work.', navigationId: 'jeeves.codex', href: '/agentCodex' },
      { id: 'game-kb', title: 'Game knowledge', description: 'Search the game knowledge base used by Jeeves.', navigationId: 'jeeves.game.kb', href: '/game-kb' },
      { id: 'jury-room', title: 'Jury room', description: 'Compare critiques before a draft is accepted.', navigationId: 'jeeves.jury', href: '/jury-room' },
      { id: 'dragon-crawler-pilot', title: 'Dragon research pilot', description: 'Open the signed-in research mission. Visiting does not capture URLs.', navigationId: 'jeeves.crawler.pilot', href: '/dragon-crawler-pilot' },
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
      { id: 'academy-home', title: 'Mega Academy', description: 'Open the cross-discipline Academy and curriculum hub.', navigationId: 'academy.mega', href: '/mega-academy' },
      { id: 'academy-learning', title: 'Learning Hub', description: 'Explore training paths, lessons and learning resources.', navigationId: 'academy.learning', href: '/learning-hub' },
      { id: 'academy-classes', title: 'My Classes', description: 'Resume enrolled classes, quizzes and progression.', navigationId: 'academy.classes', href: '/my-classes' },
      { id: 'academy-cs', title: 'Computer Science Academy', description: 'Study programming and computer-science curricula.', navigationId: 'academy.cs', href: '/cs-academy' },
      { id: 'academy-math', title: 'Math Academy', description: 'Open mathematics lessons and exercises.', navigationId: 'academy.math', href: '/math-academy' },
      { id: 'academy-physics', title: 'Physics Academy', description: 'Open physics lessons and simulations.', navigationId: 'academy.physics', href: '/physics-academy' },
      { id: 'academy-settings', title: 'Academy settings', description: 'Adjust narration, reading and study preferences.', navigationId: 'academy.settings', href: '/settings/academy' },
      { id: 'continue', title: 'Continue learning', description: 'Resume the current learning path.', operation: 'academy.continue' },
      { id: 'practice', title: 'Practice', description: 'Open adaptive exercises and challenges.', operation: 'academy.practice' },
      { id: 'progress', title: 'Learning progress', description: 'Inspect mastery, streaks and completed work.', operation: 'academy.progress' },
      { id: 'class-week', title: 'Class week', description: 'Read, lab and practice one week of a class.', navigationId: 'academy.week', href: '/class-week' },
      { id: 'language-academy', title: 'Language academy', description: 'Study programming languages on a structured track.', navigationId: 'academy.language', href: '/language-academy' },
      { id: 'reading-library', title: 'Reading library', description: 'Open the reading library and comprehension tools.', navigationId: 'academy.reading', href: '/readingLibrary' },
      { id: 'curriculum-browser', title: 'Curriculum', description: 'Drill into a syllabus and its lessons.', navigationId: 'academy.curriculum', href: '/curriculum' },
      { id: 'discourse', title: 'Discourse', description: 'Review arguments, claims and the sources they cite.', navigationId: 'academy.discourse', href: '/discourse' },
      { id: 'study-notes', title: 'Notes', description: 'Keep study notes beside the lesson you are in.', navigationId: 'academy.notes', href: '/notes' },
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
      { id: 'jeeves-console', title: 'Jeeves service cockpit', description: 'Review service reachability and health before running workflows.', navigationId: 'ops.jeeves.cockpit', href: '/jeeves-hub' },
      { id: 'control-dashboard', title: 'Governed control plane', description: 'Inspect execution receipts, policy gates and runtime readiness.', navigationId: 'ops.control', href: '/control-plane' },
      { id: 'preferences', title: 'All settings', description: 'Open the existing settings hub without duplicating preferences.', navigationId: 'ops.settings', href: '/settings' },
      { id: 'agents', title: 'Agents', description: 'Inspect active workers, tasks and health.', operation: 'ops.agents', legacyHref: '/agents' },
      { id: 'setup', title: 'Setup & readiness', description: 'Check first-install services, model availability and capture readiness.', navigationId: 'operations.setup', href: '/setup' },
      { id: 'runtime', title: 'Runtime health', description: 'Inspect governed queues, policy, audit and resource pressure.', operation: 'ops.runtime', href: '/control-plane' },
      { id: 'deployments', title: 'Deployments', description: 'Review build and deployment state.', operation: 'ops.deployments' },
      { id: 'command-center', title: 'Command center', description: 'Watch builds, agents and operator actions from one board.', navigationId: 'ops.command', href: '/command-center' },
      { id: 'mission-control', title: 'Mission control', description: 'Follow live missions and their admission state.', navigationId: 'ops.mission', href: '/mission-control' },
      { id: 'ops-dashboard', title: 'Dashboard', description: 'See the operator dashboard for this studio.', navigationId: 'ops.dashboard', href: '/dashboard' },
      { id: 'health-board', title: 'Health', description: 'Read service health without leaving the studio.', navigationId: 'ops.health', href: '/health' },
      { id: 'telemetry-board', title: 'Telemetry', description: 'Inspect the runtime telemetry this studio is allowed to show.', navigationId: 'ops.telemetry', href: '/telemetry' },
      { id: 'scheduler-board', title: 'Scheduler', description: 'See queued work and what is allowed to run.', navigationId: 'ops.scheduler', href: '/scheduler' },
      { id: 'marketplace-board', title: 'Marketplace', description: 'Review listings. Checkout stays closed until payment delivery is qualified.', navigationId: 'ops.marketplace', href: '/marketplace' },
      { id: 'sign-in-screen', title: 'Sign in', description: 'Open the studio sign-in screen.', navigationId: 'ops.signin', href: '/sign-in' },
    ],
  },
  { id: 'library',
    title: 'Whole studio',
    description: 'Every route installed in this build, including tools that are not yet a pillar card.',
    pillar: 'operate',
    href: capabilityHref('library'),
    actions: [
      { id: 'surface-atlas', title: 'Every installed surface', description: 'Search the complete index of routes shipped in this build.', navigationId: 'library.surfaces', href: '/surfaces' },
      { id: 'everything-menu', title: 'Everything menu', description: 'Browse the install menu of every feature card.', navigationId: 'library.menu', href: '/menu' },
      { id: 'legacy-hub', title: 'Legacy hub', description: 'Open the accumulated hub while tools are folded into the product pillars.', navigationId: 'library.hub', href: '/hub' },
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

/**
 * Existing product surfaces are exposed directly on the consolidated home.
 * Resolve from canonical navigation actions so deep links cannot drift away
 * from the capability catalog. These links NEVER admit backend operations.
 */
export const PRODUCT_HOME_SHORTCUT_IDS = [
  'studio.galaxy.unified',
  'studio.skeleton.foundation',
  'studio.snowball',
  'academy.mega',
  'jeeves.cockpit',
  'jeeves.workbench',
  'jeeves.chat.governed',
  'jeeves.runtime.setup',
  'jeeves.models.inventory',
  'ops.settings',
  'library.surfaces',
  'studio.forge.universal',
  'play.runtime',
  'ops.command',
] as const;

export const PRODUCT_HOME_SHORTCUTS: readonly {
  id: string;
  title: string;
  href: string;
  pillar: ProductPillar;
}[] = PRODUCT_CAPABILITIES.flatMap((capability) =>
  capability.actions
    .filter((action) =>
      typeof action.navigationId === 'string' &&
      (PRODUCT_HOME_SHORTCUT_IDS as readonly string[]).includes(action.navigationId))
    .map((action) => ({
      id: action.id,
      title: action.title,
      href: action.href as string,
      pillar: capability.pillar,
    })),
);

export function capabilitiesFor(pillar: ProductPillar): readonly ProductCapability[] {
  return PRODUCT_CAPABILITIES.filter((capability) => capability.pillar === pillar);
}

export function capabilityById(id: string): ProductCapability | undefined {
  return PRODUCT_CAPABILITIES.find((capability) => capability.id === id);
}

export function actionById(capabilityId: string, actionId: string): ProductAction | undefined {
  return capabilityById(capabilityId)?.actions.find((action) => action.id === actionId);
}
