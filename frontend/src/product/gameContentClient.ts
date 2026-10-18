import { CryptoDigestAlgorithm, digest } from 'expo-crypto';
import * as FileSystem from 'expo-file-system/legacy';
import { Platform } from 'react-native';
import { API_BASE } from '../utils/apiBase';
import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import { ChatClientError } from './chatErrors';
import { type LearningProject, learningRequestKey } from './gameLearningClient';

export type ContentFile = { path: string; bytes: number; uri: string; blob?: Blob };
export type ContentUpload = {
  upload_id: string; status: string; chunk_bytes: number; total_bytes: number; entrypoint: string; expires_at?: string;
  files: { path: string; bytes: number; sha256?: string; chunk_count: number; received_chunks: number[]; missing_chunks: number[] }[];
};
const ROOT = '/api/game-learning';
export const CONTENT_FILE_LIMIT = 2 * 1024 ** 3;
export const CONTENT_BUNDLE_LIMIT = 4 * 1024 ** 3;
const CHUNK = 1024 ** 2;
function invalid(message: string): never { throw new ChatClientError(message, { kind: 'protocol', retryable: false }); }
function validate(upload: ContentUpload): ContentUpload {
  if (!upload || typeof upload.upload_id !== 'string' || !upload.upload_id || typeof upload.status !== 'string' || upload.chunk_bytes !== CHUNK
    || !Number.isSafeInteger(upload.total_bytes) || upload.total_bytes < 1 || upload.total_bytes > CONTENT_BUNDLE_LIMIT
    || !Array.isArray(upload.files) || upload.files.length < 1 || upload.files.length > 64 || typeof upload.entrypoint !== 'string') invalid('The content upload returned an invalid reservation.');
  const paths = new Set<string>();
  for (const file of upload.files) {
    if (!file || typeof file.path !== 'string' || paths.has(file.path) || !Number.isSafeInteger(file.bytes) || file.bytes < 1 || file.bytes > CONTENT_FILE_LIMIT
      || file.chunk_count !== Math.ceil(file.bytes / CHUNK) || !Array.isArray(file.received_chunks) || !Array.isArray(file.missing_chunks)
      || [...file.received_chunks, ...file.missing_chunks].some(index => !Number.isSafeInteger(index) || index < 0 || index >= file.chunk_count)
      || file.received_chunks.length + file.missing_chunks.length !== file.chunk_count || new Set([...file.received_chunks, ...file.missing_chunks]).size !== file.chunk_count) invalid('A content file returned an invalid chunk inventory.');
    paths.add(file.path);
  }
  if (!paths.has(upload.entrypoint) || upload.total_bytes !== upload.files.reduce((sum, file) => sum + file.bytes, 0)) invalid('The content reservation total or entry point is invalid.');
  return upload;
}
async function request(path: string, method: 'POST' | 'GET' | 'PUT' | 'DELETE', body: string | Uint8Array | undefined, token: string, signal?: AbortSignal, headers: Record<string, string> = {}) {
  if (token !== getAuthToken()) throw new Error('Your account changed. Reopen the content upload.');
  const controller = new AbortController(); const abort = () => controller.abort(); const timer = setTimeout(abort, 45000);
  signal?.addEventListener('abort', abort, { once: true }); if (signal?.aborted) abort();
  try {
    const response = await fetch(API_BASE + ROOT + path, { method, headers: authHeaders(headers), body: body as BodyInit | undefined, signal: controller.signal });
    const raw = await response.text(); if (raw.length > 8 * 1024 * 1024) invalid('The upload response exceeds its bound.');
    if (token !== getAuthToken()) throw new Error('Your account changed. Reopen the content upload.');
    let value: Record<string, unknown>; try { value = JSON.parse(raw); } catch { invalid('The content upload returned an unreadable response.'); }
    if (!response.ok) {
      const detail = value.detail as { message?: string } | string | undefined;
      throw new ChatClientError(typeof detail === 'string' ? detail : detail?.message || 'The content upload could not be completed.', { kind: response.status === 409 ? 'conflict' : response.status === 401 || response.status === 403 ? 'authorization' : 'execution', status: response.status, retryable: response.status >= 500 });
    }
    return value;
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }
}
function uploadPath(id: string) { if (!id || id.length > 128) invalid('The content reservation is invalid.'); return '/content-uploads/' + encodeURIComponent(id); }
export async function reserveGameContent(current: LearningProject, files: ContentFile[], entrypoint: string, rightsRefs: string[], signal?: AbortSignal, key = learningRequestKey('content')): Promise<ContentUpload> {
  const result = await request('/projects/' + encodeURIComponent(current.project_id) + '/content-uploads', 'POST', JSON.stringify({ expected_version: current.version, idempotency_key: key, rights_refs: rightsRefs, rights_acknowledged: true, entrypoint, files: files.map(file => ({ path: file.path, bytes: file.bytes })) }), getAuthToken(), signal, { 'Content-Type': 'application/json' });
  return validate(result.upload as ContentUpload);
}
export async function getGameContentUpload(id: string, signal?: AbortSignal): Promise<ContentUpload> {
  const result = await request(uploadPath(id), 'GET', undefined, getAuthToken(), signal); return validate(result.upload as ContentUpload);
}
export async function withdrawGameContentUpload(id: string, signal?: AbortSignal): Promise<void> {
  await request(uploadPath(id), 'DELETE', undefined, getAuthToken(), signal);
}
async function chunk(file: ContentFile, offset: number, length: number): Promise<Uint8Array> {
  if (Platform.OS === 'web') {
    if (!file.blob) throw new Error('Choose the original local files again.');
    if (file.blob.size !== file.bytes) throw new Error('A selected content file changed size.');
    return new Uint8Array(await file.blob.slice(offset, offset + length).arrayBuffer());
  }
  if (!file.uri.startsWith('file://') && !file.uri.startsWith('content://')) throw new Error('Select a local file that supports bounded reads.');
  const raw = await FileSystem.readAsStringAsync(file.uri, { encoding: FileSystem.EncodingType.Base64, position: offset, length });
  if (raw.length > Math.ceil(length / 3) * 4 + 4 || !/^[A-Za-z0-9+/]*={0,2}$/.test(raw) || typeof atob !== 'function') throw new Error('This device cannot read the selected file in bounded chunks.');
  return Uint8Array.from(atob(raw), character => character.charCodeAt(0));
}
export function contentReceivedBytes(upload: ContentUpload): number {
  return upload.files.reduce((total, file) => total + file.received_chunks.reduce((sum, index) => sum + Math.min(CHUNK, file.bytes - index * CHUNK), 0), 0);
}
/** One local file slice and one request at a time; whole content is never buffered. */
export async function transferGameContent(upload: ContentUpload, files: ContentFile[], update: (current: ContentUpload) => void, signal: AbortSignal): Promise<ContentUpload> {
  const token = getAuthToken(); let current = await getGameContentUpload(upload.upload_id, signal);
  if (files.length !== current.files.length || files.some((file, index) => file.path !== current.files[index].path || file.bytes !== current.files[index].bytes)) throw new Error('Resume with the same selected content files and paths.');
  update(current);
  for (let fileIndex = 0; fileIndex < files.length; fileIndex++) {
    for (const index of current.files[fileIndex].missing_chunks) {
      if (signal.aborted || token !== getAuthToken()) throw new Error('The content upload was paused.');
      const file = files[fileIndex]; const length = Math.min(CHUNK, file.bytes - index * CHUNK); const bytes = await chunk(file, index * CHUNK, length);
      if (bytes.byteLength !== length) throw new Error('A local content slice did not match its declared size.');
      const hash = await digest(CryptoDigestAlgorithm.SHA256, bytes as unknown as BufferSource);
      const checksum = Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, '0')).join('');
      const result = await request(uploadPath(current.upload_id) + '/files/' + fileIndex + '/chunks/' + index, 'PUT', bytes, token, signal, { 'Content-Type': 'application/octet-stream', 'X-Chunk-SHA256': checksum });
      current = validate(result.upload as ContentUpload); update(current);
    }
  }
  return current;
}
export async function completeGameContent(id: string, signal?: AbortSignal): Promise<void> {
  await request(uploadPath(id) + '/complete', 'POST', undefined, getAuthToken(), signal);
}
