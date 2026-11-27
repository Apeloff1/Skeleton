/** Lossless presentation adapter. The existing server owns operation validity. */
export type ParameterPath = readonly (string | number)[];
export type ParameterNode = {
  kind: 'object' | 'array' | 'string' | 'number' | 'boolean' | 'null';
  path: ParameterPath;
  value: unknown;
  start: number;
  end: number;
  entryStart?: number;
  children: ParameterNode[];
};
export const FORGE_PARAMETER_LIMITS = Object.freeze({
  rawChars: 512000, compactBytes: 128000, topFields: 32, depth: 64, nodes: 20000,
});
export type ParameterInspection =
  | { ok: true; root: ParameterNode; value: Record<string, unknown>; bytes: number; fieldCount: number }
  | { ok: false; error: string };

/** Count JSON's actual UTF-8 size without depending on a native TextEncoder. */
function utf8Bytes(text: string): number {
  let count = 0;
  for (let i = 0; i < text.length; i += 1) {
    const code = text.charCodeAt(i);
    if (code <= 0x7f) count += 1;
    else if (code <= 0x7ff) count += 2;
    else if (code >= 0xd800 && code <= 0xdbff && text.charCodeAt(i + 1) >= 0xdc00 && text.charCodeAt(i + 1) <= 0xdfff) {
      count += 4; i += 1;
    } else count += 3;
  }
  return count;
}

function decimalIdentity(text: string): string {
  const parts = /^(-?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$/.exec(text)!;
  let digits = (parts[2] + (parts[3] || '')).replace(/^0+/, '');
  if (!digits) return '0';
  const exponent = Number(parts[4] || 0);
  if (!Number.isSafeInteger(exponent)) throw new Error('Use a number that the editor can represent exactly.');
  let power = exponent - (parts[3]?.length || 0);
  while (digits.endsWith('0')) { digits = digits.slice(0, -1); power += 1; }
  return parts[1] + digits + 'e' + power;
}

/** Never silently round a long integer, decimal, exponent or unfinished draft. */
export function parseForgeNumber(text: string): number {
  if (!/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(text)) {
    throw new Error('Finish this number using JSON notation, such as 12, -0.5 or 1e3.');
  }
  const value = Number(text);
  if (!Number.isFinite(value) || Number.isInteger(value) && !Number.isSafeInteger(value)
      || decimalIdentity(text) !== decimalIdentity(String(value))) {
    throw new Error('This number cannot be represented without rounding. Repair it in Advanced JSON.');
  }
  return value;
}

/** Parse value spans, including duplicate-key detection, without rewriting input. */
export function inspectForgeParameters(raw: string): ParameterInspection {
  try {
    if (typeof raw !== 'string' || raw.length > FORGE_PARAMETER_LIMITS.rawChars) {
      throw new Error('The parameter draft exceeds the bounded editor size. Reduce it in Advanced JSON.');
    }
    let at = 0; let count = 0;
    const whitespace = () => { while (at < raw.length && /[ \t\r\n]/.test(raw[at])) at += 1; };
    const fail = (): never => { throw new Error('The parameters contain unfinished or invalid JSON. Your exact text is retained in Advanced JSON.'); };
    const string = (): string => {
      if (raw[at] !== '"') return fail();
      const start = at++;
      while (at < raw.length) {
        const character = raw[at++];
        if (character === '"') {
          try { return JSON.parse(raw.slice(start, at)); } catch { return fail(); }
        }
        if (character === '\\') at += 1;
        else if (character.charCodeAt(0) < 32) return fail();
      }
      return fail();
    };
    const walk = (path: ParameterPath, depth: number): ParameterNode => {
      whitespace();
      if (++count > FORGE_PARAMETER_LIMITS.nodes || depth > FORGE_PARAMETER_LIMITS.depth) {
        throw new Error('The draft exceeds guided inspection limits. Reduce its nesting or item count in Advanced JSON.');
      }
      const start = at;
      const node: ParameterNode = { kind: 'null', value: null, path, start, end: start, children: [] };
      const character = raw[at];
      if (character === '{') {
        node.kind = 'object';
        const value: Record<string, unknown> = {}; const keys = new Set<string>(); at += 1; whitespace();
        if (raw[at] !== '}') while (true) {
          whitespace(); const entryStart = at; const key = string(); whitespace();
          if (keys.has(key)) throw new Error('Duplicate parameter names are ambiguous. Remove the duplicate in Advanced JSON.');
          keys.add(key);
          if (raw[at++] !== ':') return fail();
          const child = walk([...path, key], depth + 1); child.entryStart = entryStart; node.children.push(child);
          Object.defineProperty(value, key, { value: child.value, writable: true, enumerable: true, configurable: true });
          whitespace();
          if (raw[at] !== ',') break;
          at += 1;
        }
        if (raw[at++] !== '}') return fail();
        node.value = value;
      } else if (character === '[') {
        node.kind = 'array'; const value: unknown[] = []; at += 1; whitespace();
        if (raw[at] !== ']') while (true) {
          const child = walk([...path, value.length], depth + 1); child.entryStart = child.start;
          node.children.push(child); value.push(child.value); whitespace();
          if (raw[at] !== ',') break;
          at += 1;
        }
        if (raw[at++] !== ']') return fail();
        node.value = value;
      } else if (character === '"') { node.kind = 'string'; node.value = string(); }
      else {
        while (at < raw.length && !/[ \t\r\n,\]}]/.test(raw[at])) at += 1;
        const token = raw.slice(start, at);
        if (token === 'true' || token === 'false') { node.kind = 'boolean'; node.value = token === 'true'; }
        else if (token === 'null') node.value = null;
        else { node.kind = 'number'; node.value = parseForgeNumber(token); }
      }
      node.end = at; return node;
    };
    const root = walk([], 0); whitespace();
    if (at !== raw.length) return fail();
    if (root.kind !== 'object') throw new Error('Action parameters must be a JSON object. Repair the root in Advanced JSON.');
    if (root.children.length > FORGE_PARAMETER_LIMITS.topFields) throw new Error('An operation supports at most 32 top-level parameters.');
    const bytes = utf8Bytes(JSON.stringify(root.value));
    if (bytes > FORGE_PARAMETER_LIMITS.compactBytes) throw new Error('The operation exceeds 128,000 compact UTF-8 JSON bytes. Reduce it before queueing.');
    return { ok: true, root, value: root.value as Record<string, unknown>, bytes, fieldCount: count - 1 };
  } catch (cause) {
    return { ok: false, error: cause instanceof Error ? cause.message : 'The parameters could not be inspected. Your exact JSON is retained.' };
  }
}

function checked(raw: string, expectedRaw: string): Extract<ParameterInspection, { ok: true }> {
  if (raw !== expectedRaw) throw new Error('The parameter draft changed. Review its current value before applying this edit.');
  const result = inspectForgeParameters(raw); if (!result.ok) throw new Error(result.error); return result;
}
function atPath(root: ParameterNode, path: ParameterPath): ParameterNode {
  let current = root;
  for (const part of path) {
    if (current.kind === 'array' && (typeof part !== 'number' || !Number.isInteger(part) || part < 0)
        || current.kind === 'object' && typeof part !== 'string'
        || current.kind !== 'array' && current.kind !== 'object') throw new Error('This parameter path no longer exists.');
    const child = current.children.find(item => item.path[item.path.length - 1] === part);
    if (!child) throw new Error('This parameter path no longer exists.'); current = child;
  }
  return current;
}
function serialized(value: unknown): string {
  const seen = new Set<object>(); let count = 0;
  const visit = (part: unknown, depth: number): string => {
    if (++count > FORGE_PARAMETER_LIMITS.nodes || depth > FORGE_PARAMETER_LIMITS.depth) throw new Error('The replacement exceeds guided inspection limits.');
    if (part === null || typeof part === 'string' || typeof part === 'boolean') return JSON.stringify(part);
    if (typeof part === 'number') { parseForgeNumber(String(part)); return Object.is(part, -0) ? '-0' : String(part); }
    if (typeof part !== 'object' || seen.has(part)) throw new Error('Use a finite JSON value without cycles or executable properties.');
    const prototype = Object.getPrototypeOf(part);
    if (!Array.isArray(part) && prototype !== Object.prototype && prototype !== null) throw new Error('Use a plain JSON object.');
    seen.add(part);
    if (Array.isArray(part) && (Object.keys(part).length !== part.length
        || Object.keys(part).some((key, index) => key !== String(index)))) throw new Error('JSON arrays must contain explicit contiguous items without named properties.');
    const encoded: string[] = [];
    for (const key of Reflect.ownKeys(part)) {
      if (Array.isArray(part) && key === 'length') continue;
      if (typeof key !== 'string') throw new Error('JSON parameters cannot contain symbol keys.');
      const descriptor = Object.getOwnPropertyDescriptor(part, key)!;
      if (!('value' in descriptor) || !descriptor.enumerable) throw new Error('JSON parameters cannot contain accessors or hidden properties.');
      encoded.push((Array.isArray(part) ? '' : JSON.stringify(key) + ':') + visit(descriptor.value, depth + 1));
    }
    seen.delete(part);
    return (Array.isArray(part) ? '[' : '{') + encoded.join(',') + (Array.isArray(part) ? ']' : '}');
  };
  return visit(value, 0);
}
function verifiedEdit(raw: string): string {
  const result = inspectForgeParameters(raw); if (!result.ok) throw new Error(result.error); return raw;
}
export function replaceForgeParameter(raw: string, expectedRaw: string, path: ParameterPath, replacement: unknown): string {
  const document = checked(raw, expectedRaw); const node = atPath(document.root, path);
  const encoded = serialized(replacement);
  if (serialized(node.value) === encoded) return raw;
  return verifiedEdit(raw.slice(0, node.start) + encoded + raw.slice(node.end));
}
export function removeForgeParameter(raw: string, expectedRaw: string, path: ParameterPath): string {
  if (!path.length) throw new Error('The root parameter object cannot be removed.');
  const document = checked(raw, expectedRaw); const parent = atPath(document.root, path.slice(0, -1)); const node = atPath(document.root, path);
  const index = parent.children.indexOf(node); const next = parent.children[index + 1]; const previous = parent.children[index - 1];
  const start = next ? node.entryStart! : previous ? previous.end : node.entryStart!;
  const end = next ? next.entryStart! : node.end;
  return verifiedEdit(raw.slice(0, start) + raw.slice(end));
}
export function appendForgeParameter(raw: string, expectedRaw: string, parentPath: ParameterPath, key: string | null, value: unknown): string {
  const document = checked(raw, expectedRaw); const parent = atPath(document.root, parentPath);
  if (parent.kind !== 'array' && parent.kind !== 'object') throw new Error('Choose an object or array before adding a value.');
  if (parent.kind === 'object' && (typeof key !== 'string' || parent.children.some(child => child.path[child.path.length - 1] === key))) throw new Error('Choose a new, unique parameter name.');
  if (parent.kind === 'array' && key !== null) throw new Error('Array items do not have property names.');
  const entry = (parent.children.length ? ',' : '') + (parent.kind === 'object' ? JSON.stringify(key) + ':' : '') + serialized(value);
  return verifiedEdit(raw.slice(0, parent.end - 1) + entry + raw.slice(parent.end - 1));
}
export function duplicateForgeParameter(raw: string, expectedRaw: string, path: ParameterPath): string {
  if (!path.length) throw new Error('Choose an array item to duplicate.');
  const document = checked(raw, expectedRaw); const parent = atPath(document.root, path.slice(0, -1)); const node = atPath(document.root, path);
  if (parent.kind !== 'array') throw new Error('Only array items can be duplicated.');
  return verifiedEdit(raw.slice(0, parent.end - 1) + ',' + raw.slice(node.start, node.end) + raw.slice(parent.end - 1));
}
export function parameterPathLabel(path: ParameterPath): string {
  return '/' + path.map(part => String(part).replace(/~/g, '~0').replace(/\//g, '~1')).join('/');
}
