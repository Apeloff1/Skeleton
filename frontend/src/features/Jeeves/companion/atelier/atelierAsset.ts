/** Presentation-only admission. No network, authority, or persistence. */
export const ATELIER_SCHEMA = 'skeleton.dragon.atelier-fold.admission.v1';
import pin from '../emeraldAssetPin.json';
export const MAX_MODEL_BYTES = 512 * 1024 * 1024;
export const PEAK_MODEL_BYTES = pin.native.modelBytes;
export const PEAK_MODEL_SHA256 = pin.native.modelSha256;
const PEAK_CLIPS = 380;
const PEAK_JOINTS = 108;
const MAX_JSON = 32 * 1024 * 1024;
export const FAMILIES = ['ground','takeoff','flight','landing'] as const;
export type Family = typeof FAMILIES[number];
export type Catalogue = Readonly<Record<Family, readonly string[]>>;
export interface AtelierReceipt {
  readonly schema: typeof ATELIER_SCHEMA;
  readonly sha256: string;
  readonly bytes: number;
  readonly joints: number;
  readonly clips: readonly string[];
  readonly families: Catalogue;
}
type Row = Record<string, unknown>;
function check(condition: unknown, reason: string): asserts condition {
  if (!condition) throw new Error(reason);
}
function row(value: unknown): Row {
  check(value !== null && typeof value === 'object' && !Array.isArray(value), 'Invalid model object');
  return value as Row;
}
function list(value: unknown, maximum: number): unknown[] {
  check(Array.isArray(value) && value.length <= maximum, 'Invalid or excessive model list');
  return value;
}
function names(value: unknown, floor: number): string[] {
  const values = list(value, 1024);
  check(values.length >= floor && values.every(name => typeof name === 'string' && name.length > 0 && name.length <= 256 && name.trim() === name && !/[\u0000-\u001f\u007f]/.test(name)), 'Invalid clip names');
  const result = values as string[];
  check(new Set(result).size === result.length, 'Duplicate clip name');
  return [...result];
}
function integer(value: unknown, low: number, high: number): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= low && value <= high;
}
export function parseReceipt(value: unknown, trustedDigest: string): AtelierReceipt {
  const v = row(value);
  check(/^[0-9a-f]{64}$/.test(trustedDigest), 'Enter an independently trusted SHA-256');
  check(v.schema === ATELIER_SCHEMA && v.asset === 'emerald_continuum.glb' && v.sha256 === trustedDigest, 'Wrong asset or custody digest');
  check(integer(v.bytes, 32, MAX_MODEL_BYTES) && v.joints === PEAK_JOINTS, 'Unsupported model dimensions');
  const clips = names(v.clips, PEAK_CLIPS);
  check(clips.length === PEAK_CLIPS, 'Original catalogue must retain all 380 clips');
  const available = new Set(clips);
  const seen = new Set<string>();
  const families = row(v.families);
  check(Object.keys(families).length === 4, 'Four explicit families required');
  const copy = {} as Record<Family, readonly string[]>;
  for (const family of FAMILIES) {
    const values = names(families[family], 1);
    for (const name of values) {
      check(available.has(name) && !seen.has(name), 'Unknown or overlapping family clip');
      seen.add(name);
    }
    copy[family] = Object.freeze(values);
  }
  check(seen.size === available.size, 'Unassigned original clips');
  return Object.freeze({schema: ATELIER_SCHEMA, sha256: trustedDigest, bytes: v.bytes, joints: v.joints, clips: Object.freeze(clips), families: Object.freeze(copy)});
}
export function parsePeakReceipt(value: unknown): AtelierReceipt {
  const receipt=parseReceipt(value,PEAK_MODEL_SHA256);
  check(receipt.bytes===PEAK_MODEL_BYTES,'Receipt does not identify the pinned original Fold model');
  return receipt;
}
const ALLOWED_EXTENSIONS = new Set(['KHR_materials_clearcoat','KHR_materials_sheen','KHR_materials_specular','KHR_materials_ior','KHR_materials_emissive_strength','KHR_materials_unlit','KHR_texture_transform','KHR_materials_transmission','KHR_materials_volume','KHR_materials_iridescence','KHR_materials_anisotropy','KHR_mesh_quantization']);
function inspectEmbeddedDocument(document: Row): void {
  check(row(document.asset).version === '2.0', 'Not glTF 2.0');
  check(document.extensionsRequired === undefined || list(document.extensionsRequired, 32).length === 0, 'Required extensions are not qualified');
  if (document.extensionsUsed !== undefined) check(list(document.extensionsUsed, 32).every(e => typeof e === 'string' && ALLOWED_EXTENSIONS.has(e)), 'Unqualified glTF extension');
  const pending: unknown[] = [document];
  let visited = 0;
  while (pending.length) {
    check(++visited <= 5_000_000, 'Excessive GLB JSON structure');
    const value = pending.pop();
    if (Array.isArray(value)) {
      for (const child of value) pending.push(child);
    } else if (value !== null && typeof value === 'object') {
      for (const [key, child] of Object.entries(value)) {
        check(!['uri','url','__proto__','constructor','prototype'].includes(key), 'External or unsafe resource property');
        pending.push(child);
      }
    }
  }
}
export function inspectBuffer(bytes: ArrayBuffer, receipt: AtelierReceipt): void {
  check(bytes.byteLength === receipt.bytes && bytes.byteLength >= 32, 'Asset size mismatch');
  const data = new DataView(bytes);
  check(data.getUint32(0,true) === 0x46546c67 && data.getUint32(4,true) === 2 && data.getUint32(8,true) === bytes.byteLength, 'Invalid GLB header');
  const size = data.getUint32(12,true);
  check(size >= 4 && size <= MAX_JSON && size % 4 === 0 && size+28 <= bytes.byteLength && data.getUint32(16,true) === 0x4e4f534a, 'Invalid GLB JSON chunk');
  const binary = data.getUint32(size+20,true);
  check(binary % 4 === 0 && binary+size+28 === bytes.byteLength && data.getUint32(size+24,true) === 0x004e4942, 'Invalid GLB binary chunk');
  const document = row(JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(new Uint8Array(bytes,20,size))));
  inspectEmbeddedDocument(document);
  const buffers = list(document.buffers,1);
  check(buffers.length === 1, 'Embedded buffer required');
  const declared = row(buffers[0]).byteLength;
  check(integer(declared,1,binary) && binary-declared <= 3, 'Invalid embedded buffer length');
  for (const item of list(document.bufferViews ?? [],200000)) {
    const view = row(item);
    const offset = view.byteOffset ?? 0;
    check(view.buffer === 0 && integer(offset,0,declared) && integer(view.byteLength,1,declared-offset), 'Out of bounds buffer view');
  }
  const nodeCount = list(document.nodes,8192).length;
  let jointCount=0;
  for (const item of list(document.skins,128)) {
    const joints = new Set<number>();
    for (const joint of list(row(item).joints,8192)) {
      check(integer(joint,0,nodeCount-1), 'Invalid skin joint');
      check(!joints.has(joint),'Duplicate skin joint');joints.add(joint);
    }
    jointCount=Math.max(jointCount,joints.size);
  }
  check(jointCount === receipt.joints, 'Rig differs from receipt');
  const clips = names(list(document.animations,1024).map(a=>row(a).name),PEAK_CLIPS);
  check(clips.length === receipt.clips.length && clips.every((clip,i)=>clip === receipt.clips[i]), 'Animation catalogue differs from receipt');
}
function readAbortable(model:File,signal?:AbortSignal):Promise<ArrayBuffer>{
  if(signal?.aborted)return Promise.reject(new Error('Prototype closed'));
  if(!signal)return model.arrayBuffer();
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    const cleanup=()=>signal.removeEventListener('abort',cancel);
    const cancel=()=>reader.abort();
    reader.onload=()=>{cleanup();if(signal.aborted||!(reader.result instanceof ArrayBuffer))reject(new Error('Prototype closed or unreadable'));else resolve(reader.result);};
    reader.onerror=()=>{cleanup();reject(new Error('Local file could not be read'));};
    reader.onabort=()=>{cleanup();reject(new Error('Prototype closed'));};
    signal.addEventListener('abort',cancel,{once:true});
    try{reader.readAsArrayBuffer(model);}catch(error){cleanup();reject(error);}
  });
}
export async function verifyFile(model: File, receipt: AtelierReceipt, signal?:AbortSignal): Promise<ArrayBuffer> {
  check(model.name === 'emerald_continuum.glb' && model.size === receipt.bytes, 'Select the original model');
  check(typeof crypto !== 'undefined' && !!crypto.subtle, 'Secure local SHA-256 is unavailable');
  const bytes = await readAbortable(model,signal);
  check(!signal?.aborted,'Prototype closed');
  const hash = new Uint8Array(await crypto.subtle.digest('SHA-256',bytes));
  check(!signal?.aborted,'Prototype closed');
  const actual = Array.from(hash,b=>b.toString(16).padStart(2,'0')).join('');
  check(actual === receipt.sha256, 'Model digest mismatch');
  inspectBuffer(bytes,receipt);
  return bytes;
}
