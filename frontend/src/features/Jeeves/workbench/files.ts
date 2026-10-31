import { Platform, Share } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { LIMITS } from './types';
import { WorkbenchError } from './validation';

export function exportName(title: string, extension: string): string {
  const name = title.normalize('NFKD').replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80);
  return `${name || 'jeeves-workbench'}.${extension}`;
}

export async function saveTextFile(content: string, filename: string, mime = 'text/plain'): Promise<void> {
  if (Platform.OS === 'web') {
    const blob = new Blob([content], { type: `${mime};charset=utf-8` });
    const uri = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = uri;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(uri), 1000);
    return;
  }
  if (FileSystem.cacheDirectory && await Sharing.isAvailableAsync()) {
    const path = `${FileSystem.cacheDirectory}${Date.now()}-${filename}`;
    try {
      await FileSystem.writeAsStringAsync(path, content, { encoding: FileSystem.EncodingType.UTF8 });
      await Sharing.shareAsync(path, { mimeType: mime, dialogTitle: 'Export Jeeves workbench' });
    } finally {
      await FileSystem.deleteAsync(path, { idempotent: true }).catch(() => {});
    }
    return;
  }
  if (content.length > 20000) throw new WorkbenchError('File sharing is unavailable. Use a device with file sharing to export this backup.');
  await Share.share({ title: filename, message: content });
}

export async function pickBackupFile(): Promise<{ name: string; text: string } | null> {
  const result = await DocumentPicker.getDocumentAsync({
    type: ['application/json', 'text/plain'],
    copyToCacheDirectory: true,
    multiple: false,
  });
  if (result.canceled || !result.assets[0]) return null;
  const asset = result.assets[0];
  if ((asset.size || 0) > LIMITS.backupBytes) throw new WorkbenchError('Choose a backup smaller than 12 MB.');
  if (Platform.OS === 'web') {
    const file = asset.file || await (await fetch(asset.uri)).blob();
    if (file.size > LIMITS.backupBytes) throw new WorkbenchError('Choose a backup smaller than 12 MB.');
    return { name: asset.name, text: await file.text() };
  }
  const info = await FileSystem.getInfoAsync(asset.uri);
  if (!info.exists || info.isDirectory) throw new WorkbenchError('The selected backup is not a readable file.');
  if (info.size > LIMITS.backupBytes) throw new WorkbenchError('Choose a backup smaller than 12 MB.');
  const text = await FileSystem.readAsStringAsync(asset.uri, { encoding: FileSystem.EncodingType.UTF8 });
  return { name: asset.name, text };
}
