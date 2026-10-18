import { Platform, Share } from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { safeFilename } from './chatFiles';

export type ChatExportFile = { filename: string; mimeType: string; content: string };

/** Save only the document returned by the authorized server export operation. */
export async function saveChatExport(file: ChatExportFile): Promise<void> {
  const mimeType = file.mimeType.split(';', 1)[0].trim().toLowerCase();
  if (!['application/json', 'text/markdown'].includes(mimeType)
    || typeof file.content !== 'string' || !file.content
    || new TextEncoder().encode(file.content).byteLength > 8 * 1024 * 1024) {
    throw new Error('The conversation export is empty or exceeds the download limit.');
  }
  const filename = safeFilename(file.filename);
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(new Blob([file.content], { type: mimeType + ';charset=utf-8' }));
    const link = document.createElement('a');
    try {
      link.href = url; link.download = filename;
      document.body.appendChild(link); link.click();
    } finally {
      link.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000);
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
    await Sharing.shareAsync(uri, { mimeType, dialogTitle: 'Save conversation' });
  } finally {
    await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {});
  }
}
