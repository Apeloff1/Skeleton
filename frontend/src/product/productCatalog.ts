export type ProductPillar = 'create' | 'play' | 'learn' | 'operate';

export type ProductCapability = {
  id: string;
  title: string;
  description: string;
  pillar: ProductPillar;
  href: string;
  backendSurface?: string;
  experimental?: boolean;
};

/**
 * Canonical user-facing capability map.
 *
 * Skeleton has accumulated hundreds of backend surfaces. This catalog is the
 * redesign boundary: the UI exposes a small product vocabulary while legacy
 * and mined systems remain implementation details behind those experiences.
 */
export const PRODUCT_CAPABILITIES: readonly ProductCapability[] = [
  {
    id: 'studio',
    title: 'Studio',
    description: 'Describe, design, build, test and publish a playable project.',
    pillar: 'create',
    href: '/hub',
    backendSurface: '/api/gameforge-studio',
  },
  {
    id: 'world-forge',
    title: 'World Forge',
    description: 'Construct worlds, scenes, systems, assets and simulation rules.',
    pillar: 'create',
    href: '/hub',
    backendSurface: '/api/worldforge',
  },
  {
    id: 'playables',
    title: 'Play',
    description: 'Launch, inspect and iterate on generated playable builds.',
    pillar: 'play',
    href: '/hub',
    backendSurface: '/api/playable',
  },
  {
    id: 'jeeves',
    title: 'Jeeves',
    description: 'Plan, reason, teach and coordinate build work through one assistant.',
    pillar: 'learn',
    href: '/hub',
    backendSurface: '/api/jeeves',
  },
  {
    id: 'academy',
    title: 'Academy',
    description: 'Learn game development, programming, languages and mathematics.',
    pillar: 'learn',
    href: '/hub',
    backendSurface: '/api/academy',
  },
  {
    id: 'operations',
    title: 'Operations',
    description: 'Observe builds, queues, agents, deployments, safety and runtime health.',
    pillar: 'operate',
    href: '/hub',
    backendSurface: '/api/ops',
  },
  {
    id: 'governance',
    title: 'Governance',
    description: 'Audit consequential actions, moderation decisions and execution policy.',
    pillar: 'operate',
    href: '/hub',
    backendSurface: '/api/governance',
  },
] as const;

export function capabilitiesFor(pillar: ProductPillar): readonly ProductCapability[] {
  return PRODUCT_CAPABILITIES.filter((capability) => capability.pillar === pillar);
}

export function capabilityById(id: string): ProductCapability | undefined {
  return PRODUCT_CAPABILITIES.find((capability) => capability.id === id);
}
