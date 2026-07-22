/**
 * src/feature-flags/index.ts — barrel export for the feature-flag system.
 */
export {
  FeatureFlagProvider,
  useFeatureFlag,
  useFeatureFlags,
} from './FeatureFlagProvider';
export {
  loadFlags,
  snapshot,
  invalidate,
  isEnabledCached,
} from './flagsClient';
export type { ResolvedFlag, FlagsSnapshot } from './flagsClient';
export {
  loadLocalOverrides,
  setLocalOverride,
  clearLocalOverrides,
  getLocalOverridesCached,
  getQueryOverrides,
} from './overrides';
export {
  loadAdminToken,
  setAdminToken,
  adminHeaders,
  getAdminTokenCached,
} from './adminToken';
export { recordImpression, flush as flushImpressions, start as startImpressions } from './impressions';
export { BUNDLED_FALLBACK_FLAGS } from './fallback';

// Canonical flag-name constants — keep these in sync with
// `core/feature_flags.py::DEFAULT_FLAGS`. Using constants instead of
// raw strings prevents typos at call sites.
export const FLAG = {
  HUB_NETWORK_BANNER:        'hub.network_banner',
  HUB_COMMAND_PALETTE:       'hub.command_palette',
  HUB_LAZY_MODALS:           'hub.lazy_modals',
  BOOT_STARFALL:             'boot.starfall_background',
  EXP_LIVE_COLLAB_V2:        'experimental.live_collab_v2',
  EXP_AI_PIPELINE_V3:        'experimental.ai_pipeline_v3',
  UX_REDUCE_MOTION_STRICT:   'ux.reduce_motion_strict',
  OBS_FE_BREADCRUMBS:        'observability.frontend_breadcrumbs',
} as const;
