/**
 * Explicit local-only export of a source-sealed Godot project.
 *
 * No new backend request, cloud upload, provider call, or second forge run.
 * Validates the exact SHA-256 of each returned file and the overall source
 * manifest before opening an OS-level share sheet or browser download.
 */
import type { RunPayload } from './types';
import { buildGodotSourceArchive } from './sourceArchive';

export async function shareGodotSourceArchive(
  payload: RunPayload,
  stillCurrent: () => boolean = () => true,
): Promise<void> {
  if (!stillCurrent()) throw new Error('Godot source export cancelled because the account changed');
  // The builder independently applies a hard file/source/ZIP byte budget
  // before any platform-native dependencies or memory-heavy work.
  const archive = buildGodotSourceArchive(payload);
  const files = payload.files!;
  const expected = payload.source_manifest!.files!;
  const Crypto = await import('expo-crypto');
  const digest = Crypto.CryptoDigestAlgorithm.SHA256;
  const sorted = Object.keys(files).sort();
  for (const path of sorted) {
    if (!stillCurrent()) throw new Error('Godot source export cancelled because the account changed');
    const observed = await Crypto.digestStringAsync(digest, files[path]);
    if (observed !== expected[path]) throw new Error('Godot source file checksum mismatch');
  }
  const sortedChecksums: Record<string, string> = {};
  for (const name of sorted) sortedChecksums[name] = expected[name];
  const overall = await Crypto.digestStringAsync(digest, JSON.stringify(sortedChecksums));
  if (overall !== archive.manifestSha256) {
    throw new Error('Godot source manifest checksum mismatch');
  }
  if (!stillCurrent()) throw new Error('Godot source export cancelled because the account changed');

  const { Platform } = await import('react-native');
  if (Platform.OS === 'web') {
    // Web File Sharing cannot share local file:// URIs. A user-initiated
    // download keeps the source on their device, not on any upload server.
    const download = new Blob([Uint8Array.from(archive.bytes)], { type: 'application/zip' });
    const url = URL.createObjectURL(download);
    try {
      const a = document.createElement('a');
      a.href = url;
      a.download = archive.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } finally {
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    }
    return;
  }

  const Sharing = await import('expo-sharing');
  if (!await Sharing.isAvailableAsync()) {
    throw new Error('Device file sharing is unavailable; your generated game remains in this run');
  }
  if (!stillCurrent()) throw new Error('Godot source export cancelled because the account changed');
  const { File, Paths } = await import('expo-file-system');
  // A unique native cache object avoids overlapping share operations
  // clobbering another user/session's ZIP with the same manifest name.
  const uniqueName = archive.filename.replace(/\.zip$/, `-${Crypto.randomUUID()}.zip`);
  const file = new File(Paths.cache, uniqueName);
  // Never retain another authenticated user's authored project in the
  // shared device cache. A share sheet can fail or be cancelled, so cleanup
  // must run for both success and failure, not just auth rotation.
  try {
    if (file.exists) throw new Error('Godot share temp file already exists');
    file.create();
    file.write(archive.bytes);
    if (!stillCurrent()) {
      throw new Error('Godot source export cancelled because the account changed');
    }
    await Sharing.shareAsync(file.uri, {
      mimeType: 'application/zip',
      dialogTitle: 'Save or share your Godot project source',
      UTI: 'public.zip-archive',
    });
  } finally {
    try { if (file.exists) file.delete(); }
    catch { /* Sharing result/error must not be disguised by cache cleanup. */ }
  }
}
