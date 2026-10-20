import { Platform } from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { ChatClientError } from '../../product/chatErrors';

/** Save exact authorized JSON text. A parsed preview is never a serialization source. */
export async function saveRuntimeJson(file: { content: string; filename: string; maximumBytes: number; dialogTitle: string }, isCurrent: () => boolean): Promise<void> {
  if (!Number.isSafeInteger(file.maximumBytes) || file.maximumBytes < 1 || file.maximumBytes > 1024 * 1024 || !file.content || new TextEncoder().encode(file.content).byteLength > file.maximumBytes) throw new ChatClientError('The runtime export is empty or exceeds its declared file limit.', { kind: 'validation', retryable: false });
  const current = () => { if (!isCurrent()) throw new ChatClientError('The account or runtime view changed before the export could be saved. Refresh and try again.', { kind: 'authorization', retryable: false }); };
  current();
  const filename = file.filename.replace(/[^a-zA-Z0-9._-]/g, '-').replace(/^\.+/, '').slice(0, 160) || 'jeeves-runtime-export.json';
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(new Blob([file.content], { type: 'application/json;charset=utf-8' }));
    const link = document.createElement('a');
    try { current(); link.href = url; link.download = filename; document.body.appendChild(link); link.click(); }
    finally { link.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000); }
    return;
  }
  if (!FileSystem.cacheDirectory || !await Sharing.isAvailableAsync()) throw new ChatClientError('File sharing is unavailable on this device. Open the studio on a device with file export support.', { kind: 'unavailable', retryable: false });
  current();
  const uri = `${FileSystem.cacheDirectory}${Date.now()}-${Math.random().toString(36).slice(2, 10)}-${filename}`;
  try {
    await FileSystem.writeAsStringAsync(uri, file.content, { encoding: FileSystem.EncodingType.UTF8 });
    current();
    await Sharing.shareAsync(uri, { mimeType: 'application/json', dialogTitle: file.dialogTitle });
  } finally { await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {}); }
}
