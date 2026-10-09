/**
 * User-facing cross-capability journeys for the existing product shell.
 *
 * A step being opened is NOT evidence that an operation ran or a build finished.
 * No model execution, asset or project data is stored by this module.
 */
import { projectHref } from './worldWorkspace';

export type JourneyStep = {
  id: string;
  title: string;
  description: string;
  href: string;
  requiresBuild?: boolean;
  acceptsBuild?: boolean;
};
export type ProductJourney = {
  id: string;
  title: string;
  purpose: string;
  steps: readonly JourneyStep[];
};

export const PRODUCT_JOURNEYS: readonly ProductJourney[] = [
  {
    id: 'idea-to-game', title: 'Idea → playable game',
    purpose: 'Turn a rough idea into an editable build and its game knowledge base.',
    steps: [
      { id: 'describe', title: 'Describe your game', description: 'Start with the AI game generator.', href: '/ai-game-generator' },
      { id: 'design', title: 'Shape the design', description: 'Set the genre, era and scope in Galaxy Factory.', href: '/galaxy' },
      { id: 'build', title: 'Build and iterate', description: 'Run the staged build and quality pipeline.', href: '/studio', acceptsBuild: true },
      { id: 'knowledge', title: 'Inspect game knowledge', description: 'Review and refine generated source artifacts.', href: '/game-kb', requiresBuild: true },
      { id: 'library', title: 'Review your builds', description: 'Inspect build status and download artifacts.', href: '/my-builds' },
    ],
  },
  {
    id: 'research-to-creation', title: 'Research → creation',
    purpose: 'Find evidence, ask Jeeves, turn the result into a game design.',
    steps: [
      { id: 'discover', title: 'Discover material', description: 'Search your accessible catalog and resources.', href: '/search' },
      { id: 'sources', title: 'Inspect knowledge', description: 'Review knowledge databases and available sources.', href: '/knowledge-databases' },
      { id: 'reason', title: 'Discuss findings', description: 'Reason through the game concept with Jeeves.', href: '/jeeves-chat' },
      { id: 'spec', title: 'Draft the design', description: 'Convert the concept into a design specification.', href: '/design-spec' },
      { id: 'prototype', title: 'Prototype in Studio', description: 'Build a playable draft from the design.', href: '/studio', acceptsBuild: true },
    ],
  },
  {
    id: 'polish-and-export', title: 'Polish → export',
    purpose: 'Choose a build, refine it, review the results and package it.',
    steps: [
      { id: 'choose', title: 'Find your build', description: 'Browse saved builds and their actual statuses.', href: '/my-builds' },
      { id: 'refine', title: 'Improve the build', description: 'Run the Snowball pipeline and advanced alternatives.', href: '/studio', acceptsBuild: true },
      { id: 'inspect', title: 'Edit the knowledge base', description: 'Inspect generated artifacts and approvals.', href: '/game-kb', requiresBuild: true },
      { id: 'quality', title: 'Review quality', description: 'Inspect quality checks for the current work.', href: '/quality-control' },
      { id: 'compare', title: 'Compare renders', description: 'Review visual changes before packaging.', href: '/render-compare' },
      { id: 'export', title: 'Package the result', description: 'Return to Studio for gated APK/ZIP export.', href: '/studio', acceptsBuild: true },
    ],
  },
  {
    id: 'learn-and-make', title: 'Learn → make',
    purpose: 'Choose a learning path, practice and immediately apply it in a project.',
    steps: [
      { id: 'explore', title: 'Explore learning', description: 'Browse your learning hub.', href: '/learning-hub' },
      { id: 'path', title: 'Choose a path', description: 'Find a structured study route.', href: '/study-paths' },
      { id: 'practice', title: 'Practice code', description: 'Write and run a practical experiment.', href: '/playground' },
      { id: 'compare', title: 'Compare languages', description: 'Solve a task across languages.', href: '/rosetta-playground' },
      { id: 'apply', title: 'Apply your skills', description: 'Use Studio to turn practice into a project.', href: '/studio', acceptsBuild: true },
    ],
  },
  {
    id: 'operate-and-recover', title: 'Operate → recover',
    purpose: 'Observe the app and locate issues without losing your work.',
    steps: [
      { id: 'status', title: 'Check the app', description: 'Review actual service health and readiness.', href: '/product' },
      { id: 'command', title: 'Open command center', description: 'Review operator controls.', href: '/command-center' },
      { id: 'control', title: 'Inspect control plane', description: 'Review runtime and agent execution state.', href: '/control-plane' },
      { id: 'boot', title: 'Inspect startup trace', description: 'Diagnose boot and launch problems.', href: '/boot-log' },
      { id: 'projects', title: 'Recover project context', description: 'Return to saved builds, even after navigation changes.', href: '/my-builds' },
      { id: 'safe', title: 'Use safe mode', description: 'Open the dedicated fallback environment if required.', href: '/safe-mode' },
    ],
  },
  {
    id: 'assistant-to-builder', title: 'AI assistant → builder',
    purpose: 'Use Jeeves to reason and coordinate, then inspect work in the builder.',
    steps: [
      { id: 'ask', title: 'Start with Jeeves', description: 'Discuss the goal in an AI conversation.', href: '/jeeves-chat' },
      { id: 'review', title: 'Review agent proposals', description: 'Inspect agent output before acting.', href: '/agent-review' },
      { id: 'mission', title: 'Inspect the mission', description: 'Review current work and its execution status.', href: '/mission-control' },
      { id: 'tools', title: 'Open the builder hub', description: 'Choose the tool relevant to your task.', href: '/build-hub' },
      { id: 'studio', title: 'Continue in Studio', description: 'Work on an existing or new game.', href: '/studio', acceptsBuild: true },
      { id: 'review', title: 'Review the design', description: 'Compile a game-scoped design review with explicit control.', href: '/design-review', requiresBuild: true },
    ],
  },
  {
    id: 'world-and-systems', title: 'World → systems',
    purpose: 'Design a world and its systems, then integrate the outcome.',
    steps: [
      { id: 'choose', title: 'Choose the game', description: 'Select the project whose world you want to improve.', href: '/my-builds' },
      { id: 'workbench', title: 'Open World Workbench', description: 'Inspect world evidence and forge missing artifacts.', href: '/world-workbench', requiresBuild: true },
      { id: 'world', title: 'Create a world', description: 'Define regions, ecology and world rules from the game.', href: '/worldforge', acceptsBuild: true },
      { id: 'scene', title: 'Compose a scene', description: 'Build a scene for this game.', href: '/compose-scene', requiresBuild: true },
      { id: 'assets', title: 'Build assets', description: 'Generate art grounded in this game's knowledge.', href: '/asset-genesis', requiresBuild: true },
      { id: 'mechanics', title: 'Engineer mechanics', description: 'Mount and inspect game systems.', href: '/systems-forge', requiresBuild: true },
      { id: 'review', title: 'Review your design', description: 'Compile an evidence-guided design brief.', href: '/design-review', requiresBuild: true },
      { id: 'studio', title: 'Integrate the project', description: 'Continue with the integrated game build.', href: '/studio', acceptsBuild: true },
    ],
  },
  {
    id: 'knowledge-iteration', title: 'Knowledge → iteration',
    purpose: 'Turn knowledge into a reviewed, editable game artifact.',
    steps: [
      { id: 'sources', title: 'Browse knowledge', description: 'Find resources in the knowledge databases.', href: '/knowledge-databases' },
      { id: 'design', title: 'Define requirements', description: 'Capture game intent in a design specification.', href: '/design-spec' },
      { id: 'choose', title: 'Select the game', description: 'Choose an existing build to improve.', href: '/my-builds' },
      { id: 'artifacts', title: 'Review game artifacts', description: 'Edit, approve and refine the game knowledge base.', href: '/game-kb', requiresBuild: true },
      { id: 'apply', title: 'Continue the build', description: 'Run the Studio pipeline after approving artifacts.', href: '/studio', acceptsBuild: true },
    ],
  },
] as const;

export const JOURNEY_SESSION_VERSION = 1;
export type JourneySession = {
  version: 1;
  selected: string;
  opened: Record<string, string[]>;
  last: { journey: string; step: string } | null;
};

export function initialJourneySession(): JourneySession {
  return { version: 1, selected: PRODUCT_JOURNEYS[0].id, opened: {}, last: null };
}

export function journeyById(id: string): ProductJourney | undefined {
  return PRODUCT_JOURNEYS.find((journey) => journey.id === id);
}

export function normalizeJourneySession(raw: unknown): JourneySession {
  const clean = initialJourneySession();
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return clean;
  const value = raw as Record<string, unknown>;
  if (value.version !== JOURNEY_SESSION_VERSION) return clean;
  if (typeof value.selected === 'string' && journeyById(value.selected)) clean.selected = value.selected;

  if (value.opened && typeof value.opened === 'object' && !Array.isArray(value.opened)) {
    for (const journey of PRODUCT_JOURNEYS) {
      const items = (value.opened as Record<string, unknown>)[journey.id];
      if (!Array.isArray(items)) continue;
      const valid = new Set(journey.steps.map((step) => step.id));
      clean.opened[journey.id] = [...new Set(items.filter((id): id is string => typeof id === 'string' && valid.has(id)))].slice(0, journey.steps.length);
    }
  }
  const last = value.last;
  if (last && typeof last === 'object' && !Array.isArray(last)) {
    const row = last as Record<string, unknown>;
    if (typeof row.journey === 'string' && typeof row.step === 'string' &&
        journeyById(row.journey)?.steps.some((step) => step.id === row.step)) {
      clean.last = { journey: row.journey, step: row.step };
    }
  }
  return clean;
}

export function recordJourneyOpen(state: JourneySession, journeyId: string, stepId: string): JourneySession {
  const journey = journeyById(journeyId);
  if (!journey?.steps.some((step) => step.id === stepId)) return state;
  const seen = state.opened[journeyId] ?? [];
  return {
    version: 1,
    selected: journeyId,
    opened: { ...state.opened, [journeyId]: seen.includes(stepId) ? seen : [...seen, stepId] },
    last: { journey: journeyId, step: stepId },
  };
}

export function nextUnopened(journey: ProductJourney, seen: readonly string[], hasBuild: boolean): JourneyStep | null {
  return journey.steps.find((step) => !seen.includes(step.id) && (!step.requiresBuild || hasBuild)) ?? null;
}

export function validBuildId(value: unknown): string {
  const id = typeof value === 'string' ? value : '';
  return /^[A-Za-z0-9_-]{1,128}$/.test(id) ? id : '';
}

export function journeyStepHref(step: JourneyStep, buildId: unknown): string | null {
  const id = validBuildId(buildId);
  if (step.requiresBuild && !id) return null;
  if (id && (step.requiresBuild || step.acceptsBuild)) {
    return projectHref(step.href, id);
  }
  return step.href;
}
