import { Platform, Share } from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import type { Artifact, Conversation } from './workspace';
import { transcript } from './workspace';

export const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;
const SAFE_MIMES = new Set([
  'image/png', 'image/jpeg', 'image/webp', 'application/pdf',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'text/csv',
]);

export function safeFilename(name: string): string {
  return name.replace(/[^a-zA-Z0-9._-]+/g, '-').replace(/^\.+/, '').slice(0, 100) || 'jeeves-export';
}

function download(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = safeFilename(filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function exportTranscript(conversation: Conversation): Promise<void> {
  const content = transcript(conversation);
  if (Platform.OS === 'web') {
    download(new Blob([content], { type: 'text/markdown;charset=utf-8' }), `${safeFilename(conversation.title)}.md`);
  } else {
    await Share.share({ title: conversation.title, message: content });
  }
}

export async function saveArtifact(artifact: Artifact): Promise<void> {
  if (!SAFE_MIMES.has(artifact.mime)) throw new Error('This file type cannot be downloaded from Jeeves.');
  if (!artifact.base64 || artifact.base64.length > 24 * 1024 * 1024) throw new Error('The artifact is empty or too large to download.');
  const extension = artifact.mime === 'application/pdf' ? '.pdf'
    : artifact.mime.includes('spreadsheet') ? '.xlsx'
      : artifact.mime === 'text/csv' ? '.csv' : `.${artifact.mime.split('/')[1]}`;
  const filename = safeFilename(artifact.filename || `${artifact.title || 'jeeves-artifact'}${extension}`);
  if (Platform.OS === 'web') {
    const bytes = Uint8Array.from(atob(artifact.base64), c => c.charCodeAt(0));
    download(new Blob([bytes], { type: artifact.mime }), filename);
  } else {
    if (!FileSystem.cacheDirectory || !await Sharing.isAvailableAsync()) throw new Error('File sharing is unavailable on this device.');
    const uri = `${FileSystem.cacheDirectory}${Date.now()}-${filename}`;
    try {
      await FileSystem.writeAsStringAsync(uri, artifact.base64, { encoding: FileSystem.EncodingType.Base64 });
      await Sharing.shareAsync(uri, { mimeType: artifact.mime, dialogTitle: artifact.title || 'Save Jeeves artifact' });
    } finally {
      await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {});
    }
  }
}

export function validateAttachment(base64: string): void {
  if (!base64 || base64.length > Math.ceil(MAX_ATTACHMENT_BYTES / 3) * 4) {
    throw new Error('Choose an image or PDF smaller than 5 MB.');
  }
}
