/** Explicit user-initiated export of an already owner-authorized crawler source.
 * All bytes must originate from exportCrawlSource() which validates the digest.
 * Files are ephemeral in the native cache and are erased after sharing.
 */
import { Platform, Share } from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import type { SourceExport } from './crawlerClient';

export async function saveCrawlerExport(file: SourceExport): Promise<void> {
  if (!file || typeof file.content !== 'string' || file.content.length > 2_097_152
    || !/^[0-9a-f]{64}$/.test(file.content_digest)
    || !['application/json', 'text/markdown'].includes(file.media_type.split(';')[0].trim())) {
    throw new Error('The source export is not a verified bounded document.');
  }
  const filename = file.filename.replace(/[^a-zA-Z0-9._-]/g, '-').slice(0, 160) || 'captured-source.json';
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(new Blob([file.content], { type: file.media_type }));
    const element = document.createElement('a');
    try {
      element.href = url;
      element.download = filename;
      document.body.appendChild(element);
      element.click();
    } finally {
      element.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    }
    return;
  }
  if (!FileSystem.cacheDirectory || !await Sharing.isAvailableAsync()) {
    await Share.share({ title: filename, message: file.content });
    return;
  }
  const uri = FileSystem.cacheDirectory + Date.now() + '-' + filename;
  try {
    await FileSystem.writeAsStringAsync(uri, file.content, { encoding: FileSystem.EncodingType.UTF8 });
    await Sharing.shareAsync(uri, { mimeType: file.media_type });
  } finally {
    await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => undefined);
  }
}
