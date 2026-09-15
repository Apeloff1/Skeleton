/**
 * Skeleton cockpit preview bridge.
 *
 * Distilled from the strongest host/guest preview mechanics in the HyperForge
 * cockpit without importing its router, auth, database, or vendor-specific
 * presentation layer. The bridge is inert on native and top-level web runs.
 * External parents are accepted only through an explicit origin allowlist;
 * same-origin parents are permitted automatically.
 *
 * Project synchronization is intentionally read-only: the guest may publish a
 * canonical WorldGraph revision/hash summary, but the host cannot submit world
 * mutations through this bridge. Mutations remain behind typed application
 * capabilities and backend revision/evidence gates.
 */

export const COCKPIT_BRIDGE_CHANNEL = 'skeleton-cockpit-bridge' as const;
export const COCKPIT_BRIDGE_VERSION = 1 as const;
export const COCKPIT_PROJECT_STATE_EVENT = 'skeleton:cockpit-project-state-change' as const;

const HISTORY_ROOT_KEY = '__skeletonCockpitBridgeRoot';
const FALLBACK_ORIGIN = 'https://skeleton.invalid';
const MAX_REQUEST_ID_LENGTH = 128;
const MAX_PROJECT_ID_LENGTH = 256;
const MAX_PROJECT_SOURCE_LENGTH = 128;
const REQUEST_ID_PATTERN = /^[A-Za-z0-9._:-]+$/;
const PROJECT_ID_PATTERN = /^[A-Za-z0-9._:/-]+$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

type BridgeRecord = Record<string, unknown>;
type CommandStatus = 'accepted' | 'rejected';
type ReceiptCommand = 'navigate' | 'history' | 'project-state-request';

type LocationWithAncestors = Location & {
  ancestorOrigins?: {
    readonly length: number;
    readonly [index: number]: string;
  };
};

export interface CockpitProjectState {
  projectId?: string;
  revision: number;
  semanticHash: string;
  dirty?: boolean;
  source?: string;
}

export interface CockpitBridgeOptions {
  allowedParentOrigins?: readonly string[];
  getRoutePaths?: () => readonly string[];
  getProjectState?: () => CockpitProjectState | null;
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

function readRequestId(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  if (
    trimmed.length === 0 ||
    trimmed.length > MAX_REQUEST_ID_LENGTH ||
    !REQUEST_ID_PATTERN.test(trimmed)
  ) {
    return null;
  }
  return trimmed;
}

function normalizeOptionalBoundedString(
  value: unknown,
  options: { maxLength: number; pattern?: RegExp },
): string | undefined {
  if (value === undefined || value === null || value === '') return undefined;
  if (typeof value !== 'string') return undefined;
  const trimmed = value.trim();
  if (trimmed.length === 0 || trimmed.length > options.maxLength) return undefined;
  if (options.pattern && !options.pattern.test(trimmed)) return undefined;
  return trimmed;
}

export function normalizeCockpitProjectState(value: unknown): CockpitProjectState | null {
  if (!isRecord(value)) return null;
  const revision = value.revision;
  if (
    typeof revision !== 'number' ||
    !Number.isSafeInteger(revision) ||
    revision < 0
  ) {
    return null;
  }
  if (typeof value.semanticHash !== 'string') return null;
  const semanticHash = value.semanticHash.trim().toLowerCase();
  if (!SHA256_PATTERN.test(semanticHash)) return null;

  const projectId = normalizeOptionalBoundedString(value.projectId, {
    maxLength: MAX_PROJECT_ID_LENGTH,
    pattern: PROJECT_ID_PATTERN,
  });
  if (value.projectId !== undefined && value.projectId !== null && projectId === undefined) {
    return null;
  }
  const source = normalizeOptionalBoundedString(value.source, {
    maxLength: MAX_PROJECT_SOURCE_LENGTH,
  });
  if (value.source !== undefined && value.source !== null && source === undefined) {
    return null;
  }
  if (value.dirty !== undefined && typeof value.dirty !== 'boolean') return null;

  return {
    ...(projectId ? { projectId } : {}),
    revision,
    semanticHash,
    ...(typeof value.dirty === 'boolean' ? { dirty: value.dirty } : {}),
    ...(source ? { source } : {}),
  };
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

/** Read the locally published canonical project revision/hash summary. */
export function getConfiguredCockpitProjectState(): CockpitProjectState | null {
  const value = (
    globalThis as typeof globalThis & {
      __SKELETON_COCKPIT_PROJECT_STATE__?: unknown;
    }
  ).__SKELETON_COCKPIT_PROJECT_STATE__;
  return normalizeCockpitProjectState(value);
}

/**
 * Publish local application project state and notify an installed bridge.
 * This API validates before storage and never accepts state from host messages.
 */
export function publishCockpitProjectState(state: CockpitProjectState | null): boolean {
  const target = globalThis as typeof globalThis & {
    __SKELETON_COCKPIT_PROJECT_STATE__?: CockpitProjectState;
  };
  if (state === null) {
    delete target.__SKELETON_COCKPIT_PROJECT_STATE__;
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event(COCKPIT_PROJECT_STATE_EVENT));
    }
    return true;
  }
  const normalized = normalizeCockpitProjectState(state);
  if (normalized === null) return false;
  target.__SKELETON_COCKPIT_PROJECT_STATE__ = normalized;
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(COCKPIT_PROJECT_STATE_EVENT));
  }
  return true;
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
 * - `hello` -> guest re-announces location, routes, project state, readiness.
 * - `navigate` + safe relative `path` -> guest navigation.
 * - `history` + delta -1/1 -> bounded browser history movement.
 * - `project-state-request` -> read-only canonical revision/hash refresh.
 *
 * Trusted commands may carry a bounded `requestId`. When present, the guest
 * emits a `command-result` receipt with accepted/rejected status and reason.
 *
 * Protocol from guest:
 * - `location`, `routes`, `project-state`, `ready`, `command-result`.
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

  const postCommandResult = (
    request: BridgeRecord,
    command: ReceiptCommand,
    status: CommandStatus,
    reason?: string,
  ) => {
    const requestId = readRequestId(request.requestId);
    if (requestId === null) return;
    post({
      type: 'command-result',
      requestId,
      command,
      status,
      ...(reason ? { reason } : {}),
    });
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

  const reportProjectState = () => {
    let state: CockpitProjectState | null = null;
    try {
      state = normalizeCockpitProjectState(options.getProjectState?.() ?? null);
    } catch {
      state = null;
    }
    if (state === null) {
      post({ type: 'project-state', available: false });
      return;
    }
    post({
      type: 'project-state',
      available: true,
      ...(state.projectId ? { projectId: state.projectId } : {}),
      revision: state.revision,
      semanticHash: state.semanticHash,
      ...(typeof state.dirty === 'boolean' ? { dirty: state.dirty } : {}),
      ...(state.source ? { source: state.source } : {}),
      writable: false,
    });
  };

  const announce = () => {
    reportLocation();
    reportRoutes();
    reportProjectState();
    post({ type: 'ready' });
  };

  const defaultNavigate = (path: string): boolean => {
    if (!isSafeCockpitPath(path)) return false;
    try {
      const url = new URL(path, window.location.origin);
      if (url.origin !== window.location.origin) return false;
      const next = `${url.pathname}${url.search}${url.hash}`;
      window.history.pushState(window.history.state, '', next);
      window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
      return true;
    } catch {
      return false;
    }
  };

  const navigate = (path: string): boolean => {
    if (!isSafeCockpitPath(path)) return false;
    if (options.navigate) {
      try {
        options.navigate(path);
        return true;
      } catch {
        return false;
      }
    }
    return defaultNavigate(path);
  };

  const onMessage = (event: MessageEvent) => {
    if (event.source !== window.parent || event.origin !== parentOrigin) return;
    if (!isEnvelope(event.data)) return;

    if (event.data.type === 'hello') {
      announce();
      return;
    }

    if (event.data.type === 'project-state-request') {
      reportProjectState();
      postCommandResult(event.data, 'project-state-request', 'accepted');
      return;
    }

    if (event.data.type === 'navigate') {
      if (typeof event.data.path !== 'string' || !isSafeCockpitPath(event.data.path)) {
        postCommandResult(event.data, 'navigate', 'rejected', 'invalid_path');
        return;
      }
      if (!navigate(event.data.path)) {
        postCommandResult(event.data, 'navigate', 'rejected', 'navigation_failed');
        return;
      }
      postCommandResult(event.data, 'navigate', 'accepted');
      queueMicrotask(reportLocation);
      return;
    }

    if (event.data.type === 'history') {
      if (event.data.delta !== -1 && event.data.delta !== 1) {
        postCommandResult(event.data, 'history', 'rejected', 'invalid_delta');
        return;
      }
      if (event.data.delta === -1 && isAtHistoryRoot()) {
        postCommandResult(event.data, 'history', 'rejected', 'history_floor');
        return;
      }
      window.history.go(event.data.delta);
      postCommandResult(event.data, 'history', 'accepted');
    }
  };

  const onLocationChange = () => reportLocation();
  const onProjectStateChange = () => reportProjectState();

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
  window.addEventListener(COCKPIT_PROJECT_STATE_EVENT, onProjectStateChange);
  announce();

  return () => {
    window.removeEventListener('message', onMessage);
    window.removeEventListener('popstate', onLocationChange);
    window.removeEventListener('hashchange', onLocationChange);
    window.removeEventListener(COCKPIT_PROJECT_STATE_EVENT, onProjectStateChange);
    window.history.pushState = originalPushState;
    window.history.replaceState = originalReplaceState;
  };
}
