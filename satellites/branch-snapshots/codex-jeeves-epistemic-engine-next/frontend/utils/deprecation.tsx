/**
 * deprecation — central registry of components / utils / endpoints that
 * are slated for removal, with one-line documentation per entry so
 * future maintainers can answer "what replaced this?" without grepping.
 *
 * Two ways to use:
 *
 *   1. Wrap a deprecated React component:
 *        export default deprecated(LegacyFooModal, {
 *          since: '2026-02', removeBy: '2026-06',
 *          replaceWith: '/foo native route',
 *          reason: 'modal converted to native route',
 *        });
 *      → first mount logs a console warning + telemetry event;
 *        subsequent mounts (same session) are silent.
 *
 *   2. Mark a non-component (helper, hook, endpoint):
 *        deprecatedFn('utils/oldHelper', { since: '2026-02', replaceWith: 'utils/newHelper' });
 *      → fires once on module evaluation.
 *
 * Inspect at runtime:
 *      getDeprecationLog() → all events seen this session.
 */
import React from 'react';
import { recordEvent } from './modalLogger';

export interface DeprecationInfo {
  /** Date (YYYY-MM) the API was first deprecated. */
  since:        string;
  /** Date (YYYY-MM) the API will be removed. Pure documentation. */
  removeBy?:    string;
  /** Pointer to the replacement (e.g. "/foo native route" or "useNewBar"). */
  replaceWith?: string;
  /** One-line reason. */
  reason?:      string;
}

const _seen = new Set<string>();
const _log: Array<{ name: string; info: DeprecationInfo; ts: number }> = [];

function _emit(name: string, info: DeprecationInfo): void {
  const key = name + (info.since || '');
  if (_seen.has(key)) return;
  _seen.add(key);
  _log.push({ name, info, ts: Date.now() });
  const msg =
    `[deprecated] ${name} — since ${info.since}` +
    (info.removeBy ? ` · remove by ${info.removeBy}` : '') +
    (info.replaceWith ? ` · use ${info.replaceWith}` : '') +
    (info.reason ? ` · ${info.reason}` : '');
  // eslint-disable-next-line no-console
  console.warn(msg);
  try {
    recordEvent(name, 'deprecation_used', 'warn', info as any);
  } catch { /* swallow */ }
}

export function deprecated<P extends object>(
  Component: React.ComponentType<P>,
  info: DeprecationInfo,
): React.FC<P> {
  const name = Component.displayName || Component.name || 'AnonymousComponent';
  const Wrapped: React.FC<P> = (props) => {
    _emit(name, info);
    return <Component {...props} />;
  };
  Wrapped.displayName = `Deprecated(${name})`;
  return Wrapped;
}

/** Mark a non-React function / module as deprecated. Call from module top. */
export function deprecatedFn(name: string, info: DeprecationInfo): void {
  _emit(name, info);
}

export function getDeprecationLog(): typeof _log {
  return _log.slice();
}
