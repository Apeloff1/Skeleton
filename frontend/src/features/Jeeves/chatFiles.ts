import { Platform, Share } from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { API_BASE } from '../../utils/apiBase';
import { authHeaders } from '../../auth/gameforgeAuth';
import type { Artifact, Conversation } from './workspace';
import { transcript } from './workspace';

export const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;
export const CHAT_ATTACHMENT_MIMES = [
  'text/plain', 'text/markdown', 'text/csv', 'application/json', 'application/pdf',
  'image/png', 'image/jpeg', 'image/webp', 'audio/wav',
] as const;

export type UploadedChatAttachment = {
  attachmentId: string;
  attachmentRef: string;
  filename: string;
  mimeType: string;
  sizeBytes: number;
  expiresAt: string;
  preview: string;
  capabilities: string[];
};

export type ChatAttachmentUploadInput = {
  threadId: string;
  filename: string;
  mimeType: string;
  base64: string;
  rightsAcknowledged: true;
  uploadId?: string;
  signal?: AbortSignal;
  headers?: Record<string, string>;
};

type AttachmentRequestOptions = { signal?: AbortSignal; headers?: Record<string, string> };

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
  if (!base64 || base64.length > Math.ceil(MAX_ATTACHMENT_BYTES / 3) * 4
    || base64.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(base64)) {
    throw new Error('Choose a valid file smaller than 5 MB.');
  }
  const padding = base64.endsWith('==') ? 2 : base64.endsWith('=') ? 1 : 0;
  if (base64.length / 4 * 3 - padding > MAX_ATTACHMENT_BYTES) throw new Error('Choose a file smaller than 5 MB.');
}


function attachmentId(reference: string): string {
  const id = reference.replace(/^chat-attachment:\/\//, '');
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id)) {
    throw new Error('This attachment reference is invalid.');
  }
  return id;
}

function newUploadId(): string {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  // Upload IDs provide retry identity; they are never an authorization token.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, kind => {
    const random = Math.floor(Math.random() * 16);
    return (kind === 'x' ? random : (random & 3) | 8).toString(16);
  });
}

async function fileRequest(path: string, init: RequestInit, options: AttachmentRequestOptions = {}): Promise<any> {
  const response = await fetch(`${API_BASE}/api/ai/attachments${path}`, {
    ...init,
    headers: authHeaders({ 'Content-Type': 'application/json', ...options.headers }),
    signal: options.signal,
  });
  const raw = await response.text();
  if (raw.length > 128 * 1024) throw new Error('The attachment response exceeded its size limit.');
  let data: any;
  try { data = raw ? JSON.parse(raw) : {}; } catch { throw new Error('The server returned an invalid attachment response.'); }
  if (!response.ok) {
    const message = typeof data?.detail === 'string' ? data.detail : `Attachment request failed (${response.status}).`;
    throw new Error(message);
  }
  return data;
}

function uploadProjection(data: any): UploadedChatAttachment {
  const id = attachmentId(String(data?.attachment_id || ''));
  const reference = `chat-attachment://${id}`;
  if (data?.attachment_ref !== reference || typeof data?.filename !== 'string'
    || typeof data?.media_type !== 'string' || !Number.isInteger(data?.size_bytes)
    || data.size_bytes < 1 || data.size_bytes > MAX_ATTACHMENT_BYTES
    || !Array.isArray(data?.capabilities) || data.capabilities.some((value: unknown) => typeof value !== 'string')
    || typeof data?.expires_at !== 'string' || !Number.isFinite(Date.parse(data.expires_at))) {
    throw new Error('The server returned an invalid attachment identity.');
  }
  return {
    attachmentId: id, attachmentRef: reference, filename: data.filename, mimeType: data.media_type,
    sizeBytes: data.size_bytes, expiresAt: data.expires_at, preview: String(data.preview || '').slice(0, 500),
    capabilities: [...data.capabilities],
  };
}

/** Upload once to the canonical conversation; only references may be cached. */
export async function uploadChatAttachment(input: ChatAttachmentUploadInput): Promise<UploadedChatAttachment> {
  if (!input.threadId?.trim()) throw new Error('Create a conversation before attaching a file.');
  if (input.rightsAcknowledged !== true) throw new Error('Confirm permission to use this file in the conversation.');
  const mime = input.mimeType.toLowerCase().split(';', 1)[0].trim();
  if (!(CHAT_ATTACHMENT_MIMES as readonly string[]).includes(mime)) throw new Error('This file type is not supported.');
  validateAttachment(input.base64);
  const data = await fileRequest('', {
    method: 'POST',
    body: JSON.stringify({
      thread_id: input.threadId, filename: safeFilename(input.filename), media_type: mime,
      base64: input.base64, rights_acknowledged: true, upload_id: input.uploadId || newUploadId(),
    }),
  }, input);
  return uploadProjection(data);
}

/** Upload a batch of files ("Upload all files") to the canonical conversation. */
export async function uploadAllChatAttachments(inputs: ChatAttachmentUploadInput[]): Promise<UploadedChatAttachment[]> {
  if (!Array.isArray(inputs) || inputs.length === 0) {
    throw new Error('Select at least one file to upload.');
  }
  const uploaded: UploadedChatAttachment[] = [];
  for (const input of inputs.slice(0, 4)) {
    if (input.signal?.aborted) break;
    uploaded.push(await uploadChatAttachment(input));
  }
  return uploaded;
}

export async function readChatAttachment(reference: string, threadId: string, options: AttachmentRequestOptions = {}): Promise<UploadedChatAttachment> {
  const data = await fileRequest(`/${attachmentId(reference)}?thread_id=${encodeURIComponent(threadId)}`, { method: 'GET' }, options);
  return uploadProjection(data);
}

export async function deleteChatAttachment(reference: string, threadId: string, options: AttachmentRequestOptions = {}): Promise<void> {
  await fileRequest(`/${attachmentId(reference)}?thread_id=${encodeURIComponent(threadId)}`, { method: 'DELETE' }, options);
}

export async function attachmentCapabilities(options: AttachmentRequestOptions = {}): Promise<any> {
  return fileRequest('/capabilities', { method: 'GET' }, options);
}

/** Read a user-selected local file; arbitrary remote URLs are never fetched. */
export async function readPickedAttachment(asset: { uri: string; size?: number; file?: Blob }): Promise<string> {
  if (typeof asset.size === 'number' && asset.size > MAX_ATTACHMENT_BYTES) throw new Error('Choose a file smaller than 5 MB.');
  let encoded: string;
  if (Platform.OS === 'web') {
    if (!asset.file && !asset.uri.startsWith('blob:')) throw new Error('Choose a local file from your device.');
    const blob = asset.file || await (await fetch(asset.uri)).blob();
    if (blob.size > MAX_ATTACHMENT_BYTES) throw new Error('Choose a file smaller than 5 MB.');
    encoded = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
      reader.onerror = () => reject(new Error('The selected file could not be read.'));
      reader.onabort = () => reject(new Error('Reading the file was cancelled.'));
      reader.readAsDataURL(blob);
    });
  } else {
    if (!/^(file|content):\/\//.test(asset.uri)) throw new Error('Choose a local file from your device.');
    const info = await FileSystem.getInfoAsync(asset.uri);
    if (!info.exists || ('size' in info && typeof info.size === 'number' && info.size > MAX_ATTACHMENT_BYTES)) {
      throw new Error('The selected file is missing or larger than 5 MB.');
    }
    encoded = await FileSystem.readAsStringAsync(asset.uri, { encoding: FileSystem.EncodingType.Base64 });
  }
  validateAttachment(encoded);
  return encoded;
}

/** Save only a bounded, authorized canonical JSON/Markdown export already checked by its client. */
export async function saveChatExport(file: { filename: string; mediaType: string; content: string }): Promise<void> {
  const mime = file.mediaType.split(';')[0].trim();
  if (!['application/json', 'text/markdown'].includes(mime) || !file.content || new TextEncoder().encode(file.content).byteLength > 8 * 1024 * 1024) throw new Error('The conversation export is invalid or too large.');
  const filename = safeFilename(file.filename);
  if (Platform.OS === 'web') { download(new Blob([file.content], { type: mime + ';charset=utf-8' }), filename); return; }
  if (!FileSystem.cacheDirectory || !await Sharing.isAvailableAsync()) { await Share.share({ title: filename, message: file.content }); return; }
  const uri = FileSystem.cacheDirectory + Date.now() + '-' + filename;
  try { await FileSystem.writeAsStringAsync(uri, file.content, { encoding: FileSystem.EncodingType.UTF8 }); await Sharing.shareAsync(uri, { mimeType: mime, dialogTitle: 'Save conversation' }); }
  finally { await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {}); }
}
