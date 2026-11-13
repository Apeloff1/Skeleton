/**
 * Bounded, deterministic ZIP "store" archive of the *actual returned*
 * Godot project source. No regeneration, arbitrary paths, compression
 * dependency, browser APIs, network calls or platform filesystem access.
 *
 * Data custody: only call after a successful forge with explicit
 * include_files=true; the API normally removes source bodies.
 */
import type { RunPayload } from './types';

export const MAX_EXPORT_FILES = 256;
export const MAX_EXPORT_SOURCE_BYTES = 8 * 1024 * 1024;
export const MAX_EXPORT_ARCHIVE_BYTES = 9 * 1024 * 1024;
export interface GodotSourceArchive {
  filename: string;
  bytes: Uint8Array;
  fileCount: number;
  sourceBytes: number;
  manifestSha256: string;
}

function utf8(text: string): Uint8Array {
  const out: number[] = [];
  for (let i = 0; i < text.length; i++) {
    const n = text.codePointAt(i)!;
    // Malformed UTF-16 must never be silently encoded as a different file
    // from the source hashed by the canonical Python projector.
    if (n >= 0xd800 && n <= 0xdfff) {
      throw new Error('Godot source contains an invalid UTF-16 surrogate');
    }
    if (n > 0xffff) i++;
    if (n < 0x80) out.push(n);
    else if (n < 0x800) out.push(0xc0 | (n >> 6), 0x80 | (n & 63));
    else if (n < 0x10000) {
      out.push(0xe0 | (n >> 12), 0x80 | ((n >> 6) & 63), 0x80 | (n & 63));
    } else {
      out.push(0xf0 | (n >> 18), 0x80 | ((n >> 12) & 63),
        0x80 | ((n >> 6) & 63), 0x80 | (n & 63));
    }
  }
  return Uint8Array.from(out);
}

// Explicitly initialize a typed table; ArrayLike without indexed entries
// is not portable across TypeScript/JS engines.
const CRC_TABLE = new Uint32Array(256);
for (let i = 0; i < CRC_TABLE.length; i++) {
  let crc = i;
  for (let bit = 0; bit < 8; bit++) {
    crc = crc & 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1;
  }
  CRC_TABLE[i] = crc >>> 0;
}
function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const b of bytes) crc = CRC_TABLE[(crc ^ b) & 255] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}
const WINDOWS_DEVICES = new Set([
  'con', 'nul', 'aux', 'prn', ...Array.from({ length: 9 }, (_, i) => 'com' + (i + 1)),
  ...Array.from({ length: 9 }, (_, i) => 'lpt' + (i + 1)),
]);
function safeSourcePath(path: string): boolean {
  if (typeof path !== 'string' || !path || path.length > 240
      || path.includes('\\') || path.includes(':') || path.startsWith('/')) return false;
  return path.split('/').every(part => part.length > 0
    && !part.startsWith('.') && part.trimEnd() === part && !part.endsWith('.')
    && /^[a-zA-Z0-9_.-]{1,120}$/.test(part)
    && !WINDOWS_DEVICES.has(part.split('.')[0].toLowerCase()));
}
function put16(view: DataView, offset: number, value: number): void {
  view.setUint16(offset, value, true);
}
function put32(view: DataView, offset: number, value: number): void {
  view.setUint32(offset, value >>> 0, true);
}
interface Entry { name: Uint8Array; body: Uint8Array; crc: number; localAt: number }
function zipStore(entries: Entry[], totalBytes: number): Uint8Array {
  const data = new Uint8Array(totalBytes);
  const view = new DataView(data.buffer);
  let offset = 0;
  for (const file of entries) {
    file.localAt = offset;
    put32(view, offset, 0x04034b50);
    put16(view, offset + 4, 20); // ZIP version
    put16(view, offset + 6, 0x0800); // UTF-8 paths
    put16(view, offset + 8, 0); // stored, not compressed
    put16(view, offset + 10, 0); // fixed deterministic time
    put16(view, offset + 12, 0x0021); // 1980-01-01
    put32(view, offset + 14, file.crc);
    put32(view, offset + 18, file.body.length);
    put32(view, offset + 22, file.body.length);
    put16(view, offset + 26, file.name.length);
    put16(view, offset + 28, 0);
    offset += 30;
    data.set(file.name, offset); offset += file.name.length;
    data.set(file.body, offset); offset += file.body.length;
  }
  const centralStart = offset;
  for (const file of entries) {
    put32(view, offset, 0x02014b50);
    put16(view, offset + 4, 20); // made by
    put16(view, offset + 6, 20);
    put16(view, offset + 8, 0x0800);
    put16(view, offset + 10, 0);
    put16(view, offset + 12, 0);
    put16(view, offset + 14, 0x0021);
    put32(view, offset + 16, file.crc);
    put32(view, offset + 20, file.body.length);
    put32(view, offset + 24, file.body.length);
    put16(view, offset + 28, file.name.length);
    put16(view, offset + 30, 0);
    put16(view, offset + 32, 0);
    put16(view, offset + 34, 0);
    put16(view, offset + 36, 0);
    put32(view, offset + 38, 0);
    put32(view, offset + 42, file.localAt);
    offset += 46;
    data.set(file.name, offset); offset += file.name.length;
  }
  const centralBytes = offset - centralStart;
  put32(view, offset, 0x06054b50);
  put16(view, offset + 4, 0);
  put16(view, offset + 6, 0);
  put16(view, offset + 8, entries.length);
  put16(view, offset + 10, entries.length);
  put32(view, offset + 12, centralBytes);
  put32(view, offset + 16, centralStart);
  put16(view, offset + 20, 0);
  offset += 22;
  if (offset !== totalBytes) throw new Error('ZIP source assembly length mismatch');
  return data;
}

export function buildGodotSourceArchive(payload: RunPayload): GodotSourceArchive {
  if (!payload || payload.succeeded !== true) throw new Error('No successful forge run to export');
  if (!payload.source_export || payload.source_export.status !== 'ready') {
    throw new Error('Godot source was not prepared for this run; enable source export before forging');
  }
  if (!payload.files || typeof payload.files !== 'object' || Array.isArray(payload.files)) {
    throw new Error('The returned project has no source files');
  }
  const files = Object.entries(payload.files).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0);
  if (!files.length || files.length > MAX_EXPORT_FILES || !Object.prototype.hasOwnProperty.call(payload.files, 'project.godot')) {
    throw new Error('Source archive exceeds the file budget or lacks project.godot');
  }
  const digest = payload.source_manifest?.sha256;
  if (payload.source_manifest?.schema !== 'skeleton.forge.source_manifest.v1') {
    throw new Error('Unexpected Godot source manifest schema');
  }
  if (typeof digest !== 'string' || !/^[0-9a-f]{64}$/.test(digest)
      || digest !== payload.source_export.manifest_sha256) {
    throw new Error('Export source manifest is unsealed or inconsistent');
  }
  if (payload.source_manifest?.file_count !== files.length
      || payload.source_export.file_count !== files.length) {
    throw new Error('Export file count does not match the source manifest');
  }
  const listed = payload.source_manifest.files;
  if (!listed || typeof listed !== 'object' || Array.isArray(listed)
      || Object.keys(listed).length !== files.length) {
    throw new Error('Manifest file inventory does not match the returned sources');
  }
  const entries: Entry[] = [];
  const casefoldedNames = new Set<string>();
  let sourceBytes = 0;
  let archiveBytes = 22;
  for (const [name, body] of files) {
    if (!safeSourcePath(name) || typeof body !== 'string'
        || !Object.prototype.hasOwnProperty.call(listed, name)
        || !/^[0-9a-f]{64}$/.test(listed[name])) {
      throw new Error('Unsafe or unlisted Godot project source path');
    }
    const foldedName = name.toLowerCase();
    if (casefoldedNames.has(foldedName)) {
      throw new Error('Case-colliding Godot project paths cannot be exported');
    }
    casefoldedNames.add(foldedName);
    const encodedName = utf8(name), encodedBody = utf8(body);
    sourceBytes += encodedBody.length;
    if (sourceBytes > MAX_EXPORT_SOURCE_BYTES) throw new Error('Godot export exceeds the 8 MiB source budget');
    archiveBytes += 76 + 2 * encodedName.length + encodedBody.length;
    if (archiveBytes > MAX_EXPORT_ARCHIVE_BYTES) throw new Error('Godot ZIP archive exceeds its 9 MiB budget');
    entries.push({ name: encodedName, body: encodedBody, crc: crc32(encodedBody), localAt: 0 });
  }
  if (sourceBytes !== payload.source_export.bytes) {
    throw new Error('Export source byte count differs from server custody');
  }
  return {
    filename: 'skeleton-godot-' + digest.slice(0, 16) + '.zip',
    bytes: zipStore(entries, archiveBytes),
    fileCount: entries.length,
    sourceBytes,
    manifestSha256: digest,
  };
}
