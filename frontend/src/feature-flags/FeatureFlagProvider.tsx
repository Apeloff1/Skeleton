/**
 * Feature-flag context with local-first startup semantics.
 *
 * Bundled flags and per-device/query overrides are always sufficient for first
 * paint. Remote flags refresh in the background after cold-start work has had
 * a chance to finish, sharing the same keyed cache/in-flight request as the
 * boot phase-1 warmer.
 */
import React from 'react';
import { loadFlags, snapshot, invalidate, ResolvedFlag, FlagsSnapshot } from './flagsClient';
import { BUNDLED_FALLBACK_FLAGS } from './fallback';
import { getQueryOverrides, loadLocalOverrides, getLocalOverridesCached } from './overrides';
import { recordImpression, start as startImpressions } from './impressions';

const INITIAL_REMOTE_REFRESH_DELAY_MS = 1_500;

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
  byName: Object.fromEntries(BUNDLED_FALLBACK_FLAGS.map(flag => [flag.name, flag])),
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

function applyOverrides(serverFlags: ResolvedFlag[]): ResolvedFlag[] {
  const local = getLocalOverridesCached();
  const query = getQueryOverrides();
  return serverFlags.map(flag => {
    let resolved = flag.resolved;
    if (Object.prototype.hasOwnProperty.call(local, flag.name)) resolved = !!local[flag.name];
    if (Object.prototype.hasOwnProperty.call(query, flag.name)) resolved = !!query[flag.name];
    return resolved === flag.resolved ? flag : { ...flag, resolved };
  });
}

export const FeatureFlagProvider: React.FC<ProviderProps> = ({
  initialUserId = 'default_user',
  initialFlags,
  children,
}) => {
  const initialSnapshot = React.useRef(snapshot()).current;
  const cold = initialFlags || initialSnapshot?.flags || BUNDLED_FALLBACK_FLAGS;
  const [userId, setUserId] = React.useState<string | null>(initialUserId);
  const [flags, setFlags] = React.useState<ResolvedFlag[]>(cold);
  const [loading, setLoading] = React.useState<boolean>(cold === BUNDLED_FALLBACK_FLAGS);
  const [error, setError] = React.useState<string | null>(null);
  const [environment, setEnvironment] = React.useState<string>(initialSnapshot?.environment || 'unknown');

  const ingest = React.useCallback((next: FlagsSnapshot) => {
    if (!next.ok) {
      setError('flags_fetch_failed');
      return;
    }
    setFlags(applyOverrides(next.flags));
    setEnvironment(next.environment);
    setError(null);
  }, []);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await loadLocalOverrides();
      invalidate();
      const next = await loadFlags(userId, { force: true });
      ingest(next);
    } catch (caught: any) {
      setError(caught?.message || 'flags_error');
    } finally {
      setLoading(false);
    }
  }, [userId, ingest]);

  React.useEffect(() => {
    startImpressions();
    let cancelled = false;
    let remoteTimer: ReturnType<typeof setTimeout> | null = null;

    setLoading(true);
    setError(null);

    // Local/query overrides are startup-safe and should affect bundled or
    // cached flags as soon as storage resolves. They do not wait for network.
    void loadLocalOverrides()
      .then(() => {
        if (cancelled) return;
        const warmed = snapshot();
        if (warmed?.ok) ingest(warmed);
        else setFlags(current => applyOverrides(current));
        setLoading(false);
      })
      .catch((caught: any) => {
        if (cancelled) return;
        setError(caught?.message || 'flags_override_error');
        setLoading(false);
      });

    // Remote refresh is intentionally background-only. Boot phase 1 may have
    // already started the same request; loadFlags then reuses that in-flight
    // promise or its successful cache instead of issuing a duplicate fetch.
    remoteTimer = setTimeout(() => {
      void loadFlags(userId)
        .then(next => {
          if (!cancelled) ingest(next);
        })
        .catch((caught: any) => {
          if (!cancelled) setError(caught?.message || 'flags_error');
        });
    }, INITIAL_REMOTE_REFRESH_DELAY_MS);

    return () => {
      cancelled = true;
      if (remoteTimer) clearTimeout(remoteTimer);
    };
  }, [userId, ingest]);

  const byName = React.useMemo(() => {
    const map: Record<string, ResolvedFlag> = {};
    for (const flag of flags) map[flag.name] = flag;
    return map;
  }, [flags]);

  const value = React.useMemo<FeatureFlagContextValue>(() => ({
    flags,
    byName,
    environment,
    loading,
    error,
    userId,
    refresh,
    setUserId,
  }), [flags, byName, environment, loading, error, userId, refresh]);

  return (
    <FeatureFlagContext.Provider value={value}>{children}</FeatureFlagContext.Provider>
  );
};

export function useFeatureFlag(name: string, fallback: boolean = false): boolean {
  const context = React.useContext(FeatureFlagContext);
  const flag = context.byName[name];
  const value = flag ? flag.resolved : fallback;
  React.useEffect(() => { recordImpression(name, value); }, [name, value]);
  return value;
}

export function useFeatureFlags(): FeatureFlagContextValue {
  return React.useContext(FeatureFlagContext);
}

export default FeatureFlagProvider;
