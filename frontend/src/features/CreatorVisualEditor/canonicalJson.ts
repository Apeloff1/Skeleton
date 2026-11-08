/**
 * Python-compatible canonical JSON for creator contracts (#807 B019).
 *
 * The backend (skeleton/forge/creator/design_graph.py, semantic_diff.py)
 * serializes with `json.dumps(sort_keys=True, separators=(",", ":"),
 * ensure_ascii=True, allow_nan=False)`. Visual editing must not lose source
 * round-trip fidelity, so this module mirrors that byte format exactly:
 *
 *   - integer vs float lexemes are preserved (`1` stays `1`, `1.0` stays `1.0`)
 *     via the {@link PyFloat} wrapper;
 *   - floats render with Python `repr` rules (`1e-05`, `1.5e+16`, `0.1`);
 *   - non-ASCII text is escaped as lowercase `\uXXXX` (surrogate pairs);
 *   - duplicate object keys are rejected, like `_no_duplicate_object`;
 *   - integers outside the IEEE-754 safe range are rejected instead of being
 *     silently rounded (that would break fidelity).
 *
 * Pure TypeScript, no I/O, no transport.
 */

export const MAX_CANONICAL_TEXT = 4 * 1024 * 1024;
export const MAX_CANONICAL_DEPTH = 64;
export const MAX_CANONICAL_ITEMS = 65_536;

export class CanonicalJsonError extends Error {
  readonly reason: string;
  constructor(message: string, reason: string) {
    super(message);
    this.name = 'CanonicalJsonError';
    this.reason = reason;
  }
}

/** A JSON number whose source lexeme was a float (Python `float`). */
export class PyFloat {
  readonly value: number;
  constructor(value: number) {
    if (!Number.isFinite(value)) {
      throw new CanonicalJsonError('floats must be finite', 'non_finite');
    }
    this.value = value;
    Object.freeze(this);
  }
}

export type JsonScalar = string | number | boolean | null | PyFloat;
export type JsonValue = JsonScalar | JsonValue[] | { [key: string]: JsonValue };

export function isPyFloat(value: unknown): value is PyFloat {
  return value instanceof PyFloat;
}

/** Python `repr(float)` for a finite double. */
export function pyFloatRepr(value: number): string {
  if (!Number.isFinite(value)) {
    throw new CanonicalJsonError('floats must be finite', 'non_finite');
  }
  if (value === 0) return Object.is(value, -0) ? '-0.0' : '0.0';
  // toExponential() without an argument yields the shortest round-trip digits,
  // the same digit string Python's repr uses.
  const [mantissa, expPart] = value.toExponential().split('e');
  const exponent = Number(expPart);
  const negative = mantissa.startsWith('-');
  const digits = mantissa.replace('-', '').replace('.', '');
  const sign = negative ? '-' : '';
  if (exponent >= -4 && exponent < 16) {
    let text: string;
    if (exponent >= 0) {
      const intLen = exponent + 1;
      const intPart = digits.length >= intLen ? digits.slice(0, intLen) : digits + '0'.repeat(intLen - digits.length);
      const frac = digits.length > intLen ? digits.slice(intLen) : '';
      text = `${intPart}.${frac || '0'}`;
    } else {
      text = `0.${'0'.repeat(-exponent - 1)}${digits}`;
    }
    return sign + text;
  }
  const mant = digits.length > 1 ? `${digits[0]}.${digits.slice(1)}` : digits;
  const expSign = exponent < 0 ? '-' : '+';
  const expAbs = Math.abs(exponent);
  return `${sign}${mant}e${expSign}${expAbs < 10 ? '0' : ''}${expAbs}`;
}

function escapeString(value: string): string {
  let out = '"';
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i);
    const ch = value[i];
    if (ch === '"') out += '\\"';
    else if (ch === '\\') out += '\\\\';
    else if (ch === '\n') out += '\\n';
    else if (ch === '\r') out += '\\r';
    else if (ch === '\t') out += '\\t';
    else if (ch === '\b') out += '\\b';
    else if (ch === '\f') out += '\\f';
    else if (code < 0x20 || code > 0x7e) {
      // Python ensure_ascii escapes everything above 0x7f; 0x7f (DEL) stays raw.
      if (code === 0x7f) out += ch;
      else out += `\\u${code.toString(16).padStart(4, '0')}`;
    } else out += ch;
  }
  return `${out}"`;
}

/** Python codepoint ordering for object keys (sort_keys=True). */
export function compareCodepoints(a: string, b: string): number {
  const ai = Array.from(a);
  const bi = Array.from(b);
  const n = Math.min(ai.length, bi.length);
  for (let i = 0; i < n; i += 1) {
    const d = (ai[i].codePointAt(0) as number) - (bi[i].codePointAt(0) as number);
    if (d !== 0) return d;
  }
  return ai.length - bi.length;
}

export function canonicalStringify(value: JsonValue): string {
  const active = new Set<object>();
  const encode = (node: JsonValue, depth: number): string => {
    if (depth > MAX_CANONICAL_DEPTH) {
      throw new CanonicalJsonError('JSON nesting exceeds bounded depth', 'depth');
    }
    if (node === null) return 'null';
    if (node === true) return 'true';
    if (node === false) return 'false';
    if (node instanceof PyFloat) return pyFloatRepr(node.value);
    if (typeof node === 'number') {
      if (!Number.isSafeInteger(node)) {
        throw new CanonicalJsonError('plain numbers must be safe integers; wrap floats in PyFloat', 'number');
      }
      return String(node);
    }
    if (typeof node === 'string') {
      if (node.length > MAX_CANONICAL_TEXT) throw new CanonicalJsonError('oversized JSON string', 'bound');
      const result = escapeString(node);
      if (result.length > MAX_CANONICAL_TEXT) throw new CanonicalJsonError('oversized canonical JSON', 'bound');
      return result;
    }
    if (typeof node !== 'object' || active.has(node)) {
      throw new CanonicalJsonError('invalid or cyclic JSON structure', 'json_type');
    }
    active.add(node);
    try {
      let result: string;
      if (Array.isArray(node)) {
        if (node.length > MAX_CANONICAL_ITEMS) throw new CanonicalJsonError('JSON array size exceeds bound', 'bound');
        const parts: string[] = [];
        let bytes = 2;
        for (const item of node) {
          const encoded = encode(item, depth + 1);
          bytes += encoded.length + (parts.length ? 1 : 0);
          if (bytes > MAX_CANONICAL_TEXT) throw new CanonicalJsonError('oversized canonical JSON', 'bound');
          parts.push(encoded);
        }
        result = '[' + parts.join(',') + ']';
      } else {
        const record = node as Record<string, JsonValue>;
        if (Object.getPrototypeOf(record) !== Object.prototype && Object.getPrototypeOf(record) !== null) {
          throw new CanonicalJsonError('JSON object must be a plain record', 'json_type');
        }
        const keys = Object.keys(record).sort(compareCodepoints);
        if (keys.length > MAX_CANONICAL_ITEMS) throw new CanonicalJsonError('JSON object size exceeds bound', 'bound');
        const parts: string[] = [];
        let bytes = 2;
        for (const key of keys) {
          const descriptor = Object.getOwnPropertyDescriptor(record, key);
          if (!descriptor || !('value' in descriptor)) {
            throw new CanonicalJsonError('JSON accessor is not canonical data', 'json_type');
          }
          const entry = escapeString(key) + ':' + encode(descriptor.value, depth + 1);
          bytes += entry.length + (parts.length ? 1 : 0);
          if (bytes > MAX_CANONICAL_TEXT) throw new CanonicalJsonError('oversized canonical JSON', 'bound');
          parts.push(entry);
        }
        result = '{' + parts.join(',') + '}';
      }
      return result;
    } finally {
      active.delete(node);
    }
  };
  return encode(value, 0);
}

/** Strict JSON parser that keeps int/float lexemes apart and rejects duplicate keys. */
export function parseCanonicalJson(text: string): JsonValue {
  if (typeof text !== 'string') throw new CanonicalJsonError('JSON source must be text', 'malformed');
  if (text.length > MAX_CANONICAL_TEXT) throw new CanonicalJsonError('JSON source exceeds bounded bytes', 'bound');
  let pos = 0;
  const fail = (msg: string): never => {
    throw new CanonicalJsonError(`${msg} at offset ${pos}`, 'malformed');
  };
  const ws = () => {
    while (pos < text.length && ' \t\n\r'.includes(text[pos])) pos += 1;
  };
  const parseString = (): string => {
    if (text[pos] !== '"') fail('expected string');
    pos += 1;
    let out = '';
    for (;;) {
      if (pos >= text.length) fail('unterminated string');
      const ch = text[pos];
      if (ch === '"') {
        pos += 1;
        return out;
      }
      if (ch === '\\') {
        const esc = text[pos + 1];
        const simple: Record<string, string> = { '"': '"', '\\': '\\', '/': '/', b: '\b', f: '\f', n: '\n', r: '\r', t: '\t' };
        if (esc in simple) {
          out += simple[esc];
          pos += 2;
        } else if (esc === 'u') {
          const hex = text.slice(pos + 2, pos + 6);
          if (!/^[0-9a-fA-F]{4}$/.test(hex)) fail('bad unicode escape');
          out += String.fromCharCode(parseInt(hex, 16));
          pos += 6;
        } else fail('bad escape');
      } else {
        if (ch.charCodeAt(0) < 0x20) fail('control character in string');
        out += ch;
        pos += 1;
      }
    }
  };
  const parseNumber = (): number | PyFloat => {
    const m = /^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?/.exec(text.slice(pos));
    if (!m) return fail('bad number');
    pos += m[0].length;
    const n = Number(m[0]);
    if (m[2] || m[3]) {
      if (!Number.isFinite(n)) fail('non-finite float');
      return new PyFloat(n);
    }
    if (!Number.isSafeInteger(n)) fail('integer outside safe range');
    return n;
  };
  const parseValue = (depth: number): JsonValue => {
    if (depth > 64) fail('nesting too deep');
    ws();
    const ch = text[pos];
    if (ch === '{') {
      pos += 1;
      const obj: { [key: string]: JsonValue } = {};
      ws();
      if (text[pos] === '}') {
        pos += 1;
        return obj;
      }
      let entries = 0;
      for (;;) {
        if (++entries > MAX_CANONICAL_ITEMS) fail('JSON object exceeds item ceiling');
        ws();
        const key = parseString();
        if (Object.prototype.hasOwnProperty.call(obj, key)) {
          throw new CanonicalJsonError(`duplicate JSON key: ${key}`, 'duplicate_key');
        }
        ws();
        if (text[pos] !== ':') fail('expected colon');
        pos += 1;
        Object.defineProperty(obj, key, { value: parseValue(depth + 1), enumerable: true, writable: true, configurable: true });
        ws();
        if (text[pos] === ',') {
          pos += 1;
          continue;
        }
        if (text[pos] === '}') {
          pos += 1;
          return obj;
        }
        fail('expected comma or brace');
      }
    }
    if (ch === '[') {
      pos += 1;
      const arr: JsonValue[] = [];
      ws();
      if (text[pos] === ']') {
        pos += 1;
        return arr;
      }
      for (;;) {
        if (arr.length >= MAX_CANONICAL_ITEMS) fail('JSON array exceeds item ceiling');
        arr.push(parseValue(depth + 1));
        ws();
        if (text[pos] === ',') {
          pos += 1;
          continue;
        }
        if (text[pos] === ']') {
          pos += 1;
          return arr;
        }
        fail('expected comma or bracket');
      }
    }
    if (ch === '"') return parseString();
    if (text.startsWith('true', pos)) {
      pos += 4;
      return true;
    }
    if (text.startsWith('false', pos)) {
      pos += 5;
      return false;
    }
    if (text.startsWith('null', pos)) {
      pos += 4;
      return null;
    }
    return parseNumber();
  };
  const value = parseValue(0);
  ws();
  if (pos !== text.length) fail('trailing data');
  return value;
}

/** Python `==` semantics for JSON scalars (1 == 1.0 == True). */
export function pyScalarEquals(a: JsonScalar | undefined, b: JsonScalar | undefined): boolean {
  const num = (v: JsonScalar | undefined): number | undefined => {
    if (v instanceof PyFloat) return v.value;
    if (typeof v === 'number') return v;
    if (typeof v === 'boolean') return v ? 1 : 0;
    return undefined;
  };
  const an = num(a);
  const bn = num(b);
  if (an !== undefined && bn !== undefined) return an === bn;
  return a === b;
}
