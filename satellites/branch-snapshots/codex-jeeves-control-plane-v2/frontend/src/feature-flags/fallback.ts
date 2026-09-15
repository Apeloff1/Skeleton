/**
 * src/feature-flags/fallback.ts — bundled defaults.
 *
 * When the backend is unreachable on first boot we still need the app
 * to behave sensibly. These defaults MIRROR `core/feature_flags.py::
 * DEFAULT_FLAGS` so the cold-boot experience matches a freshly-seeded
 * server. Keep the two lists in sync.
 */
import type { ResolvedFlag } from './flagsClient';

export const BUNDLED_FALLBACK_FLAGS: ResolvedFlag[] = [
  { name: 'hub.network_banner',          description: 'Show offline banner on Hub.',     enabled: true,  rollout: 100, environments: [], resolved: true  },
  { name: 'hub.command_palette',         description: 'Cmd/Ctrl-K command palette.',     enabled: true,  rollout: 100, environments: [], resolved: true  },
  { name: 'hub.lazy_modals',             description: 'Lazy mount heavy modals.',        enabled: true,  rollout: 100, environments: [], resolved: true  },
  { name: 'boot.starfall_background',    description: 'Starfall splash backdrop.',       enabled: true,  rollout: 100, environments: [], resolved: true  },
  { name: 'experimental.live_collab_v2', description: 'v2 live collab engine (beta).',   enabled: false, rollout:  10, environments: ['dev','staging'], resolved: false },
  { name: 'experimental.ai_pipeline_v3', description: 'v3 AI pipeline orchestrator.',    enabled: false, rollout:   0, environments: ['dev'], resolved: false },
  { name: 'ux.reduce_motion_strict',     description: 'Stricter motion reduction.',      enabled: false, rollout: 100, environments: [], resolved: false },
  { name: 'observability.frontend_breadcrumbs', description: 'Ship FE breadcrumb trail.', enabled: true, rollout: 100, environments: [], resolved: true  },
];
