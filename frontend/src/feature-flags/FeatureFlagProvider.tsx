/**
 * src/feature-flags/FeatureFlagProvider.tsx — context + hooks (Feb 2026).
 *
 * Boot-time prefetch + override merge:
 *
 *   final.resolved = (queryOverride ?? localOverride ?? server.resolved)
 *
 * Bundled fallback flags are used as the absolute floor so cold-boot
 * with no network still renders a sane UI. Impressions are recorded
 * on every useFeatureFlag() call and flushed every 30s to the server.
 */
import React from 'react';
import { loadFlags, snapshot, invalidate, ResolvedFlag, FlagsSnapshot } from './flagsClient';
import { BUNDLED_FALLBACK_FLAGS } from './fallback';
import { getQueryOverrides, loadLocalOverrides, getLocalOverridesCached } from './overrides';
import { recordImpression, start as startImpressions } from './impressions';

interface FeatureFlagContextValue {
  flags: ResolvedFlag[];
  byName: Record<string, ResolvedFlag>;
  environment: string;
  loading: boolean;
  error: string | null;
  userId: string | null;
  refresh: () => Promise<void>;
  setUserId: (id: string | null) => void;
}

const FeatureFlagContext = React.createContext<FeatureFlagContextValue>({
  flags: BUNDLED_FALLBACK_FLAGS,
  byName: Object.fromEntries(BUNDLED_FALLBACK_FLAGS.map(f => [f.name, f])),
  environment: 'unknown',
  loading: true,
  error: null,
  userId: null,
  refresh: async () => {},
  setUserId: () => {},
});

interface ProviderProps {
  initialUserId?: string | null;
  initialFlags?: ResolvedFlag[];
  children: React.ReactNode;
}

/** Merges server flags with local + query overrides. Pure. */
function applyOverrides(serverFlags: ResolvedFlag[]): ResolvedFlag[] {
  const local = getLocalOverridesCached();
  const query = getQueryOverrides();
  return serverFlags.map(f => {
    let resolved = f.resolved;
    if (Object.prototype.hasOwnProperty.call(local, f.name)) resolved = !!local[f.name];
    if (Object.prototype.hasOwnProperty.call(query, f.name)) resolved = !!query[f.name];
    return resolved === f.resolved ? f : { ...f, resolved };
  });
}

export const FeatureFlagProvider: React.FC<ProviderProps> = ({
  initialUserId = 'default_user',
  initialFlags,
  children,
}) => {
  const cold = initialFlags || snapshot()?.flags || BUNDLED_FALLBACK_FLAGS;
  const [userId, setUserId]   = React.useState<string | null>(initialUserId);
  const [flags,  setFlags]    = React.useState<ResolvedFlag[]>(cold);
  const [loading, setLoading] = React.useState<boolean>(cold === BUNDLED_FALLBACK_FLAGS);
  const [error,  setError]    = React.useState<string | null>(null);
  const [env,    setEnv]      = React.useState<string>('unknown');

  const ingest = React.useCallback((snap: FlagsSnapshot) => {
    setFlags(applyOverrides(snap.flags));
    setEnv(snap.environment);
    if (!snap.ok && snap.flags.length === 0) setError('flags_fetch_failed');
  }, []);

  const refresh = React.useCallback(async () => {
    setLoading(true); setError(null);
    try {
      // Make sure local overrides are loaded before we apply them.
      await loadLocalOverrides();
      invalidate();
      const snap = await loadFlags(userId, { force: true });
      ingest(snap);
    } catch (e: any) {
      setError(e?.message || 'flags_error');
    } finally {
      setLoading(false);
    }
  }, [userId, ingest]);

  React.useEffect(() => {
    startImpressions();
    let cancelled = false;
    (async () => {
      try {
        await loadLocalOverrides();
        const snap = await loadFlags(userId);
        if (cancelled) return;
        ingest(snap);
      } catch (e: any) {
        if (!cancelled) setError(e?.message || 'flags_error');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [userId, ingest]);

  const byName = React.useMemo(() => {
    const m: Record<string, ResolvedFlag> = {};
    for (const f of flags) m[f.name] = f;
    return m;
  }, [flags]);

  const value = React.useMemo<FeatureFlagContextValue>(() => ({
    flags, byName, environment: env, loading, error, userId, refresh, setUserId,
  }), [flags, byName, env, loading, error, userId, refresh]);

  return (
    <FeatureFlagContext.Provider value={value}>{children}</FeatureFlagContext.Provider>
  );
};

/** Returns `true`/`false` for a flag name (with optional fallback). */
export function useFeatureFlag(name: string, fallback: boolean = false): boolean {
  const ctx = React.useContext(FeatureFlagContext);
  const f = ctx.byName[name];
  const value = f ? f.resolved : fallback;
  // Record impression (best-effort, fire-and-forget).
  React.useEffect(() => { recordImpression(name, value); }, [name, value]);
  return value;
}

export function useFeatureFlags(): FeatureFlagContextValue {
  return React.useContext(FeatureFlagContext);
}

export default FeatureFlagProvider;
