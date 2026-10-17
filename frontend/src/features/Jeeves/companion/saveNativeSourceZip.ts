/** Authenticated native-source ZIP save shared by both Dragon creator screens. */
import {Platform} from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';

/** Save only bounded local source archives, never browser-origin HTML or ROMs. */
export async function saveNativeSourceZip(
  blob: Blob, name: string, maxBytes = 3_000_000,
): Promise<void> {
  if (!/^dragon-(?:original|native)-[a-f0-9-]+\.zip$/.test(name)) {
    throw new Error('Invalid native source archive name.');
  }
  if (!blob.size || blob.size > maxBytes) {
    throw new Error('Native source ZIP exceeds the allowed download size.');
  }
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(blob);
    try {
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = name;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
    } finally {
      setTimeout(() => URL.revokeObjectURL(url), 15_000);
    }
    return;
  }
  if (!FileSystem.documentDirectory) {
    throw new Error('Device storage for source archives is unavailable.');
  }
  const encoded = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Unable to decode native source archive.'));
    reader.onload = () => {
      if (typeof reader.result !== 'string') {
        reject(new Error('Invalid archive encoding.')); return;
      }
      const separator = reader.result.indexOf(',');
      if (separator < 0) {
        reject(new Error('Invalid archive encoding.')); return;
      }
      resolve(reader.result.slice(separator + 1));
    };
    reader.readAsDataURL(blob);
  });
  const destination = FileSystem.documentDirectory + name;
  await FileSystem.writeAsStringAsync(destination, encoded, {
    encoding: FileSystem.EncodingType.Base64,
  });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(destination, {
      mimeType: 'application/zip',
      dialogTitle: 'Share original Dragon native source',
    });
  }
}
