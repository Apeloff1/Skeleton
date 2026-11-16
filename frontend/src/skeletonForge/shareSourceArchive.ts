/**
 * Explicit local-only export of a source-sealed Godot project.
 *
 * No new backend request, cloud upload, provider call, or second forge run.
 * Validates the exact SHA-256 of each returned file and the overall source
 * manifest before opening an OS-level share sheet or browser download.
 */
import type { RunPayload } from './types';
import { buildGodotSourceArchive, nativeSourceInventory } from './sourceArchive';

export async function shareGodotSourceArchive(
  payload: RunPayload,
  stillCurrent: () => boolean = () => true,
): Promise<void> {
  if (!stillCurrent()) throw new Error('Godot source export cancelled because the account changed');
  // The builder independently applies a hard file/source/ZIP byte budget
  // before any platform-native dependencies or memory-heavy work.
  // Freeze the exact bounded input before both ZIP construction and
  // asynchronous hashing. The returned HTTP JSON contains plain own fields.
  // Reject an oversized inventory before copying its references.
  if (!payload.files || !payload.source_manifest?.files
      || Object.keys(payload.files).length > 256
      || Object.keys(payload.source_manifest.files).length > 256) {
    throw new Error('Godot source export inventory is missing or oversized');
  }
  const files = Object.freeze({ ...payload.files! });
  const expected = Object.freeze({ ...payload.source_manifest!.files! });
  const nativeInventory = nativeSourceInventory(payload);
  const nativeDigest = payload.playable_source?.source_sha256;
  const snapshot: RunPayload = {
    succeeded: payload.succeeded,
    forge: payload.forge ? { ...payload.forge } : undefined,
    playable_source: payload.playable_source ? { ...payload.playable_source,
      source_files: Object.freeze({ ...payload.playable_source.source_files }) } : undefined,
    files,
    source_manifest: { ...payload.source_manifest, files: expected },
    source_export: payload.source_export ? { ...payload.source_export } : undefined,
  };
  const archive = buildGodotSourceArchive(snapshot);
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
  if (nativeInventory && await Crypto.digestStringAsync(digest, JSON.stringify(nativeInventory)) !== nativeDigest) {
    throw new Error('Godot playable source receipt checksum mismatch');
  }
  if (!stillCurrent()) throw new Error('Godot source export cancelled because the account changed');

  const { Platform } = await import('react-native');
  if (!stillCurrent()) throw new Error('Godot source export cancelled because the account changed');
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
  if (!stillCurrent()) throw new Error('Godot source export cancelled because the account changed');
  // A unique native cache object avoids overlapping share operations
  // clobbering another user/session's ZIP with the same manifest name.
  const uniqueName = archive.filename.replace(/\.zip$/, `-${Crypto.randomUUID()}.zip`);
  const file = new File(Paths.cache, uniqueName);
  // Never retain another authenticated user's authored project in the
  // shared device cache. A share sheet can fail or be cancelled, so cleanup
  // must run for both success and failure, not just auth rotation.
  let created = false;
  try {
    if (file.exists) throw new Error('Godot share temp file already exists');
    file.create();
    created = true;
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
    try { if (created && file.exists) file.delete(); }
    catch { /* Sharing result/error must not be disguised by cache cleanup. */ }
  }
}
