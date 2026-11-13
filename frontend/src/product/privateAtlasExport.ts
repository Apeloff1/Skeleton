/** Explicit private HTML file export. Never navigate/render it at app origin. */
import { Platform } from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import api from '../utils/apiClient';
import { getAuthEpoch, subscribeAuthChanges } from '../auth/gameforgeAuth';

export const MAX_ATLAS_EXPORT_BYTES = 2 * 1024 * 1024;

export async function downloadPrivateAtlas(gameId: string, signal?: AbortSignal): Promise<void> {
  if (typeof gameId !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(gameId)) throw new Error('The atlas project identity is invalid.');
  const epoch = getAuthEpoch();
  const request = new AbortController();
  let objectUrl: string | null = null;
  let temporaryFile: string | null = null;
  let link: HTMLAnchorElement | null = null;
  const erase = () => {
    link?.remove();
    if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; }
    if (temporaryFile) void FileSystem.deleteAsync(temporaryFile, { idempotent: true }).catch(() => {});
  };
  const abort = () => { request.abort(); erase(); };
  const current = () => {
    if (request.signal.aborted || epoch !== getAuthEpoch()) throw new Error('Atlas export cancelled because the account changed.');
  };
  const unsubscribe = subscribeAuthChanges(abort);
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) abort();
  try {
    current();
    const result = await api.get<string>(`/api/snowball/${gameId}/atlas.html`, {
      headers: { Accept: 'text/html' }, responseType: 'text',
      maxResponseChars: MAX_ATLAS_EXPORT_BYTES, timeoutMs: 15_000, retries: 0,
      signal: request.signal,
    });
    current();
    if (!result.ok || typeof result.data !== 'string' || !result.data.trim()
      || new TextEncoder().encode(result.data).byteLength > MAX_ATLAS_EXPORT_BYTES) {
      throw new Error('The atlas could not be downloaded or exceeds its file limit.');
    }
    const filename = `${gameId}-world-atlas.html`;
    if (Platform.OS === 'web') {
      // Octet-stream plus download forces file delivery, rather than granting
      // generated HTML a blob document with access to the application origin.
      objectUrl = URL.createObjectURL(new Blob([result.data], { type: 'application/octet-stream' }));
      link = document.createElement('a');
      current();
      link.href = objectUrl; link.download = filename;
      document.body.appendChild(link); link.click();
      // Let the browser consume the explicit file action before revocation.
      await new Promise<void>(resolve => setTimeout(resolve, 0));
      current();
      return;
    }
    if (!FileSystem.cacheDirectory || !await Sharing.isAvailableAsync()) {
      throw new Error('Atlas file export is unavailable on this device. Open the web app to download it.');
    }
    current();
    temporaryFile = `${FileSystem.cacheDirectory}${Date.now()}-${Math.random().toString(36).slice(2, 10)}-${filename}`;
    try {
      await FileSystem.writeAsStringAsync(temporaryFile, result.data, { encoding: FileSystem.EncodingType.UTF8 });
      current();
      await Sharing.shareAsync(temporaryFile, { mimeType: 'application/octet-stream', dialogTitle: 'Save world atlas HTML' });
      current();
    } finally {
      // Repeat cleanup after an adapter finishes a write that ignored logout.
      await FileSystem.deleteAsync(temporaryFile, { idempotent: true }).catch(() => {});
      temporaryFile = null;
    }
  } finally {
    erase(); unsubscribe(); signal?.removeEventListener('abort', abort);
  }
}
