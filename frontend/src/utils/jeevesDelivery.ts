/** Strict, bounded decoder for exact-byte package verification on web and native. */
const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
const MAX_BYTES = 8 * 1024 * 1024;
const lookup = new Int16Array(128).fill(-1);
for (let i = 0; i < ALPHABET.length; i++) lookup[ALPHABET.charCodeAt(i)] = i;

export function decodePackageBytes(value: unknown, expectedSize: number): Uint8Array<ArrayBuffer> {
  if (!Number.isSafeInteger(expectedSize) || expectedSize < 1 || expectedSize > MAX_BYTES ||
      typeof value !== 'string' || value.length !== Math.ceil(expectedSize / 3) * 4) {
    throw new Error('Package byte budget or length mismatch');
  }
  const result = new Uint8Array(expectedSize);
  const padding = (3 - expectedSize % 3) % 3;
  const end = value.length - padding;
  for (let i = end; i < value.length; i++) {
    if (value[i] !== '=') throw new Error('Malformed package padding');
  }
  let accumulator = 0, bits = 0, offset = 0;
  for (let i = 0; i < end; i++) {
    const code = value.charCodeAt(i);
    const digit = code < lookup.length ? lookup[code] : -1;
    if (digit < 0) throw new Error('Malformed package alphabet');
    accumulator = (accumulator << 6) | digit;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      if (offset >= result.length) throw new Error('Package length mismatch');
      result[offset++] = (accumulator >> bits) & 255;
      accumulator &= (1 << bits) - 1;
    }
  }
  if (offset !== result.length || accumulator !== 0) throw new Error('Noncanonical package encoding');
  return result;
}

export function hexDigest(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

export function validPackageIdentity(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{32}$/.test(value);
}

export function validPackageName(value: unknown): value is string {
  return typeof value === 'string' && /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,159}$/.test(value);
}
