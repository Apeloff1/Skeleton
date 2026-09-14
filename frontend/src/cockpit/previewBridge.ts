/**
 * Skeleton cockpit preview bridge.
 *
 * Distilled from the strongest host/guest preview mechanics in the HyperForge
 * cockpit without importing its router, auth, database, or vendor-specific
 * presentation layer. The bridge is inert on native and top-level web runs.
 * External parents are accepted only through an explicit origin allowlist;
 * same-origin parents are permitted automatically.
 */

export const COCKPIT_BRIDGE_CHANNEL = 'skeleton-cockpit-bridge' as const;
export const COCKPIT_BRIDGE_VERSION = 1 as const;

const HISTORY_ROOT_KEY = '__skeletonCockpitBridgeRoot';
const FALLBACK_ORIGIN = 'https://skeleton.invalid';

type BridgeRecord = Record<string, unknown>;

type LocationWithAncestors = Location & {
  ancestorOrigins?: {
    readonly length: number;
    readonly [index: number]: string;
  };
};

export interface CockpitBridgeOptions {
  allowedParentOrigins?: readonly string[];
  getRoutePaths?: () => readonly string[];
  navigate?: (path: string) => void;
}

function isRecord(value: unknown): value is BridgeRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function normalizeOrigin(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' && url.protocol !== 'http:') return null;
    return url.origin;
  } catch {
    return null;
  }
}

/**
 * Reads externally injected cockpit origins without binding the product to a
 * specific host. Deployments can set `globalThis.__SKELETON_COCKPIT_ORIGINS__`
 * to either a comma-separated string or an array before the application boots.
 */
export function getConfiguredCockpitOrigins(): string[] {
  const configured = (
    globalThis as typeof globalThis & {
      __SKELETON_COCKPIT_ORIGINS__?: string | readonly string[];
    }
  ).__SKELETON_COCKPIT_ORIGINS__;

  const raw = Array.isArray(configured)
    ? configured
    : typeof configured === 'string'
      ? configured.split(',')
      : [];

  const origins = new Set<string>();
  for (const entry of raw) {
    if (typeof entry !== 'string') continue;
    const normalized = normalizeOrigin(entry.trim());
    if (normalized !== null) origins.add(normalized);
  }
  return [...origins];
}

/** Only relative, same-origin application paths are accepted. */
export function isSafeCockpitPath(path: string): boolean {
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')) {
    return false;
  }
  try {
    const resolved = new URL(path, FALLBACK_ORIGIN);
    return resolved.origin === FALLBACK_ORIGIN;
  } catch {
    return false;
  }
}

function resolveParentOrigin(allowedParentOrigins: readonly string[]): string | null {
  if (typeof window === 'undefined' || typeof document === 'undefined') return null;
  if (window.parent === window) return null;

  const allowed = new Set<string>();
  const ownOrigin = normalizeOrigin(window.location.origin);
  if (ownOrigin !== null) allowed.add(ownOrigin);
  for (const value of allowedParentOrigins) {
    const origin = normalizeOrigin(value);
    if (origin !== null) allowed.add(origin);
  }

  const candidates: string[] = [];
  const location = window.location as LocationWithAncestors;
  if (location.ancestorOrigins && location.ancestorOrigins.length > 0) {
    candidates.push(location.ancestorOrigins[0]);
  }
  if (document.referrer) {
    const referrerOrigin = normalizeOrigin(document.referrer);
    if (referrerOrigin !== null) candidates.push(referrerOrigin);
  }

  for (const candidate of candidates) {
    const origin = normalizeOrigin(candidate);
    if (origin !== null && allowed.has(origin)) return origin;
  }
  return null;
}

function isEnvelope(value: unknown): value is BridgeRecord {
  return (
    isRecord(value) &&
    value.channel === COCKPIT_BRIDGE_CHANNEL &&
    value.version === COCKPIT_BRIDGE_VERSION &&
    typeof value.type === 'string'
  );
}

function historyStateWithRoot(state: unknown, isRoot: boolean): BridgeRecord {
  return {
    ...(isRecord(state) ? state : {}),
    [HISTORY_ROOT_KEY]: isRoot,
  };
}

/**
 * Installs a strict host ↔ guest bridge and returns its disposer.
 *
 * Protocol from host:
 * - `hello` -> guest re-announces location, routes, and readiness.
 * - `navigate` + safe relative `path` -> guest navigation.
 * - `history` + delta -1/1 -> bounded browser history movement.
 *
 * Protocol from guest:
 * - `location`, `routes`, `ready`.
 */
export function installCockpitPreviewBridge(
  options: CockpitBridgeOptions = {},
): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => {};

  const parentOrigin = resolveParentOrigin(options.allowedParentOrigins ?? []);
  if (parentOrigin === null) return () => {};

  const originalPushState = window.history.pushState.bind(window.history);
  const originalReplaceState = window.history.replaceState.bind(window.history);

  const isAtHistoryRoot = () => {
    const state = window.history.state;
    return isRecord(state) && state[HISTORY_ROOT_KEY] === true;
  };

  try {
    const current = window.history.state;
    const alreadyTagged = isRecord(current) && HISTORY_ROOT_KEY in current;
    if (!alreadyTagged) {
      originalReplaceState(
        historyStateWithRoot(current, window.history.length <= 1),
        '',
        window.location.href,
      );
    }
  } catch {
    // A restrictive host may deny history mutation. The bridge remains usable.
  }

  const post = (message: BridgeRecord) => {
    window.parent.postMessage(
      {
        channel: COCKPIT_BRIDGE_CHANNEL,
        version: COCKPIT_BRIDGE_VERSION,
        ...message,
      },
      parentOrigin,
    );
  };

  const reportLocation = () => {
    post({
      type: 'location',
      path: window.location.pathname || '/',
      search: window.location.search,
      hash: window.location.hash,
    });
  };

  const reportRoutes = () => {
    const routes = new Set<string>();
    for (const route of options.getRoutePaths?.() ?? []) {
      if (isSafeCockpitPath(route)) routes.add(route);
    }
    post({ type: 'routes', paths: [...routes].sort() });
  };

  const announce = () => {
    reportLocation();
    reportRoutes();
    post({ type: 'ready' });
  };

  const defaultNavigate = (path: string) => {
    if (!isSafeCockpitPath(path)) return;
    try {
      const url = new URL(path, window.location.origin);
      if (url.origin !== window.location.origin) return;
      const next = `${url.pathname}${url.search}${url.hash}`;
      window.history.pushState(window.history.state, '', next);
      window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
    } catch {
      // Malformed or unsupported navigation is deliberately ignored.
    }
  };

  const navigate = (path: string) => {
    if (!isSafeCockpitPath(path)) return;
    if (options.navigate) {
      options.navigate(path);
      return;
    }
    defaultNavigate(path);
  };

  const onMessage = (event: MessageEvent) => {
    if (event.source !== window.parent || event.origin !== parentOrigin) return;
    if (!isEnvelope(event.data)) return;

    if (event.data.type === 'hello') {
      announce();
      return;
    }

    if (event.data.type === 'navigate') {
      if (typeof event.data.path !== 'string') return;
      navigate(event.data.path);
      queueMicrotask(reportLocation);
      return;
    }

    if (event.data.type === 'history') {
      if (event.data.delta !== -1 && event.data.delta !== 1) return;
      if (event.data.delta === -1 && isAtHistoryRoot()) return;
      window.history.go(event.data.delta);
    }
  };

  const onLocationChange = () => reportLocation();

  window.history.pushState = (data: unknown, unused: string, url?: string | URL | null) => {
    originalPushState(historyStateWithRoot(data, false), unused, url);
    reportLocation();
  };
  window.history.replaceState = (data: unknown, unused: string, url?: string | URL | null) => {
    originalReplaceState(
      historyStateWithRoot(data, isAtHistoryRoot()),
      unused,
      url,
    );
    reportLocation();
  };

  window.addEventListener('message', onMessage);
  window.addEventListener('popstate', onLocationChange);
  window.addEventListener('hashchange', onLocationChange);
  announce();

  return () => {
    window.removeEventListener('message', onMessage);
    window.removeEventListener('popstate', onLocationChange);
    window.removeEventListener('hashchange', onLocationChange);
    window.history.pushState = originalPushState;
    window.history.replaceState = originalReplaceState;
  };
}
