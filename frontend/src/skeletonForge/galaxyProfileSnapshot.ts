/** A bounded, explicitly saved complete Galaxy authoring profile.
 * Never automatically generates a game or silently replaces a Forge draft.
 */
import { MAX_PROFILE_CHARS, normaliseGalaxyProfile, type GalaxyProfile } from './galaxyHandoff';

export const SAVED_GALAXY_SCHEMA = 'skeleton.galaxy.saved-full-design.v1' as const;
export const SAVED_GALAXY_TTL_MS = 30 * 24 * 60 * 60 * 1000;
export const SAVED_GALAXY_MAX_CHARS = MAX_PROFILE_CHARS + 2048;

export interface SavedGalaxyProfile {
  schema: typeof SAVED_GALAXY_SCHEMA;
  savedMs: number;
  profile: GalaxyProfile;
}
export function makeSavedGalaxyProfile(payload: unknown, now: number = Date.now()): SavedGalaxyProfile {
  if (!Number.isSafeInteger(now) || now < 0) throw new Error('Invalid Galaxy snapshot clock');
  const profile = payload !== null && typeof payload === 'object' &&
      !Array.isArray(payload) && (payload as Record<string, unknown>).schema === 'skeleton.gameforge.galaxy_profile.v1'
      ? normaliseGalaxyProfile((payload as GalaxyProfile).config)
      : normaliseGalaxyProfile(payload);
  const saved: SavedGalaxyProfile = { schema: SAVED_GALAXY_SCHEMA, savedMs: now, profile };
  if (JSON.stringify(saved).length > SAVED_GALAXY_MAX_CHARS) throw new Error('Saved Galaxy design exceeds budget');
  return saved;
}
export function parseSavedGalaxyProfile(raw: unknown, now: number = Date.now()): SavedGalaxyProfile | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const source = raw as Record<string, unknown>;
  if (Object.keys(source).sort().join(',') !== 'profile,savedMs,schema') return null;
  const savedMs = source.savedMs;
  if (source.schema !== SAVED_GALAXY_SCHEMA || !Number.isSafeInteger(savedMs) ||
      typeof savedMs !== 'number' || !Number.isSafeInteger(now) ||
      savedMs < 0 || savedMs > now + 30_000 || now - savedMs > SAVED_GALAXY_TTL_MS) return null;
  if (!source.profile || typeof source.profile !== 'object' || Array.isArray(source.profile)) return null;
  const original = source.profile as Record<string, unknown>;
  if (Object.keys(original).sort().join(',') !== 'config,schema' ||
      original.schema !== 'skeleton.gameforge.galaxy_profile.v1') return null;
  try {
    const profile = normaliseGalaxyProfile(original.config);
    return { schema: SAVED_GALAXY_SCHEMA, savedMs, profile };
  } catch {
    return null;
  }
}
