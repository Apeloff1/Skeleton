/** Account-scoped image bytes. Private API URLs never become image sources. */
import { API_BASE } from '../utils/apiBase';
import { prepareApiRequest } from '../utils/apiClient';

export const MAX_PRIVATE_IMAGE_BYTES = 4 * 1024 * 1024;
export const MAX_PRIVATE_IMAGE_PIXELS = 16 * 1024 * 1024;
export const PRIVATE_IMAGE_TIMEOUT_MS = 15_000;
const ID = '[A-Za-z0-9_-]{1,128}';
const PROJECT_IMAGE = new RegExp(`^/api/playable/${ID}/(?:cover\\.png|card\\.png|cover/opt/(?:0|[1-9][0-9]{0,3})\\.png)$`);
const GENESIS_IMAGE = new RegExp(`^/api/assets/genesis/${ID}\\.png$`);
const SCORECARD_IMAGE = new RegExp(`^/api/snowball/${ID}/scorecard\\.png$`);
const WORLD_IMAGES = new Set(['/api/worldforge/render', '/api/worldforge/render.gif', '/api/worldforge/heightmap.png']);
const WORLD_QUERY = new Set(['scale', 'seed', 'size', 'palette', 'climate', 'sea_level', 'mountain_level', 'moisture_bias',
  'temperature_bias', 'river_density', 'settlement_density', 'features', 'mode', 'layer', 'zoom', 'pan_x', 'pan_y', 'q', 'master']);
const MIME_TYPES = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp']);

/** Exact configured-backend routes only. Credentials and signed URLs are never
 * accepted as cache-busting query values or redirected to another service. */
export function privateImageUrl(uri: string): string {
  if (typeof uri !== 'string' || uri.length > 4096) throw new Error('Invalid private image address.');
  let backend: URL, target: URL;
  try { backend = new URL(API_BASE); target = new URL(uri, `${API_BASE}/`); }
  catch { throw new Error('Invalid private image address.'); }
  const prefix = backend.pathname.replace(/\/$/, '');
  if (!['http:', 'https:'].includes(target.protocol) || target.origin !== backend.origin || target.username || target.password
    || target.hash || target.search.length > 2048 || !target.pathname.startsWith(`${prefix}/`)) throw new Error('Invalid private image address.');
  const pathname = target.pathname.slice(prefix.length);
  const world = WORLD_IMAGES.has(pathname);
  if (!(world || PROJECT_IMAGE.test(pathname) || GENESIS_IMAGE.test(pathname) || SCORECARD_IMAGE.test(pathname))) {
    throw new Error('Invalid private image address.');
  }
  const seen = new Set<string>();
  target.searchParams.forEach((value, key) => {
    if (seen.has(key) || !(world ? WORLD_QUERY.has(key) : key === 'v') || value.length > (world ? 256 : 64)
      || !/^[A-Za-z0-9_.+,-]*$/.test(value)) throw new Error('Invalid private image address.');
    seen.add(key);
  });
  return target.href;
}

function aborted(): Error { return new Error('Private image observation cancelled.'); }
function oversized(): Error { return new Error('The private image exceeds the preview limit.'); }

/** Native adapters without a streamed body still buffer inside their platform;
 * their completed bytes are checked before any base64/data-URI allocation. */
export async function readPrivateImageBytes(response: Response, signal?: AbortSignal): Promise<Uint8Array> {
  if (signal?.aborted) throw aborted();
  const length = response.headers?.get?.('content-length');
  if (length !== null && length !== undefined && (!/^[0-9]{1,12}$/.test(length) || Number(length) > MAX_PRIVATE_IMAGE_BYTES)) {
    try { void response.body?.cancel().catch(() => {}); } catch {}
    throw oversized();
  }
  if (!response.body || typeof response.body.getReader !== 'function') {
    const buffer = await response.arrayBuffer();
    if (signal?.aborted) throw aborted();
    if (!buffer.byteLength || buffer.byteLength > MAX_PRIVATE_IMAGE_BYTES) throw oversized();
    return new Uint8Array(buffer);
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let block = new Uint8Array(64 * 1024), blockLength = 0;
  let bytes = 0, chunkCount = 0, complete = false;
  const cancel = () => { try { void reader.cancel().catch(() => {}); } catch {} };
  signal?.addEventListener('abort', cancel, { once: true });
  try {
    for (;;) {
      const chunk = await reader.read();
      if (signal?.aborted) throw aborted();
      if (chunk.done) { complete = true; break; }
      if (++chunkCount > 65536) throw new Error('The private image response is excessively fragmented.');
      bytes += chunk.value.byteLength;
      if (bytes > MAX_PRIVATE_IMAGE_BYTES) throw oversized();
      // Fixed blocks avoid both millions of tiny retained rows and repeatedly
      // copying a growing row when a native adapter trickles individual bytes.
      for (let offset = 0; offset < chunk.value.byteLength;) {
        const take = Math.min(block.byteLength - blockLength, chunk.value.byteLength - offset);
        block.set(chunk.value.subarray(offset, offset + take), blockLength); blockLength += take; offset += take;
        if (blockLength === block.byteLength) { chunks.push(block); block = new Uint8Array(64 * 1024); blockLength = 0; }
      }
    }
    if (!bytes) throw new Error('The private image is empty.');
    if (blockLength) chunks.push(block.subarray(0, blockLength));
    const result = new Uint8Array(bytes);
    let offset = 0;
    for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.byteLength; }
    return result;
  } finally { signal?.removeEventListener('abort', cancel); if (!complete) cancel(); try { reader.releaseLock(); } catch {} }
}

function imageSignature(bytes: Uint8Array, mime: string): boolean {
  const begins = (...expected: number[]) => expected.every((value, index) => bytes[index] === value);
  const pixels = (width: number, height: number) => width > 0 && height > 0 && width <= 8192 && height <= 8192 && width * height <= MAX_PRIVATE_IMAGE_PIXELS;
  if (mime === 'image/png') {
    if (bytes.length < 24 || !begins(137, 80, 78, 71, 13, 10, 26, 10)
      || bytes[12] !== 73 || bytes[13] !== 72 || bytes[14] !== 68 || bytes[15] !== 82) return false;
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    return pixels(view.getUint32(16), view.getUint32(20));
  }
  if (mime === 'image/jpeg') return begins(255, 216, 255);
  if (mime === 'image/gif') return bytes.length >= 10 && begins(71, 73, 70, 56) && [55, 57].includes(bytes[4]) && bytes[5] === 97
    && pixels(bytes[6] | bytes[7] << 8, bytes[8] | bytes[9] << 8);
  return begins(82, 73, 70, 70) && bytes[8] === 87 && bytes[9] === 69 && bytes[10] === 66 && bytes[11] === 80;
}

function base64(bytes: Uint8Array): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  const parts: string[] = []; let part = '';
  for (let index = 0; index < bytes.length; index += 3) {
    const a = bytes[index], b = bytes[index + 1], c = bytes[index + 2];
    part += alphabet[a >> 2] + alphabet[((a & 3) << 4) | ((b ?? 0) >> 4)]
      + (index + 1 < bytes.length ? alphabet[((b & 15) << 2) | ((c ?? 0) >> 6)] : '=')
      + (index + 2 < bytes.length ? alphabet[c & 63] : '=');
    if (part.length >= 8192) { parts.push(part); part = ''; }
  }
  if (part) parts.push(part);
  return parts.join('');
}

export async function loadPrivateImage(uri: string, signal?: AbortSignal): Promise<string> {
  const url = privateImageUrl(uri);
  const controller = new AbortController();
  let timedOut = false;
  let cancel: (error: Error) => void = () => {};
  const cancelled = new Promise<never>((_, reject) => { cancel = reject; });
  const abort = () => { controller.abort(); cancel(timedOut ? new Error('The private image request timed out.') : aborted()); };
  signal?.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(() => { timedOut = true; abort(); }, PRIVATE_IMAGE_TIMEOUT_MS);
  let session: Awaited<ReturnType<typeof prepareApiRequest>> | undefined;
  const request = (async () => {
    if (signal?.aborted) { abort(); throw aborted(); }
    session = await prepareApiRequest(url, { Accept: 'image/png,image/jpeg,image/gif,image/webp' }, controller.signal);
    session.signal.addEventListener('abort', abort, { once: true });
    if (!session.current()) throw aborted();
    const response = await fetch(url, { method: 'GET', headers: session.headers, signal: controller.signal,
      redirect: 'error', credentials: 'omit', cache: 'no-store' });
    if (!session.current()) throw aborted();
    if (!response.ok) throw new Error('The private image could not be loaded. Sign in and try again.');
    const mime = (response.headers.get('content-type') || '').split(';', 1)[0].trim().toLowerCase();
    if (!MIME_TYPES.has(mime)) throw new Error('The private image format is unsupported.');
    const bytes = await readPrivateImageBytes(response, controller.signal);
    if (!session.current() || controller.signal.aborted) throw aborted();
    if (!imageSignature(bytes, mime)) throw new Error('The private image content is invalid.');
    return `data:${mime};base64,${base64(bytes)}`;
  })();
  try { return await Promise.race([request, cancelled]); }
  catch (error) {
    if (controller.signal.aborted || session && !session.current()) throw timedOut ? new Error('The private image request timed out.') : aborted();
    // Adapter exceptions may echo bearer headers; only authored failures escape.
    if (error instanceof Error && /^(The private image |Invalid private image )/.test(error.message)) throw error;
    throw new Error('The private image could not be loaded. Sign in and try again.');
  } finally {
    clearTimeout(timer); signal?.removeEventListener('abort', abort);
    session?.signal.removeEventListener('abort', abort); session?.dispose(); controller.abort();
  }
}
