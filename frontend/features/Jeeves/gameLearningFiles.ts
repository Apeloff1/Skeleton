import { Platform, Share } from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';

/** Read only the file chosen by the user, bounded before and after encoding. */
export async function readLearningFile(asset: { uri: string; size?: number; file?: Blob }, maxBytes: number): Promise<string> {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1 || maxBytes > 16777216) throw new Error('The upload bound is invalid.');
  if (typeof asset.size === 'number' && asset.size > maxBytes) throw new Error(`Choose a file smaller than ${Math.round(maxBytes / 1048576)} MB.`);
  let encoded: string;
  if (Platform.OS === 'web') {
    if (!asset.file && !asset.uri.startsWith('blob:')) throw new Error('Choose a local file from your device.');
    const blob = asset.file || await (await fetch(asset.uri)).blob();
    if (blob.size > maxBytes) throw new Error('This file exceeds the upload limit.');
    encoded = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
      reader.onerror = () => reject(new Error('This file could not be read.'));
      reader.onabort = () => reject(new Error('Reading the file was cancelled.'));
      reader.readAsDataURL(blob);
    });
  } else {
    if (!/^(file|content):\/\//.test(asset.uri)) throw new Error('Choose a local file from your device.');
    const info = await FileSystem.getInfoAsync(asset.uri);
    if (!info.exists || 'size' in info && typeof info.size === 'number' && info.size > maxBytes) throw new Error('The file is missing or exceeds the upload limit.');
    encoded = await FileSystem.readAsStringAsync(asset.uri, { encoding: FileSystem.EncodingType.Base64 });
  }
  const padding = encoded.endsWith('==') ? 2 : encoded.endsWith('=') ? 1 : 0;
  if (!encoded || encoded.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(encoded) || encoded.length / 4 * 3 - padding > maxBytes) throw new Error('The selected file is invalid or too large.');
  return encoded;
}

/** Save exactly the authorized project export returned by the backend. */
export async function saveLearningExport(file: { filename: string; mimeType: string; content: string }): Promise<void> {
  const mimeType = file.mimeType.split(';', 1)[0].trim().toLowerCase();
  if (mimeType !== 'application/json' || !file.content || new TextEncoder().encode(file.content).byteLength > 8 * 1024 * 1024) throw new Error('The project export is invalid or too large.');
  const filename = file.filename.replace(/[^a-zA-Z0-9._-]+/g, '-').replace(/^\.+/, '').slice(0, 160) || 'game-project.json';
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(new Blob([file.content], { type: mimeType + ';charset=utf-8' }));
    const link = document.createElement('a');
    try { link.href = url; link.download = filename; document.body.appendChild(link); link.click(); }
    finally { link.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000); }
    return;
  }
  if (!FileSystem.cacheDirectory || !await Sharing.isAvailableAsync()) { await Share.share({ title: filename, message: file.content }); return; }
  const uri = FileSystem.cacheDirectory + Date.now() + '-' + filename;
  try { await FileSystem.writeAsStringAsync(uri, file.content, { encoding: FileSystem.EncodingType.UTF8 }); await Sharing.shareAsync(uri, { mimeType, dialogTitle: 'Save game project' }); }
  finally { await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {}); }
}

/** Save only content-checked bounded native artifacts returned by their authorized producer. */
export async function saveLearningBinary(filename: string, bytes: Uint8Array): Promise<void> {
  if (!bytes.byteLength || bytes.byteLength > 16 * 1024 * 1024) throw new Error('This build artifact exceeds the device export limit.');
  const name = filename.replace(/[^a-zA-Z0-9._-]+/g, '-').replace(/^\.+/, '').slice(0, 160) || 'game-build.bin';
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(new Blob([bytes as unknown as BlobPart], { type: 'application/octet-stream' })); const link = document.createElement('a');
    try { link.href = url; link.download = name; document.body.appendChild(link); link.click(); }
    finally { link.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000); } return;
  }
  if (!FileSystem.cacheDirectory || !await Sharing.isAvailableAsync() || typeof btoa !== 'function') throw new Error('Artifact sharing is unavailable on this device.');
  let raw = ''; for (let offset = 0; offset < bytes.byteLength; offset += 16384) raw += String.fromCharCode(...bytes.subarray(offset, offset + 16384));
  const uri = FileSystem.cacheDirectory + Date.now() + '-' + name;
  try { await FileSystem.writeAsStringAsync(uri, btoa(raw), { encoding: FileSystem.EncodingType.Base64 }); await Sharing.shareAsync(uri, { mimeType: 'application/octet-stream', dialogTitle: 'Save native game build' }); }
  finally { await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => undefined); }
}
