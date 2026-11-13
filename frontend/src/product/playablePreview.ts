/** Private generated games are untrusted, offline documents, never app pages. */
import api from '../utils/apiClient';
import { API_BASE } from '../utils/apiBase';
import { getAuthEpoch } from '../auth/gameforgeAuth';

export const MAX_PLAYABLE_HTML_CHARS = 2 * 1024 * 1024;
export const PLAYABLE_FRAME_SANDBOX = 'allow-scripts allow-pointer-lock';
export const PLAYABLE_FRAME_ALLOW = 'autoplay; fullscreen; gamepad';
export const PLAYABLE_NATIVE_ORIGIN = 'https://playable.invalid/';

// Generated games have a self-contained/offline contract. Inline canvas,
// touch/keyboard controls and procedural audio work without app-origin access.
const CSP = "default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval' data: blob:; style-src 'unsafe-inline'; img-src data: blob:; media-src data: blob:; font-src data:; connect-src 'none'; object-src 'none'; frame-src 'none'; worker-src blob:; base-uri 'none'; form-action 'none'";

// Opaque sandbox origins cannot use browser storage. Supply a fresh, bounded
// in-memory Storage interface per document so legacy high scores still work.
// No values are copied from the application or retained across previews.
const STORAGE_BOOTSTRAP = `(function(){'use strict';function memory(){var rows=new Map(),size=0,limit=65536;return Object.freeze({get length(){return rows.size;},key:function(i){var keys=Array.from(rows.keys());i=Number(i);return Number.isInteger(i)&&i>=0&&i<keys.length?keys[i]:null;},getItem:function(k){k=String(k);return rows.has(k)?rows.get(k):null;},setItem:function(k,v){k=String(k);v=String(v);var previous=rows.has(k)?k.length+rows.get(k).length:0,next=size-previous+k.length+v.length;if(k.length>256||v.length>16384||(!rows.has(k)&&rows.size>=128)||next>limit)throw new DOMException('Preview storage limit exceeded','QuotaExceededError');rows.set(k,v);size=next;},removeItem:function(k){k=String(k);if(rows.has(k)){size-=k.length+rows.get(k).length;rows.delete(k);}},clear:function(){rows.clear();size=0;}});}for(var i=0,names=['localStorage','sessionStorage'];i<names.length;i++){Object.defineProperty(window,names[i],{value:memory(),configurable:false,writable:false});}})();`;

export function preparePlayableDocument(html: string): string {
  if (typeof html !== 'string' || !html.trim() || html.length > MAX_PLAYABLE_HTML_CHARS) {
    throw new Error('The playable document is empty or exceeds the preview limit.');
  }
  // This preamble must precede every untrusted tag and script, including the
  // backend error reporter. Subsequent CSP policies can only tighten it.
  return `<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${CSP}"><script>${STORAGE_BOOTSTRAP}</script>${html}`;
}

function privateRawPath(uri: string): string {
  const backend = new URL(API_BASE);
  const target = new URL(uri, `${API_BASE}/`);
  const prefix = backend.pathname.replace(/\/$/, '');
  if (target.origin !== backend.origin || target.username || target.password || target.search || target.hash
    || !new RegExp(`^${prefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/api/playable/[A-Za-z0-9_-]{1,128}/raw$`).test(target.pathname)) {
    throw new Error('The playable preview address is invalid.');
  }
  return target.pathname.slice(prefix.length);
}

export async function loadPlayableDocument(uri: string, signal?: AbortSignal): Promise<string> {
  const epoch = getAuthEpoch();
  const path = privateRawPath(uri);
  if (signal?.aborted) throw new Error('Playable preview cancelled.');
  const result = await api.get<string>(path, {
    headers: { Accept: 'text/html' }, responseType: 'text', maxResponseChars: MAX_PLAYABLE_HTML_CHARS,
    timeoutMs: 15_000, retries: 0, signal,
  });
  if (signal?.aborted || epoch !== getAuthEpoch()) throw new Error('Playable preview cancelled.');
  if (!result.ok || typeof result.data !== 'string') {
    throw new Error(result.error === 'response_too_large' ? 'The playable document exceeds the preview limit.' : 'The playable preview could not be loaded. Sign in and try again.');
  }
  return preparePlayableDocument(result.data);
}

/** An opaque frame has origin "null". Other previews and page scripts cannot
 * report errors on behalf of this exact frame. */
export function playableMessage(event: { source?: unknown; origin?: unknown; data?: unknown }, frameWindow: unknown): string | null {
  if (!frameWindow || event.source !== frameWindow || event.origin !== 'null') return null;
  const data = event.data;
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
  const value = data as Record<string, unknown>;
  return value.__pl_error === true && typeof value.message === 'string' && value.message.length > 0 && value.message.length <= 1000
    ? value.message.replace(/[\u0000-\u001f\u007f]/g, ' ') : null;
}

export function playableNativeNavigation(url: string): boolean {
  return url === 'about:blank' || url === PLAYABLE_NATIVE_ORIGIN;
}
